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
from .core import (
    Citation,
    get_artifact_or_404,
    get_session_factory,
    get_settings,
    serialize_citation,
)
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


def _as_utc(value):
    """Return *value* with tzinfo=UTC when SQLite strips it on persist."""

    from datetime import UTC

    if value is None:
        return value
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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

    def verify(self, artifact_id: str, *, force: bool = False) -> VerifyResult:
        from datetime import UTC, timedelta

        from .citation_verifier import CitationOutcome
        from .core import utcnow

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
                get_artifact_or_404(session, artifact_id)
                citations = session.scalars(
                    select(Citation)
                    .where(Citation.artifact_id == artifact_id)
                    .order_by(Citation.created_at.asc())
                ).all()

                # Same-minute dedupe: if every citation was checked within the
                # last 60 seconds, surface the persisted state instead of
                # burning another round-trip. Callers can opt out via force=True.
                if not force and citations and all(
                    c.last_checked_at is not None
                    and (_as_utc(c.last_checked_at) > utcnow() - timedelta(seconds=60))
                    for c in citations
                ):
                    cached = VerifyResult(artifact_id=artifact_id)
                    cached.outcomes = [
                        CitationOutcome(
                            citation_id=c.id,
                            resolved_state=c.resolved_state,
                            last_observed=c.last_observed,
                        )
                        for c in citations
                    ]
                    return cached

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


class CitationInsightService:
    """Reads that surface context for a single citation (preview, diff)."""

    #: Number of context lines shown before/after a repo_range citation.
    PREVIEW_CONTEXT_LINES = 3
    #: Soft cap on bytes surfaced in PR body / commit message previews.
    PREVIEW_TEXT_LIMIT = 2_000

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_factory = get_session_factory()

    def preview(self, citation_id: str) -> dict:
        citation = self._load_citation(citation_id)

        if citation.kind == "repo_range":
            return self._preview_repo_range(citation)
        if citation.kind == "repo_pr":
            return self._preview_repo_pr(citation)
        if citation.kind == "repo_commit":
            return self._preview_repo_commit(citation)
        if citation.kind == "transcript_range":
            return self._preview_transcript_range(citation)
        raise ValueError(f"Unknown citation kind: {citation.kind}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_citation(self, citation_id: str) -> Citation:
        with self._session_factory() as session:
            row = session.get(Citation, citation_id)
            if row is None:
                raise ValueError("Citation not found")
            session.expunge(row)
            return row

    def _reader(self) -> tuple[CachedGitHubReader, GitHubClient]:
        token = self._settings.github_default_token
        if not token:
            raise GitHubAuthError(
                "No GitHub token available. Set GITHUB_DEFAULT_TOKEN to load citation previews."
            )
        client = GitHubClient(token)
        reader = CachedGitHubReader(client, self._session_factory)
        return reader, client

    def _preview_repo_range(self, citation: Citation) -> dict:
        target = citation.target or {}
        observed = citation.last_observed or {}
        repo = str(target.get("repo") or "")
        path = str(target.get("path") or "")
        target_start = int(target.get("line_start") or 0)
        target_end = int(target.get("line_end") or 0)
        at_ref = str(observed.get("at_ref") or target.get("ref_at_draft") or "")
        if not (repo and path and target_start > 0 and target_end >= target_start and at_ref):
            raise ValueError("repo_range citation is missing required target fields")

        # If the verifier suggested a new range at HEAD, prefer it so the preview
        # shows the current code. Otherwise we preview the pinned range as-is.
        suggested = observed.get("suggested_range") or {}
        render_start = int(suggested.get("line_start") or target_start)
        render_end = int(suggested.get("line_end") or target_end)

        reader, client = self._reader()
        try:
            file_content = reader.get_file(repo, at_ref, path)
        finally:
            client.close()

        lines = _decode_lines(file_content.content)
        context_start = max(1, render_start - self.PREVIEW_CONTEXT_LINES)
        context_end = min(len(lines), render_end + self.PREVIEW_CONTEXT_LINES)

        window = []
        for line_no in range(context_start, context_end + 1):
            window.append(
                {
                    "line": line_no,
                    "text": lines[line_no - 1],
                    "highlighted": render_start <= line_no <= render_end,
                }
            )
        return {
            "citation_id": citation.id,
            "kind": "repo_range",
            "at_ref": at_ref,
            "path": path,
            "target_start": render_start,
            "target_end": render_end,
            "context_start": context_start,
            "context_end": context_end,
            "lines": window,
        }

    def _preview_repo_pr(self, citation: Citation) -> dict:
        target = citation.target or {}
        repo = str(target.get("repo") or "")
        number = int(target.get("number") or 0)
        if not (repo and number):
            raise ValueError("repo_pr citation is missing repo or number")

        reader, client = self._reader()
        try:
            pr = client.get_pr(repo, number)
        finally:
            client.close()

        return {
            "citation_id": citation.id,
            "kind": "repo_pr",
            "repo": repo,
            "number": number,
            "title": pr.title,
            "state": pr.state,
            "merged": pr.merged,
            "html_url": pr.html_url,
        }

    def _preview_repo_commit(self, citation: Citation) -> dict:
        target = citation.target or {}
        repo = str(target.get("repo") or "")
        sha = str(target.get("sha") or "")
        if not (repo and sha):
            raise ValueError("repo_commit citation is missing repo or sha")

        reader, client = self._reader()
        try:
            commit = client.get_commit(repo, sha)
        finally:
            client.close()

        return {
            "citation_id": citation.id,
            "kind": "repo_commit",
            "repo": repo,
            "sha": commit.sha,
            "message": commit.message[: self.PREVIEW_TEXT_LIMIT],
            "html_url": commit.html_url,
        }

    def _preview_transcript_range(self, citation: Citation) -> dict:
        # Transcript previews are served from the spec source rows, not GitHub.
        # For v1 we return the target range as-is; the frontend already knows
        # the transcript text. Later we can splice the matching segment here.
        target = citation.target or {}
        return {
            "citation_id": citation.id,
            "kind": "transcript_range",
            "start": target.get("start"),
            "end": target.get("end"),
        }


def _decode_lines(content: bytes) -> list[str]:
    text = content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return text.split("\n")
