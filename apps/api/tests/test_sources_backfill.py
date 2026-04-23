"""Tests for the SpecSource → Source/Snapshot/Link backfill."""

from __future__ import annotations

from app.auth import User, hash_password
from app.core import Artifact, Conversation, SpecSource
from app.projects import (
    PERSONAL_PROJECT_NAME,
    Project,
    ProjectMember,
    ROLE_OWNER,
)
from app.sources import (
    KIND_REPO,
    KIND_TRANSCRIPT,
    ROLE_DERIVED_FROM,
    PadSourceLink,
    Source,
    SourceSnapshot,
    backfill_spec_sources,
    _extract_repo_slug,
)


def _seeded_pad(session) -> tuple[User, Project, Artifact]:
    user = User(email="a@example.com", password_hash=hash_password("correct-horse"))
    session.add(user)
    session.flush()
    project = Project(name=PERSONAL_PROJECT_NAME, created_by_user_id=user.id)
    session.add(project)
    session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role=ROLE_OWNER))
    conv = Conversation(title="seed", owner_id=user.id, project_id=project.id)
    session.add(conv)
    session.flush()
    art = Artifact(
        conversation_id=conv.id,
        origin_conversation_id=conv.id,
        title="RFC",
        content="body",
        content_type="markdown",
        version=1,
        project_id=project.id,
    )
    session.add(art)
    session.flush()
    return user, project, art


def test_backfill_promotes_transcript_and_repo_sources(session) -> None:
    _, project, art = _seeded_pad(session)
    session.add(
        SpecSource(
            artifact_id=art.id,
            kind="transcript",
            payload={"text": "Standup notes\nLine two", "hash": "deadbeef"},
        )
    )
    session.add(
        SpecSource(
            artifact_id=art.id,
            kind="repo",
            payload={"repo": "acme/widget", "ref_pinned": "abc123"},
        )
    )
    session.commit()

    summary = backfill_spec_sources(session)
    assert summary == {"sources": 2, "snapshots": 2, "links": 2, "skipped": 0}

    sources = session.query(Source).all()
    kinds = {s.kind for s in sources}
    assert kinds == {KIND_TRANSCRIPT, KIND_REPO}
    for s in sources:
        assert s.project_id == project.id

    links = session.query(PadSourceLink).all()
    assert {link.role for link in links} == {ROLE_DERIVED_FROM}
    assert all(link.added_by_system for link in links)

    # Transcript snapshot carries content_text, repo snapshot doesn't.
    snapshots = {
        snap.source_id: snap for snap in session.query(SourceSnapshot).all()
    }
    repo_source = next(s for s in sources if s.kind == KIND_REPO)
    transcript_source = next(s for s in sources if s.kind == KIND_TRANSCRIPT)
    assert snapshots[repo_source.id].content_text is None
    assert snapshots[repo_source.id].snapshot_ref == "abc123"
    assert snapshots[transcript_source.id].content_text.startswith("Standup notes")


def test_backfill_is_idempotent(session) -> None:
    _, _, art = _seeded_pad(session)
    session.add(
        SpecSource(
            artifact_id=art.id,
            kind="transcript",
            payload={"text": "hello world"},
        )
    )
    session.commit()

    first = backfill_spec_sources(session)
    second = backfill_spec_sources(session)

    assert first["sources"] == 1
    assert second == {"sources": 0, "snapshots": 0, "links": 0, "skipped": 0}
    assert session.query(Source).count() == 1
    assert session.query(PadSourceLink).count() == 1


def test_backfill_skips_orphan_and_unusable_rows(session) -> None:
    # Orphan artifact: project_id=None (pre-Phase-1D data that failed the
    # personal-project backfill). Must not blow up; must not promote.
    orphan_conv = Conversation(title="orphan")
    session.add(orphan_conv)
    session.flush()
    orphan_art = Artifact(
        conversation_id=orphan_conv.id,
        title="orphan",
        content="",
        content_type="markdown",
        version=1,
    )
    session.add(orphan_art)
    session.flush()
    session.add(
        SpecSource(
            artifact_id=orphan_art.id,
            kind="transcript",
            payload={"text": "never mapped"},
        )
    )

    # Unusable payload on a real pad: empty transcript text.
    _, _, art = _seeded_pad(session)
    session.add(
        SpecSource(
            artifact_id=art.id,
            kind="transcript",
            payload={"text": "   "},
        )
    )
    session.commit()

    summary = backfill_spec_sources(session)
    assert summary["sources"] == 0
    assert summary["links"] == 0
    assert summary["skipped"] == 2


def test_backfill_dedupes_repo_across_pads_in_same_project(session) -> None:
    _, project, art_a = _seeded_pad(session)
    # Second pad in the same project pointing at the same repo slug.
    conv_b = Conversation(
        title="thread B", owner_id=art_a.conversation.owner_id, project_id=project.id
    )
    session.add(conv_b)
    session.flush()
    art_b = Artifact(
        conversation_id=conv_b.id,
        origin_conversation_id=conv_b.id,
        title="RFC 2",
        content="",
        content_type="markdown",
        version=1,
        project_id=project.id,
    )
    session.add(art_b)
    session.flush()

    for art in (art_a, art_b):
        session.add(
            SpecSource(
                artifact_id=art.id,
                kind="repo",
                payload={"url": "https://github.com/acme/widget", "ref_pinned": "sha1"},
            )
        )
    session.commit()

    summary = backfill_spec_sources(session)
    # One source shared, one snapshot shared, two links — one per pad.
    assert summary == {"sources": 1, "snapshots": 1, "links": 2, "skipped": 0}


def test_extract_repo_slug_accepts_urls_and_bare_slugs() -> None:
    assert _extract_repo_slug("https://github.com/acme/widget") == "acme/widget"
    assert _extract_repo_slug("https://github.com/acme/widget.git") == "acme/widget"
    assert _extract_repo_slug("git@github.com:acme/widget.git") == "acme/widget"
    assert _extract_repo_slug("acme/widget") == "acme/widget"
    assert _extract_repo_slug("") is None
    assert _extract_repo_slug("not a repo") is None
