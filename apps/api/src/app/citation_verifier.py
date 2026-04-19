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
        """Run a verify pass for *artifact_id*. Per-kind resolution lands next."""

        raise NotImplementedError("CitationVerifier.verify is wired in subsequent commits.")
