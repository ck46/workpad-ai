"""Projects: the top-level container in v1.

A ``Project`` groups pads, threads, sources, and members. There is no
workspace layer above it — a user either has access to a given project
(as ``owner`` or ``member``) or they don't.

Invite model: a signed bearer token. Any signed-in user who holds the
token can accept it and become a ``member``. The ``email`` field on the
invite is informational (so owners can see who they sent it to) but is
not enforced at accept time. This matches how small teams actually use
shareable invite links.

Schema is registered on the shared ``Base`` so ``Base.metadata.create_all``
picks up all three tables on startup.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import User, find_user_by_email, normalize_email
from .core import Base, utcnow


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
INVITE_TTL_DAYS = 14

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"
_ROLES = (ROLE_OWNER, ROLE_MEMBER)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(240))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MEMBER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invite(Base):
    __tablename__ = "project_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    invited_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ProjectError(Exception):
    """Base class for project-domain errors mapped to HTTP by the caller."""


class NotAMember(ProjectError):
    pass


class NotOwner(ProjectError):
    pass


class InviteInvalid(ProjectError):
    pass


# ---------------------------------------------------------------------------
# Token hashing (shared pattern with password reset)
# ---------------------------------------------------------------------------
def _hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Membership helpers
# ---------------------------------------------------------------------------
def get_membership(session: Session, project_id: str, user_id: str) -> ProjectMember | None:
    return session.scalar(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .where(ProjectMember.user_id == user_id)
    )


def require_member(session: Session, project_id: str, user_id: str) -> ProjectMember:
    membership = get_membership(session, project_id, user_id)
    if membership is None:
        raise NotAMember()
    return membership


def require_owner(session: Session, project_id: str, user_id: str) -> ProjectMember:
    membership = require_member(session, project_id, user_id)
    if membership.role != ROLE_OWNER:
        raise NotOwner()
    return membership


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------
def create_project(session: Session, *, name: str, owner: User) -> Project:
    cleaned = (name or "").strip()[:240]
    if not cleaned:
        raise ValueError("project name is required")
    project = Project(name=cleaned, created_by_user_id=owner.id)
    session.add(project)
    session.flush()  # get project.id for the member row
    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ROLE_OWNER))
    session.commit()
    session.refresh(project)
    return project


def list_projects_for_user(session: Session, user_id: str) -> list[tuple[Project, str]]:
    """Return the user's projects paired with their role in each."""

    rows = session.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
        .order_by(Project.updated_at.desc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def get_project_for_user(session: Session, project_id: str, user_id: str) -> tuple[Project, str]:
    membership = require_member(session, project_id, user_id)
    project = session.get(Project, project_id)
    if project is None:
        # Member row exists but project doesn't — shouldn't happen with
        # ON DELETE CASCADE, but guard anyway.
        raise NotAMember()
    return project, membership.role


def list_members(session: Session, project_id: str) -> list[tuple[ProjectMember, User]]:
    rows = session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def list_pending_invites(session: Session, project_id: str) -> list[Invite]:
    return list(
        session.scalars(
            select(Invite)
            .where(Invite.project_id == project_id)
            .where(Invite.accepted_at.is_(None))
            .order_by(Invite.created_at.desc())
        )
    )


# ---------------------------------------------------------------------------
# Invite flow
# ---------------------------------------------------------------------------
def create_invite(
    session: Session, *, project: Project, email: str, invited_by: User
) -> tuple[Invite, str]:
    """Mint a new invite token. Returns (record, raw_token).

    The raw token is only returned so the caller can build a copy-paste URL;
    only the hash is persisted.
    """

    require_owner(session, project.id, invited_by.id)
    clean_email = normalize_email(email or "")
    if not clean_email or "@" not in clean_email:
        raise ValueError("invalid invite email")

    raw = secrets.token_urlsafe(32)
    record = Invite(
        project_id=project.id,
        email=clean_email,
        token_hash=_hash_invite_token(raw),
        invited_by_user_id=invited_by.id,
        expires_at=utcnow() + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, raw


def accept_invite(session: Session, *, token: str, user: User) -> tuple[Project, ProjectMember]:
    """Consume an invite token and add ``user`` to the project as a member.

    If ``user`` is already a member (e.g. they accepted a different invite
    earlier), the invite is still marked used but no duplicate membership
    row is created — the existing role is preserved so accepting an invite
    doesn't accidentally downgrade an owner.
    """

    if not token:
        raise InviteInvalid()
    digest = _hash_invite_token(token)
    invite = session.scalar(select(Invite).where(Invite.token_hash == digest))
    if invite is None:
        raise InviteInvalid()
    if invite.accepted_at is not None:
        raise InviteInvalid()
    if invite.expires_at.replace(tzinfo=UTC) < utcnow():
        raise InviteInvalid()

    project = session.get(Project, invite.project_id)
    if project is None:
        raise InviteInvalid()

    existing = get_membership(session, project.id, user.id)
    if existing is not None:
        invite.accepted_at = utcnow()
        session.commit()
        return project, existing

    member = ProjectMember(project_id=project.id, user_id=user.id, role=ROLE_MEMBER)
    session.add(member)
    invite.accepted_at = utcnow()
    session.commit()
    session.refresh(member)
    return project, member


def valid_role(role: str) -> bool:
    return role in _ROLES


# ---------------------------------------------------------------------------
# Backfill — one-shot migration to scope existing pads/conversations to
# per-user "Personal" projects. Idempotent; safe to call on every startup.
# ---------------------------------------------------------------------------
PERSONAL_PROJECT_NAME = "Personal"


def _find_personal_project(session: Session, user_id: str) -> Project | None:
    """Return the user's existing 'Personal' project if any, else None."""

    return session.scalar(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(Project.name == PERSONAL_PROJECT_NAME)
        .where(ProjectMember.user_id == user_id)
        .where(ProjectMember.role == ROLE_OWNER)
        .where(Project.created_by_user_id == user_id)
    )


def ensure_personal_project(session: Session, user_id: str) -> Project:
    """Find-or-create a 'Personal' project owned by ``user_id``.

    Does NOT commit — caller is expected to wrap in their own
    transaction (the backfill does one commit at the end).
    """

    existing = _find_personal_project(session, user_id)
    if existing is not None:
        return existing

    project = Project(name=PERSONAL_PROJECT_NAME, created_by_user_id=user_id)
    session.add(project)
    session.flush()  # need project.id
    session.add(ProjectMember(project_id=project.id, user_id=user_id, role=ROLE_OWNER))
    session.flush()
    return project


def backfill_personal_projects(session: Session) -> dict[str, int]:
    """Assign every pre-existing conversation+artifact to a Personal project.

    For each distinct ``owner_id`` that has conversations without a
    ``project_id``, find-or-create a ``Personal`` project owned by that
    user and set ``Conversation.project_id`` for their rows. Artifacts
    inherit ``project_id`` from their conversation.

    Orphan owners (owner_id points at a user that no longer exists) and
    orphan conversations (owner_id NULL) are skipped: the backfill cannot
    safely attribute them, and leaving them with NULL ``project_id``
    keeps them inaccessible via the library without data loss.

    Idempotent: a second call is a no-op because the predicate selects
    only rows whose ``project_id`` is still NULL.

    Returns a summary dict with ``projects_created``, ``conversations``,
    ``artifacts``.
    """

    from .core import Artifact, Conversation  # local import to avoid cycles

    orphan_owner_ids = list(
        session.scalars(
            select(Conversation.owner_id)
            .where(Conversation.project_id.is_(None))
            .where(Conversation.owner_id.isnot(None))
            .distinct()
        )
    )

    projects_created = 0
    conversations_migrated = 0
    artifacts_migrated = 0
    for owner_id in orphan_owner_ids:
        user = session.get(User, owner_id)
        if user is None:
            log.warning(
                "backfill: skipping orphan owner_id=%s (user no longer exists)", owner_id
            )
            continue

        had_personal = _find_personal_project(session, owner_id) is not None
        project = ensure_personal_project(session, owner_id)
        if not had_personal:
            projects_created += 1

        # Capture conversation ids for this owner before the bulk UPDATE
        # so we can scope the artifact UPDATE to them. This avoids a
        # correlated subquery and sidesteps the stale ORM identity-map
        # problem that would otherwise keep ``session.get(Conversation, _)``
        # returning ``project_id=None`` after the update.
        conv_ids = list(
            session.scalars(
                select(Conversation.id)
                .where(Conversation.owner_id == owner_id)
                .where(Conversation.project_id.is_(None))
            )
        )
        if not conv_ids:
            continue

        session.execute(
            update(Conversation)
            .where(Conversation.id.in_(conv_ids))
            .values(project_id=project.id)
        )
        conversations_migrated += len(conv_ids)

        art_result = session.execute(
            update(Artifact)
            .where(Artifact.conversation_id.in_(conv_ids))
            .where(Artifact.project_id.is_(None))
            .values(project_id=project.id)
        )
        artifacts_migrated += art_result.rowcount or 0

    if projects_created or conversations_migrated or artifacts_migrated:
        session.commit()
        log.info(
            "backfill: created %d Personal projects, migrated %d conversations, %d artifacts",
            projects_created,
            conversations_migrated,
            artifacts_migrated,
        )
    else:
        # Nothing changed — avoid a no-op commit.
        pass

    return {
        "projects_created": projects_created,
        "conversations": conversations_migrated,
        "artifacts": artifacts_migrated,
    }
