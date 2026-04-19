"""HTTP-facing glue for the v1 spec drafter.

Wraps :class:`RFCDrafter` with dependency wiring (OpenAI client, GitHub
client + cache reader, session factory) and exposes the SSE generator the
FastAPI route streams to clients.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from openai import OpenAI
from sqlalchemy import select

from .citation_verifier import CitationVerifier, VerifyResult
from .core import Citation, get_artifact_or_404, get_session_factory, get_settings, serialize_citation
from .github_client import (
    CachedGitHubReader,
    GitHubAuthError,
    GitHubClient,
    GitHubClientError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from .rfc_drafter import DraftResult, OpenAIResponsesAIClient, RFCDrafter
from .schemas import SpecDraftRequest


_SENTINEL = object()


def _sse_event(payload: dict[str, Any]) -> str:
    return f"event: app\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def _classify_error(exc: BaseException) -> dict[str, Any]:
    """Map a raised exception to a structured SSE error event.

    Error ``code`` is a stable string the frontend can branch on; ``message``
    is the short form we surface to users. Anything unexpected falls into
    ``unexpected`` so the frontend can still surface *something* useful
    instead of spinning forever.
    """

    if isinstance(exc, GitHubAuthError):
        return {"type": "error", "code": "invalid_pat", "message": str(exc)}
    if isinstance(exc, GitHubRateLimitError):
        return {"type": "error", "code": "rate_limit", "message": str(exc)}
    if isinstance(exc, GitHubNotFoundError):
        return {"type": "error", "code": "repo_unreachable", "message": str(exc)}
    if isinstance(exc, GitHubClientError):
        return {"type": "error", "code": "github_error", "message": str(exc)}
    if isinstance(exc, ValueError):
        return {"type": "error", "code": "invalid_input", "message": str(exc)}
    if exc.__class__.__module__.startswith("openai"):
        return {"type": "error", "code": "model_error", "message": str(exc) or exc.__class__.__name__}
    return {
        "type": "error",
        "code": "unexpected",
        "message": str(exc) or exc.__class__.__name__,
    }


class SpecDraftService:
    """Instantiates and drives :class:`RFCDrafter` for each request."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_factory = get_session_factory()

    # ------------------------------------------------------------------
    # Non-streaming entry point (kept for tests / simple callers).
    # ------------------------------------------------------------------

    def draft(self, payload: SpecDraftRequest) -> DraftResult:
        drafter, github_client = self._build_drafter(payload)
        try:
            return drafter.draft(
                conversation_id=payload.conversation_id,
                transcript=payload.transcript,
                repo=payload.repo,
            )
        finally:
            github_client.close()

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------

    def stream_draft(self, payload: SpecDraftRequest) -> Iterator[str]:
        """Yield SSE-formatted events as each draft phase lands.

        The drafter runs on a worker thread and emits progress events into
        a queue. The generator drains the queue as it produces, so the
        client sees pass 1 finish before pass 2 starts even though the
        enclosing HTTP call is serial.
        """

        event_queue: queue.Queue[Any] = queue.Queue()

        try:
            drafter, github_client = self._build_drafter(payload)
        except Exception as exc:  # noqa: BLE001 - surface any setup failure as an event
            yield _sse_event(_classify_error(exc))
            return

        def emit(event: dict[str, Any]) -> None:
            event_queue.put(event)

        def worker() -> None:
            try:
                result = drafter.draft(
                    conversation_id=payload.conversation_id,
                    transcript=payload.transcript,
                    repo=payload.repo,
                    on_event=emit,
                )
                event_queue.put(
                    {
                        "type": "stream.completed",
                        "artifact_id": result.artifact_id,
                        "conversation_id": result.conversation_id,
                        "citation_count": len(result.citations),
                        "dropped_count": len(result.dropped_citations),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - deliver any failure as an event
                event_queue.put(_classify_error(exc))
            finally:
                event_queue.put(_SENTINEL)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            while True:
                event = event_queue.get()
                if event is _SENTINEL:
                    break
                yield _sse_event(event)
        finally:
            thread.join(timeout=1.0)
            github_client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_drafter(self, payload: SpecDraftRequest) -> tuple[RFCDrafter, GitHubClient]:
        token = payload.github_token or self._settings.github_default_token
        if not token:
            raise GitHubAuthError(
                "No GitHub token available. Provide github_token on the request "
                "or set GITHUB_DEFAULT_TOKEN in the server environment."
            )
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured on the server.")

        github_client = GitHubClient(token)
        github_reader = CachedGitHubReader(github_client, self._session_factory)
        openai_client = OpenAI(api_key=self._settings.openai_api_key)
        ai_client = OpenAIResponsesAIClient(openai_client, self._settings.default_model)

        drafter = RFCDrafter(
            ai_client=ai_client,
            github_reader=github_reader,
            session_factory=self._session_factory,
            model=self._settings.default_model,
        )
        return drafter, github_client


class CitationVerifyService:
    """Runs a verify pass for an existing artifact."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_factory = get_session_factory()

    def verify(self, artifact_id: str) -> VerifyResult:
        token = self._settings.github_default_token
        if not token:
            raise GitHubAuthError(
                "No GitHub token available. Set GITHUB_DEFAULT_TOKEN to verify citations."
            )

        github_client = GitHubClient(token)
        try:
            reader = CachedGitHubReader(github_client, self._session_factory)
            verifier = CitationVerifier(github_reader=reader)

            with self._session_factory() as session:
                # Existence check raises ValueError (-> 404) when the id is unknown.
                get_artifact_or_404(session, artifact_id)
                citations = session.scalars(
                    select(Citation)
                    .where(Citation.artifact_id == artifact_id)
                    .order_by(Citation.created_at.asc())
                ).all()
                return verifier.verify(
                    artifact_id=artifact_id, citations=citations, session=session
                )
        finally:
            github_client.close()

    def serialize_citations(self, artifact_id: str) -> list:
        with self._session_factory() as session:
            rows = session.scalars(
                select(Citation)
                .where(Citation.artifact_id == artifact_id)
                .order_by(Citation.created_at.asc())
            ).all()
            return [serialize_citation(row) for row in rows]
