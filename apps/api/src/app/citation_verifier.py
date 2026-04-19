"""Drift detection for v1 spec citations.

Given an artifact, the verifier walks each :class:`Citation` row, fetches
the current state of its target via :class:`CachedGitHubReader`, and
classifies it as ``live`` / ``stale`` / ``missing`` by comparing against
the pinned ``ref_at_draft`` / ``content_hash_at_draft`` captured when the
spec was drafted.

This scaffold commits the public surface; the per-kind resolution
methods, content-match suggestion, 50-citation cap, and persistence step
land in the next commits. The draft()-facing shape is kept small so the
HTTP route and the frontend store can be wired against it early.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .github_client import GitHubClientError, GitHubNotFoundError
from .hashing import content_hash_for_range

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .github_client import CachedGitHubReader


#: Maximum citations resolved in a single pass before we bail out. Guards
#: the GitHub rate-limit budget when a spec has hundreds of anchors.
MAX_CITATIONS_PER_PASS = 50


@dataclass
class CitationOutcome:
    """Per-citation verification result. Written back to the row."""

    citation_id: str
    resolved_state: str  # one of "live" | "stale" | "missing" | "unknown"
    last_observed: dict[str, Any] | None = None


@dataclass
class VerifyResult:
    """Summary of a whole-artifact verify pass."""

    artifact_id: str
    outcomes: list[CitationOutcome] = field(default_factory=list)
    truncated: bool = False
    remaining: int = 0

    def counts_by_state(self) -> dict[str, int]:
        counts = {"live": 0, "stale": 0, "missing": 0, "unknown": 0}
        for outcome in self.outcomes:
            counts[outcome.resolved_state] = counts.get(outcome.resolved_state, 0) + 1
        return counts


class CitationVerifier:
    """Drives a verify pass against the repo(s) referenced by one artifact.

    Dependency-injected like the drafter so tests can hand in a
    :class:`CachedGitHubReader` wired to :class:`httpx.MockTransport`.
    """

    def __init__(self, *, github_reader: CachedGitHubReader) -> None:
        self._github_reader = github_reader

    def verify(
        self,
        *,
        artifact_id: str,
        citations: Iterable[Any],
        session: Session,
    ) -> VerifyResult:
        """Run a verify pass for *artifact_id*.

        Caches the current HEAD sha per repo for the duration of the pass
        so a spec with many citations against the same repo pays for one
        resolve_head call, not N. Per-citation exceptions are swallowed
        into ``unknown`` outcomes so a single transient failure doesn't
        sink the whole pass.
        """

        result = VerifyResult(artifact_id=artifact_id)
        head_cache: dict[str, str] = {}

        for citation in citations:
            outcome = self._resolve_one(citation, head_cache=head_cache)
            if outcome is not None:
                result.outcomes.append(outcome)

        return result

    # ------------------------------------------------------------------
    # Per-kind resolution
    # ------------------------------------------------------------------

    def _resolve_one(
        self,
        citation: Any,
        *,
        head_cache: dict[str, str],
    ) -> CitationOutcome | None:
        kind = getattr(citation, "kind", None)
        target = getattr(citation, "target", None) or {}
        if kind == "repo_range":
            return self._resolve_repo_range(citation, target, head_cache)
        if kind == "repo_pr":
            return self._resolve_repo_pr(citation, target)
        if kind == "repo_commit":
            return self._resolve_repo_commit(citation, target)
        if kind == "transcript_range":
            return CitationOutcome(
                citation_id=str(citation.id),
                resolved_state="live",
                last_observed=None,
            )
        return CitationOutcome(citation_id=str(citation.id), resolved_state="unknown")

    def _head_for_repo(self, repo: str, head_cache: dict[str, str]) -> str | None:
        cached = head_cache.get(repo)
        if cached is not None:
            return cached
        try:
            sha = self._github_reader.client.resolve_head(repo)
        except (GitHubNotFoundError, GitHubClientError):
            return None
        head_cache[repo] = sha
        return sha

    def _resolve_repo_range(
        self,
        citation: Any,
        target: dict[str, Any],
        head_cache: dict[str, str],
    ) -> CitationOutcome:
        citation_id = str(citation.id)
        repo = target.get("repo")
        path = target.get("path")
        line_start = target.get("line_start")
        line_end = target.get("line_end")
        pinned_hash = target.get("content_hash_at_draft")
        ref_at_draft = target.get("ref_at_draft")

        if not (
            isinstance(repo, str)
            and isinstance(path, str)
            and isinstance(line_start, int)
            and isinstance(line_end, int)
            and isinstance(pinned_hash, str)
        ):
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        head_sha = self._head_for_repo(repo, head_cache)
        if head_sha is None:
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        # When HEAD hasn't moved past draft, the file cannot have drifted.
        if ref_at_draft and head_sha == ref_at_draft:
            return CitationOutcome(
                citation_id=citation_id,
                resolved_state="live",
                last_observed={"at_ref": head_sha},
            )

        try:
            file_content = self._github_reader.get_file(repo, head_sha, path)
        except GitHubNotFoundError:
            return CitationOutcome(
                citation_id=citation_id,
                resolved_state="missing",
                last_observed={"at_ref": head_sha, "path": path, "reason": "path_gone"},
            )
        except GitHubClientError:
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        observed_hash = content_hash_for_range(file_content.content, line_start, line_end)
        if observed_hash == pinned_hash:
            return CitationOutcome(
                citation_id=citation_id,
                resolved_state="live",
                last_observed={"at_ref": head_sha},
            )
        return CitationOutcome(
            citation_id=citation_id,
            resolved_state="stale",
            last_observed={
                "at_ref": head_sha,
                "observed_hash": observed_hash,
                "pinned_ref": ref_at_draft,
            },
        )

    def _resolve_repo_pr(self, citation: Any, target: dict[str, Any]) -> CitationOutcome:
        citation_id = str(citation.id)
        repo = target.get("repo")
        number = target.get("number")
        if not (isinstance(repo, str) and isinstance(number, int) and number > 0):
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        try:
            pr = self._github_reader.client.get_pr(repo, number)
        except GitHubNotFoundError:
            return CitationOutcome(
                citation_id=citation_id,
                resolved_state="missing",
                last_observed={"reason": "pr_deleted"},
            )
        except GitHubClientError:
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        # PRs are always "live" unless deleted; state/title changes go into
        # last_observed so the pill can surface them without marking stale.
        observed: dict[str, Any] = {
            "state": pr.state,
            "merged": pr.merged,
            "title": pr.title,
            "html_url": pr.html_url,
        }
        title_at_draft = target.get("title_at_draft")
        if isinstance(title_at_draft, str) and title_at_draft and title_at_draft != pr.title:
            observed["title_changed"] = True
        return CitationOutcome(
            citation_id=citation_id,
            resolved_state="live",
            last_observed=observed,
        )

    def _resolve_repo_commit(self, citation: Any, target: dict[str, Any]) -> CitationOutcome:
        citation_id = str(citation.id)
        repo = target.get("repo")
        sha = target.get("sha")
        if not (isinstance(repo, str) and isinstance(sha, str) and len(sha) >= 7):
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        try:
            commit = self._github_reader.client.get_commit(repo, sha)
        except GitHubNotFoundError:
            return CitationOutcome(
                citation_id=citation_id,
                resolved_state="missing",
                last_observed={"reason": "commit_unreachable"},
            )
        except GitHubClientError:
            return CitationOutcome(citation_id=citation_id, resolved_state="unknown")

        return CitationOutcome(
            citation_id=citation_id,
            resolved_state="live",
            last_observed={"sha": commit.sha, "html_url": commit.html_url},
        )
