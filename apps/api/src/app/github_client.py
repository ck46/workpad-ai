"""Thin read-only GitHub REST client used by the v1 spec drafter.

This module is intentionally small: we only need a handful of endpoints
(tree, file, PR, commit, ref resolution) and a predictable caching /
rate-limit story. Endpoint methods and cache integration are added
incrementally in later commits; this scaffold covers the shared plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


GITHUB_API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "workpad-ai/0.1 (github.com/ck46/workpad-ai)"


class GitHubClientError(Exception):
    """Base class for all GitHub client errors."""


class GitHubAuthError(GitHubClientError):
    """Raised when the server rejects the token (401/403-without-rate-limit)."""


class GitHubNotFoundError(GitHubClientError):
    """Raised when a requested resource does not exist at the given ref."""


class GitHubRateLimitError(GitHubClientError):
    """Raised when the authenticated rate-limit budget is exhausted (or near it)."""


class GitHubRequestError(GitHubClientError):
    """Raised for unexpected HTTP failures."""


@dataclass(frozen=True)
class FileContent:
    """A file fetched at a specific ref, suitable for caching."""

    content: bytes
    sha: str
    etag: str | None


class GitHubClient:
    """Small authenticated wrapper over `httpx.Client`.

    Intentionally synchronous - the drafter and verifier run inside
    FastAPI background work and benefit from simple, testable calls.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = GITHUB_API_ROOT,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise GitHubAuthError("A GitHub token is required (set GITHUB_DEFAULT_TOKEN).")
        self._token = token
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
