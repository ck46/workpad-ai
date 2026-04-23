"""Sources: normalized, project-scoped references to external material.

A ``Source`` is the canonical record for one piece of input (a repo, a
pasted transcript, a note, an uploaded file, an image). A
``SourceSnapshot`` pins the content at a moment in time so citations
can survive drift. A ``PadSourceLink`` joins a pad to the snapshots it
draws on.

Supersedes the narrower ``SpecSource`` table, which stays read-only
through Phase 2 and is backfilled into this schema in a later Stream A
commit. See ``docs/V1_SPEC.md`` §Source Model.

Schema registers on the shared ``Base`` so ``Base.metadata.create_all``
picks all three tables up on startup.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .core import Base, utcnow

# ---------------------------------------------------------------------------
# Kind / role vocabularies — kept as module constants so callers don't
# sprinkle magic strings.
# ---------------------------------------------------------------------------
KIND_REPO = "repo"
KIND_TRANSCRIPT = "transcript"
KIND_NOTE = "note"
KIND_FILE = "file"
KIND_IMAGE = "image"
_KINDS = (KIND_REPO, KIND_TRANSCRIPT, KIND_NOTE, KIND_FILE, KIND_IMAGE)

ROLE_PRIMARY = "primary"
ROLE_CONTEXT = "context"
ROLE_CITED = "cited"
ROLE_DERIVED_FROM = "derived_from"
_ROLES = (ROLE_PRIMARY, ROLE_CONTEXT, ROLE_CITED, ROLE_DERIVED_FROM)


def valid_kind(kind: str) -> bool:
    return kind in _KINDS


def valid_role(role: str) -> bool:
    return role in _ROLES


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(500))
    provider: Mapped[str] = mapped_column(String(32))
    # Stable key for dedupe within a project (repo slug, file sha, transcript
    # hash). Nullable because notes and ad-hoc inputs may not have one.
    canonical_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    # Opaque identifier for what was captured: commit SHA for repos, content
    # hash for files/transcripts/notes.
    snapshot_ref: Mapped[str] = mapped_column(String(128))
    # Extracted text. Empty for repos (fetched live via github_client); set
    # for everything else so chunkers can index without re-fetching.
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PadSourceLink(Base):
    __tablename__ = "pad_source_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # Pads are modeled as ``Artifact`` in core.py; FK points at that table.
    pad_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=ROLE_CONTEXT)
    added_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, default=None
    )
    # True when a link was inserted by a backfill or drafter rather than a
    # direct user action — lets the UI distinguish "I attached this" from
    # "the system attached this for me."
    added_by_system: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
