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

from .core import get_session_factory, get_settings
from .github_client import CachedGitHubReader, GitHubAuthError, GitHubClient
from .rfc_drafter import DraftResult, OpenAIResponsesAIClient, RFCDrafter
from .schemas import SpecDraftRequest


_SENTINEL = object()


def _sse_event(payload: dict[str, Any]) -> str:
    return f"event: app\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


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
            yield _sse_event({"type": "error", "message": str(exc)})
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
                event_queue.put({"type": "error", "message": str(exc)})
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
