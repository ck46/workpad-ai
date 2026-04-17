"""Thin read-only GitHub REST client used by the v1 spec drafter.

This module is intentionally small: we only need a handful of endpoints
(tree, file, PR, commit, ref resolution) and a predictable caching /
rate-limit story. Endpoint methods and cache integration are added
incrementally in later commits; this scaffold covers the shared plumbing.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


GITHUB_API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "workpad-ai/0.1 (github.com/ck46/workpad-ai)"

# Abort before we completely exhaust the 5K/hr authenticated budget so an
# in-flight verify pass doesn't leave the system stranded mid-spec.
RATE_LIMIT_BUFFER = 10


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


@dataclass(frozen=True)
class PRMeta:
    """Minimal PR metadata used when citations point at a pull request."""

    number: int
    title: str
    state: str
    merged: bool
    html_url: str


@dataclass(frozen=True)
class CommitMeta:
    """Minimal commit metadata used for repo_commit citations."""

    sha: str
    message: str
    html_url: str


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
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: int | None = None

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

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Rate-limit plumbing
    # ------------------------------------------------------------------

    @property
    def rate_limit_remaining(self) -> int | None:
        """Last observed value of X-RateLimit-Remaining, or None before any call."""

        return self._rate_limit_remaining

    @property
    def rate_limit_reset(self) -> int | None:
        """Last observed rate-limit reset time as a Unix timestamp, or None."""

        return self._rate_limit_reset

    def _update_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            try:
                self._rate_limit_remaining = int(remaining)
            except ValueError:
                pass
        if reset is not None:
            try:
                self._rate_limit_reset = int(reset)
            except ValueError:
                pass

    def _guard_rate_limit(self) -> None:
        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_remaining < RATE_LIMIT_BUFFER
        ):
            raise GitHubRateLimitError(
                "GitHub rate limit near zero "
                f"(remaining={self._rate_limit_remaining}, reset={self._rate_limit_reset}). "
                "Wait for the reset window before retrying."
            )

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        if_none_match: str | None = None,
    ) -> httpx.Response:
        self._guard_rate_limit()

        merged_headers = dict(headers or {})
        if if_none_match:
            merged_headers["If-None-Match"] = if_none_match

        try:
            response = self._client.get(path, params=params, headers=merged_headers or None)
        except httpx.HTTPError as exc:
            raise GitHubRequestError(f"GitHub request failed: {exc}") from exc

        self._update_rate_limit(response)

        if response.status_code == 304:
            # Caller asked for a conditional fetch; cache is still valid.
            return response
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubRateLimitError(
                f"GitHub rate limit exhausted on {path} "
                f"(reset={self._rate_limit_reset})."
            )
        if response.status_code in (401, 403):
            raise GitHubAuthError(
                f"GitHub rejected the request ({response.status_code}) for {path}: "
                f"{response.text[:200]}"
            )
        if response.status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found: {path}")
        if response.status_code >= 400:
            raise GitHubRequestError(
                f"GitHub {response.status_code} on {path}: {response.text[:200]}"
            )
        return response

    # ------------------------------------------------------------------
    # Read endpoints
    # ------------------------------------------------------------------

    def get_tree(self, repo: str, ref: str) -> list[str]:
        """Return the file paths (blobs) in *repo* at *ref*.

        Uses the recursive git-tree endpoint. For very large repos the
        response may be truncated by GitHub; the client returns whatever
        paths came back without failing so callers can proceed with a
        partial view of the repo.
        """

        response = self._get(
            f"/repos/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        payload = response.json()
        return [entry["path"] for entry in payload.get("tree", []) if entry.get("type") == "blob"]

    def get_file(
        self,
        repo: str,
        ref: str,
        path: str,
        *,
        if_none_match: str | None = None,
    ) -> FileContent | None:
        """Fetch a single file at *ref* returning raw bytes, blob sha, and etag.

        When *if_none_match* is provided and the upstream etag still matches,
        returns ``None`` so callers can keep their cached copy without paying
        the rate-limit cost of a full fetch.

        Uses the contents endpoint in JSON mode because it surfaces the git
        blob sha alongside the content. Files larger than ~1 MB are not
        supported by this endpoint; callers hit a GitHubRequestError if they
        try. v1 intentionally accepts that limit.
        """

        response = self._get(
            f"/repos/{repo}/contents/{path}",
            params={"ref": ref},
            if_none_match=if_none_match,
        )
        if response.status_code == 304:
            return None

        payload = response.json()
        if payload.get("encoding") != "base64" or "content" not in payload:
            raise GitHubRequestError(
                f"Unexpected contents payload for {repo}@{ref}:{path} "
                f"(type={payload.get('type')}, encoding={payload.get('encoding')})"
            )

        content = base64.b64decode(payload["content"])
        sha = str(payload.get("sha") or "")
        etag = response.headers.get("ETag")
        return FileContent(content=content, sha=sha, etag=etag)

    def get_pr(self, repo: str, number: int) -> PRMeta:
        """Fetch metadata for a single pull request."""

        response = self._get(f"/repos/{repo}/pulls/{number}")
        payload = response.json()
        return PRMeta(
            number=int(payload["number"]),
            title=str(payload.get("title") or ""),
            state=str(payload.get("state") or "open"),
            merged=bool(payload.get("merged", False)),
            html_url=str(payload.get("html_url") or ""),
        )

    def get_commit(self, repo: str, sha: str) -> CommitMeta:
        """Fetch metadata for a commit at *sha*."""

        response = self._get(f"/repos/{repo}/commits/{sha}")
        payload = response.json()
        commit_block = payload.get("commit") or {}
        return CommitMeta(
            sha=str(payload.get("sha") or sha),
            message=str(commit_block.get("message") or ""),
            html_url=str(payload.get("html_url") or ""),
        )

    def resolve_head(self, repo: str, branch: str | None = None) -> str:
        """Return the commit SHA at HEAD of *branch* (default branch if omitted)."""

        if branch is None:
            repo_info = self._get(f"/repos/{repo}").json()
            branch = str(repo_info.get("default_branch") or "main")

        payload = self._get(f"/repos/{repo}/branches/{branch}").json()
        sha = (payload.get("commit") or {}).get("sha")
        if not sha:
            raise GitHubRequestError(
                f"No commit sha returned for {repo}@{branch}: {payload!r}"
            )
        return str(sha)


class CachedGitHubReader:
    """Reads that go through ``RepoCache`` before hitting the network.

    Sits between the drafter / verifier and the raw GitHubClient. On each
    get_file call it looks up the (repo, ref, path) row, sends a conditional
    request with the stored etag, and either (a) returns the cached bytes
    when GitHub responds 304, or (b) overwrites the entry with fresh content
    on a 200.
    """

    def __init__(self, client: GitHubClient, session_factory: "sessionmaker[Session]") -> None:
        self._client = client
        self._session_factory = session_factory

    def get_file(self, repo: str, ref: str, path: str) -> FileContent:
        # Local import keeps the ORM models out of the module-load path so
        # scripts that just want the raw client don't pull SQLAlchemy in.
        from .core import RepoCache, utcnow

        with self._session_factory() as session:
            cached = session.scalar(
                select(RepoCache).where(
                    RepoCache.repo == repo,
                    RepoCache.ref == ref,
                    RepoCache.path == path,
                )
            )

            fresh = self._client.get_file(
                repo,
                ref,
                path,
                if_none_match=cached.etag if cached and cached.etag else None,
            )

            if fresh is None:
                # 304 from upstream: our cached copy is still valid.
                if cached is None:
                    raise GitHubRequestError(
                        "GitHub returned 304 but we have no cached entry "
                        f"for {repo}@{ref}:{path}"
                    )
                cached.fetched_at = utcnow()
                session.commit()
                return FileContent(
                    content=bytes(cached.content),
                    sha=cached.content_hash,
                    etag=cached.etag,
                )

            content_hash = hashlib.sha256(fresh.content).hexdigest()
            if cached is None:
                session.add(
                    RepoCache(
                        repo=repo,
                        ref=ref,
                        path=path,
                        content=fresh.content,
                        content_hash=content_hash,
                        etag=fresh.etag,
                    )
                )
            else:
                cached.content = fresh.content
                cached.content_hash = content_hash
                cached.etag = fresh.etag
                cached.fetched_at = utcnow()
            session.commit()
            return fresh
