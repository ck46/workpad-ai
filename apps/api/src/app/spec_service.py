"""HTTP-facing glue for the v1 spec drafter.

Wraps :class:`RFCDrafter` with dependency wiring (OpenAI client, GitHub
client + cache reader, session factory) and exposes a small method the
FastAPI route calls. Streaming is added in a follow-up commit; this module
currently runs the draft synchronously and returns the :class:`DraftResult`.
"""

from __future__ import annotations

from openai import OpenAI

from .core import get_session_factory, get_settings
from .github_client import CachedGitHubReader, GitHubAuthError, GitHubClient
from .rfc_drafter import DraftResult, OpenAIResponsesAIClient, RFCDrafter
from .schemas import SpecDraftRequest


class SpecDraftService:
    """Instantiates and drives :class:`RFCDrafter` for each request."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session_factory = get_session_factory()

    def draft(self, payload: SpecDraftRequest) -> DraftResult:
        token = payload.github_token or self._settings.github_default_token
        if not token:
            raise GitHubAuthError(
                "No GitHub token available. Provide github_token on the request "
                "or set GITHUB_DEFAULT_TOKEN in the server environment."
            )
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured on the server.")

        github_client = GitHubClient(token)
        try:
            github_reader = CachedGitHubReader(github_client, self._session_factory)
            openai_client = OpenAI(api_key=self._settings.openai_api_key)
            ai_client = OpenAIResponsesAIClient(openai_client, self._settings.default_model)

            drafter = RFCDrafter(
                ai_client=ai_client,
                github_reader=github_reader,
                session_factory=self._session_factory,
                model=self._settings.default_model,
            )
            return drafter.draft(
                conversation_id=payload.conversation_id,
                transcript=payload.transcript,
                repo=payload.repo,
            )
        finally:
            github_client.close()
