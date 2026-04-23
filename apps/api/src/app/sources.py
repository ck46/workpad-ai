"""Sources: normalized, project-scoped references to external material.

A ``Source`` is the canonical record for one piece of input (a repo, a
pasted transcript, a note, an uploaded file, an image). A
``SourceSnapshot`` pins the content at a moment in time so citations
can survive drift. A ``PadSourceLink`` joins a pad to the snapshots it
draws on.

Supersedes the narrower ``SpecSource`` table. ``SpecSource`` rows are
migrated into this schema by :func:`backfill_spec_sources`, which runs
on every boot and is idempotent; ``SpecSource`` itself stays read-only
through Phase 2 so pre-backfill call sites keep working. See
``docs/V1_SPEC.md`` §Source Model.

Schema registers on the shared ``Base`` so ``Base.metadata.create_all``
picks all three tables up on startup.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .core import Base, utcnow

log = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# SpecSource → Source backfill
#
# One-shot migration that rebuilds every ``SpecSource`` row as a
# ``Source`` + ``SourceSnapshot`` + ``PadSourceLink`` trio, scoped to the
# pad's project. Idempotent: dedupes on (project_id, kind, canonical_key)
# for sources and (pad_id, source_id) for links, so a second run is a
# no-op. Orphans (artifact without project_id, or conversation without
# owner) are skipped with a warning — mirroring the personal-project
# backfill's handling.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _MappedSource:
    kind: str
    title: str
    provider: str
    canonical_key: str | None
    snapshot_ref: str
    content_text: str | None
    content_hash: str
    metadata_json: dict[str, Any]
    provenance_json: dict[str, Any]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_repo_slug(url_or_slug: str) -> str | None:
    """Pull ``owner/name`` out of a repo URL or accept a bare slug."""

    raw = (url_or_slug or "").strip()
    if not raw:
        return None
    match = re.search(r"github\.com[/:]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", raw)
    if match:
        return match.group(1)
    # Accept ``owner/name`` directly.
    if re.fullmatch(r"[^/\s]+/[^/\s]+", raw):
        return raw
    return None


def _summarize_transcript(text: str) -> str:
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return (first[:80] if first else "Transcript")


def _map_spec_source(kind: str, payload: dict[str, Any]) -> _MappedSource | None:
    """Map a ``SpecSource`` (kind, payload) onto new-schema fields.

    Returns ``None`` when the row's payload is unusable (empty transcript,
    missing repo slug). The backfill skips those rather than inserting a
    placeholder row.
    """

    payload = payload or {}
    if kind == "transcript":
        text = (payload.get("text") or "").strip()
        if not text:
            return None
        content_hash = payload.get("hash") or _hash_text(text)
        metadata = {k: v for k, v in payload.items() if k != "text"}
        return _MappedSource(
            kind=KIND_TRANSCRIPT,
            title=_summarize_transcript(text),
            provider="paste",
            canonical_key=content_hash,
            snapshot_ref=content_hash,
            content_text=text,
            content_hash=content_hash,
            metadata_json=metadata,
            provenance_json=dict(payload),
        )
    if kind == "repo":
        slug = _extract_repo_slug(payload.get("repo") or payload.get("url") or "")
        if not slug:
            return None
        ref_pinned = (payload.get("ref_pinned") or "").strip()
        snapshot_ref = ref_pinned or "unpinned"
        content_hash = _hash_text(f"{slug}:{snapshot_ref}")
        metadata = {"ref_pinned": ref_pinned} if ref_pinned else {}
        return _MappedSource(
            kind=KIND_REPO,
            title=slug,
            provider="github",
            canonical_key=slug,
            snapshot_ref=snapshot_ref,
            content_text=None,
            content_hash=content_hash,
            metadata_json=metadata,
            provenance_json=dict(payload),
        )
    return None


def backfill_spec_sources(session: Session) -> dict[str, int]:
    """Rebuild every ``SpecSource`` row as Source/Snapshot/Link.

    Idempotent; safe to call on every boot. Returns a summary dict
    with ``sources``, ``snapshots``, ``links``, ``skipped`` counts.
    """

    # Local import so ``core`` can import ``sources`` inside ``init_db``
    # without circular-import pain at module load time.
    from .core import Artifact, Conversation, SpecSource

    rows = session.execute(
        select(SpecSource, Artifact, Conversation)
        .join(Artifact, Artifact.id == SpecSource.artifact_id)
        .join(Conversation, Conversation.id == Artifact.conversation_id)
    ).all()

    sources_created = 0
    snapshots_created = 0
    links_created = 0
    skipped = 0

    for spec_source, artifact, conversation in rows:
        if artifact.project_id is None or conversation.owner_id is None:
            skipped += 1
            continue
        mapped = _map_spec_source(spec_source.kind, spec_source.payload)
        if mapped is None:
            skipped += 1
            continue

        source = session.scalar(
            select(Source)
            .where(Source.project_id == artifact.project_id)
            .where(Source.kind == mapped.kind)
            .where(Source.canonical_key == mapped.canonical_key)
        )
        if source is None:
            source = Source(
                project_id=artifact.project_id,
                kind=mapped.kind,
                title=mapped.title,
                provider=mapped.provider,
                canonical_key=mapped.canonical_key,
                provenance_json=mapped.provenance_json,
                created_by_user_id=conversation.owner_id,
            )
            session.add(source)
            session.flush()
            sources_created += 1

        snapshot = session.scalar(
            select(SourceSnapshot)
            .where(SourceSnapshot.source_id == source.id)
            .where(SourceSnapshot.snapshot_ref == mapped.snapshot_ref)
        )
        if snapshot is None:
            snapshot = SourceSnapshot(
                source_id=source.id,
                snapshot_ref=mapped.snapshot_ref,
                content_text=mapped.content_text,
                content_hash=mapped.content_hash,
                metadata_json=mapped.metadata_json,
            )
            session.add(snapshot)
            session.flush()
            snapshots_created += 1

        existing_link = session.scalar(
            select(PadSourceLink)
            .where(PadSourceLink.pad_id == artifact.id)
            .where(PadSourceLink.source_id == source.id)
        )
        if existing_link is None:
            session.add(
                PadSourceLink(
                    pad_id=artifact.id,
                    source_id=source.id,
                    source_snapshot_id=snapshot.id,
                    role=ROLE_DERIVED_FROM,
                    added_by_system=True,
                )
            )
            links_created += 1

    if sources_created or snapshots_created or links_created:
        session.commit()
        log.info(
            "sources backfill: %d sources, %d snapshots, %d links (skipped %d)",
            sources_created,
            snapshots_created,
            links_created,
            skipped,
        )

    return {
        "sources": sources_created,
        "snapshots": snapshots_created,
        "links": links_created,
        "skipped": skipped,
    }
