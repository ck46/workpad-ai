"""Tests for the one-shot Personal-project backfill."""

from __future__ import annotations

import logging

from app.auth import User, hash_password
from app.core import Artifact, Conversation
from app.projects import (
    PERSONAL_PROJECT_NAME,
    Project,
    ProjectMember,
    ROLE_OWNER,
    backfill_personal_projects,
)


def _make_user(session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("correct-horse"))
    session.add(user)
    session.flush()
    return user


def _stale_conversation(session, user: User, title: str) -> Conversation:
    """A pre-projects conversation: owner set, project_id NULL."""

    conv = Conversation(title=title, owner_id=user.id)
    session.add(conv)
    session.flush()
    return conv


def _stale_artifact(session, conv: Conversation, title: str) -> Artifact:
    art = Artifact(
        conversation_id=conv.id,
        origin_conversation_id=conv.id,
        title=title,
        content="body",
        content_type="markdown",
        version=1,
    )
    session.add(art)
    session.flush()
    return art


def test_backfill_assigns_each_owner_a_personal_project(session) -> None:
    user_a = _make_user(session, "a@example.com")
    user_b = _make_user(session, "b@example.com")
    conv_a = _stale_conversation(session, user_a, "A convo")
    conv_b = _stale_conversation(session, user_b, "B convo")
    art_a = _stale_artifact(session, conv_a, "A pad")
    art_b = _stale_artifact(session, conv_b, "B pad")
    session.commit()

    summary = backfill_personal_projects(session)
    assert summary["projects_created"] == 2
    assert summary["conversations"] == 2
    assert summary["artifacts"] == 2

    session.refresh(conv_a)
    session.refresh(conv_b)
    session.refresh(art_a)
    session.refresh(art_b)

    assert conv_a.project_id is not None
    assert conv_b.project_id is not None
    assert conv_a.project_id != conv_b.project_id
    # Artifact inherits from conversation.
    assert art_a.project_id == conv_a.project_id
    assert art_b.project_id == conv_b.project_id

    # Each project is named "Personal" and owned by the right user.
    project_a = session.get(Project, conv_a.project_id)
    assert project_a is not None
    assert project_a.name == PERSONAL_PROJECT_NAME
    assert project_a.created_by_user_id == user_a.id

    member_a = (
        session.query(ProjectMember).filter_by(project_id=project_a.id, user_id=user_a.id).one()
    )
    assert member_a.role == ROLE_OWNER


def test_backfill_is_idempotent(session) -> None:
    user = _make_user(session, "idem@example.com")
    conv = _stale_conversation(session, user, "Idempotent convo")
    _stale_artifact(session, conv, "Idempotent pad")
    session.commit()

    first = backfill_personal_projects(session)
    assert first["projects_created"] == 1
    assert first["conversations"] == 1

    # Second run migrates nothing.
    second = backfill_personal_projects(session)
    assert second["projects_created"] == 0
    assert second["conversations"] == 0
    assert second["artifacts"] == 0

    # And there's still exactly one Personal project for the user.
    projects = session.query(Project).filter_by(created_by_user_id=user.id).all()
    assert len(projects) == 1


def test_backfill_skips_orphan_owner_ids(session, caplog) -> None:
    """A conversation whose owner_id points at a non-existent user stays NULL."""

    caplog.set_level(logging.WARNING, logger="app.projects")
    conv = Conversation(title="Ghost conv", owner_id="ghost-user-id")
    session.add(conv)
    session.commit()

    summary = backfill_personal_projects(session)
    assert summary["projects_created"] == 0
    assert summary["conversations"] == 0

    session.refresh(conv)
    assert conv.project_id is None

    messages = [rec.message for rec in caplog.records]
    assert any("orphan owner_id" in m for m in messages)


def test_backfill_skips_conversations_without_owner(session) -> None:
    """Pre-owner_id conversations (owner_id NULL) are also left alone."""

    conv = Conversation(title="No owner", owner_id=None)
    session.add(conv)
    session.commit()

    summary = backfill_personal_projects(session)
    assert summary["conversations"] == 0
    session.refresh(conv)
    assert conv.project_id is None


def test_backfill_preserves_already_assigned_rows(session) -> None:
    """A conversation that already has a project_id must not be re-homed."""

    user = _make_user(session, "keeper@example.com")
    existing_project = Project(name="Project Alpha", created_by_user_id=user.id)
    session.add(existing_project)
    session.flush()
    session.add(
        ProjectMember(project_id=existing_project.id, user_id=user.id, role=ROLE_OWNER)
    )
    conv = Conversation(title="Already placed", owner_id=user.id, project_id=existing_project.id)
    session.add(conv)
    session.flush()
    art = Artifact(
        conversation_id=conv.id,
        origin_conversation_id=conv.id,
        title="Already placed pad",
        content="",
        content_type="markdown",
        version=1,
        project_id=existing_project.id,
    )
    session.add(art)
    session.commit()

    summary = backfill_personal_projects(session)
    assert summary["conversations"] == 0
    assert summary["artifacts"] == 0

    session.refresh(conv)
    session.refresh(art)
    assert conv.project_id == existing_project.id
    assert art.project_id == existing_project.id

    # And no "Personal" project was created for this user.
    personal = (
        session.query(Project)
        .filter_by(created_by_user_id=user.id, name=PERSONAL_PROJECT_NAME)
        .all()
    )
    assert personal == []


def test_backfill_handles_artifact_with_orphan_conversation(session) -> None:
    """An artifact whose conversation was deleted is left with project_id NULL."""

    art = Artifact(
        conversation_id="deleted-conversation-id",
        origin_conversation_id="deleted-conversation-id",
        title="Orphaned pad",
        content="",
        content_type="markdown",
        version=1,
    )
    session.add(art)
    session.commit()

    summary = backfill_personal_projects(session)
    assert summary["artifacts"] == 0
    session.refresh(art)
    assert art.project_id is None
