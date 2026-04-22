from __future__ import annotations

import json
import re
import tempfile
from html import escape as html_escape
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from markdown import markdown
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, func, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .schemas import (
    ArtifactListItem,
    ArtifactRead,
    ArtifactStatus,
    ArtifactType,
    ArtifactUpdateRequest,
    CanvasToolCall,
    CitationRead,
    ContentType,
    ConversationDetail,
    ConversationSummary,
    LibraryArtifactCreateRequest,
    MessageRead,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Settings(BaseSettings):
    app_name: str = "Workpad AI"
    api_prefix: str = "/api"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_model: str = "gpt-5.4"
    openai_reasoning_effort: str = "medium"
    github_default_token: str = ""
    app_database_url: str = "sqlite:///./data/workpad.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://host.docker.internal:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return ["http://localhost:3000", "http://127.0.0.1:3000", "http://host.docker.internal:3000"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None, index=True)
    # project_id is nullable at the schema level so the backfill migration
    # can run against existing rows; service-layer code enforces that
    # newly-created conversations always carry one.
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None, index=True)
    title: Mapped[str] = mapped_column(String(240), default="New workpad")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    # Denormalized from Conversation.project_id so library queries don't
    # need a JOIN. Backfill keeps this in sync for existing rows; new pads
    # inherit project_id from their conversation at create time.
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None, index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(32), default=ContentType.MARKDOWN.value)
    spec_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    artifact_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), default=ArtifactStatus.DRAFT.value)
    summary: Mapped[str] = mapped_column(Text, default="")
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    origin_conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="artifacts")
    versions: Mapped[list["ArtifactVersion"]] = relationship(back_populates="artifact", cascade="all, delete-orphan")


class SpecSource(Base):
    __tablename__ = "spec_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    artifact: Mapped[Artifact] = relationship()


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    anchor: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    target: Mapped[dict] = mapped_column(JSON)
    resolved_state: Mapped[str] = mapped_column(String(16), default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    last_observed: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    artifact: Mapped[Artifact] = relationship()


class RepoCache(Base):
    __tablename__ = "repo_cache"
    __table_args__ = (
        UniqueConstraint("repo", "ref", "path", name="uq_repo_cache_repo_ref_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    repo: Mapped[str] = mapped_column(String(240), index=True)
    ref: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(1024))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_hash: Mapped[str] = mapped_column(String(128))
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    artifact: Mapped[Artifact] = relationship(back_populates="versions")


@lru_cache
def get_engine():
    settings = get_settings()
    database_url = settings.app_database_url
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url)


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    # Import so the auth and projects tables are registered on
    # Base.metadata before create_all runs. Keeping these imports here
    # avoids a circular import at module load time (both modules import
    # from core).
    from . import auth as _auth  # noqa: F401
    from . import projects as _projects  # noqa: F401
    from .projects import backfill_personal_projects

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_conversation_schema(engine)
    _ensure_artifact_schema(engine)

    # One-shot backfill for pre-projects data. Idempotent — selects only
    # rows whose project_id is still NULL, so it's a no-op on clean DBs
    # and after the first successful run.
    factory = get_session_factory()
    with factory() as session:
        backfill_personal_projects(session)


def _ensure_conversation_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info('conversations')").fetchall()
        }
        if "archived_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE conversations ADD COLUMN archived_at DATETIME")
        if "owner_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE conversations ADD COLUMN owner_id VARCHAR(36)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_conversations_owner_id ON conversations(owner_id)"
            )
        if "project_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE conversations ADD COLUMN project_id VARCHAR(36)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_conversations_project_id ON conversations(project_id)"
            )


def _ensure_artifact_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info('artifacts')").fetchall()
        }
        if "spec_type" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN spec_type VARCHAR(32)")
        if "artifact_type" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN artifact_type VARCHAR(32)")
        if "status" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'draft'")
        if "summary" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
        if "last_opened_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN last_opened_at DATETIME")
        if "origin_conversation_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN origin_conversation_id VARCHAR(36)")
        if "project_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE artifacts ADD COLUMN project_id VARCHAR(36)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_artifacts_project_id ON artifacts(project_id)"
            )
        connection.exec_driver_sql(
            "UPDATE artifacts SET artifact_type = spec_type "
            "WHERE artifact_type IS NULL AND spec_type IS NOT NULL"
        )
        connection.exec_driver_sql(
            "UPDATE artifacts SET origin_conversation_id = conversation_id "
            "WHERE origin_conversation_id IS NULL"
        )
        connection.exec_driver_sql(
            "UPDATE artifacts SET status = 'active' "
            "WHERE spec_type IS NOT NULL AND (status IS NULL OR status = '' OR status = 'draft')"
        )


def serialize_conversation(conversation: Conversation, session: Session) -> ConversationSummary:
    last_message = session.scalar(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.desc()).limit(1)
    )
    artifact_count = session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.conversation_id == conversation.id)
    ) or 0
    preview = None
    if last_message:
        preview = last_message.content[:120]
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_preview=preview,
        artifact_count=int(artifact_count),
        archived_at=conversation.archived_at,
    )


def serialize_message(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


def serialize_citation(citation: Citation) -> CitationRead:
    return CitationRead(
        id=citation.id,
        artifact_id=citation.artifact_id,
        anchor=citation.anchor,
        kind=citation.kind,
        target=citation.target or {},
        resolved_state=citation.resolved_state,
        last_checked_at=citation.last_checked_at,
        last_observed=citation.last_observed,
    )


def _artifact_type_value(artifact: Artifact) -> str | None:
    return artifact.artifact_type or artifact.spec_type


def _artifact_status_value(artifact: Artifact) -> str:
    if artifact.status:
        return artifact.status
    if artifact.spec_type:
        return ArtifactStatus.ACTIVE.value
    return ArtifactStatus.DRAFT.value


def serialize_artifact(artifact: Artifact, session: Session | None = None) -> ArtifactRead:
    citations: list[CitationRead] = []
    if session is not None:
        rows = session.scalars(
            select(Citation).where(Citation.artifact_id == artifact.id).order_by(Citation.created_at.asc())
        ).all()
        citations = [serialize_citation(row) for row in rows]
    return ArtifactRead(
        id=artifact.id,
        conversation_id=artifact.conversation_id,
        origin_conversation_id=artifact.origin_conversation_id,
        title=artifact.title,
        content=artifact.content,
        content_type=artifact.content_type,
        version=artifact.version,
        artifact_type=_artifact_type_value(artifact),
        updated_at=artifact.updated_at,
        last_opened_at=artifact.last_opened_at,
        summary=artifact.summary or "",
        status=_artifact_status_value(artifact),
        spec_type=artifact.spec_type,
        citations=citations,
    )


def serialize_artifact_list_item(artifact: Artifact) -> ArtifactListItem:
    return ArtifactListItem(
        id=artifact.id,
        conversation_id=artifact.conversation_id,
        origin_conversation_id=artifact.origin_conversation_id,
        title=artifact.title,
        content_type=artifact.content_type,
        version=artifact.version,
        artifact_type=_artifact_type_value(artifact),
        updated_at=artifact.updated_at,
        last_opened_at=artifact.last_opened_at,
        summary=artifact.summary or "",
        status=_artifact_status_value(artifact),
        spec_type=artifact.spec_type,
    )


def list_conversations(
    session: Session,
    *,
    include_archived: bool = False,
    project_id: str,
) -> list[ConversationSummary]:
    """List conversations in a project.

    Callers must pass a ``project_id``; membership is enforced by the
    endpoint layer before this function is reached.
    """

    query = (
        select(Conversation)
        .where(Conversation.project_id == project_id)
        .order_by(Conversation.updated_at.desc())
    )
    if not include_archived:
        query = query.where(Conversation.archived_at.is_(None))
    conversations = session.scalars(query).all()
    return [serialize_conversation(item, session) for item in conversations]


def list_library_artifacts(
    session: Session,
    *,
    artifact_type: str | None = None,
    status: str | None = None,
    query_text: str | None = None,
    limit: int = 100,
    project_id: str,
) -> list[ArtifactListItem]:
    stmt = select(Artifact).where(Artifact.project_id == project_id)

    if artifact_type:
        stmt = stmt.where(
            or_(
                Artifact.artifact_type == artifact_type,
                Artifact.spec_type == artifact_type,
            )
        )
    if status:
        stmt = stmt.where(Artifact.status == status)
    if query_text:
        pattern = f"%{query_text.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Artifact.title).like(pattern),
                func.lower(Artifact.content).like(pattern),
                func.lower(Artifact.summary).like(pattern),
            )
        )

    capped_limit = min(max(limit, 1), 200)
    artifacts = session.scalars(stmt.order_by(Artifact.updated_at.desc()).limit(capped_limit)).all()
    return [serialize_artifact_list_item(item) for item in artifacts]


def archive_conversation(session: Session, conversation_id: str) -> Conversation:
    conversation = get_conversation_or_404(session, conversation_id)
    if conversation.archived_at is None:
        conversation.archived_at = utcnow()
        conversation.updated_at = utcnow()
        session.commit()
        session.refresh(conversation)
    return conversation


def unarchive_conversation(session: Session, conversation_id: str) -> Conversation:
    conversation = get_conversation_or_404(session, conversation_id)
    if conversation.archived_at is not None:
        conversation.archived_at = None
        conversation.updated_at = utcnow()
        session.commit()
        session.refresh(conversation)
    return conversation


def delete_conversation(session: Session, conversation_id: str) -> None:
    conversation = get_conversation_or_404(session, conversation_id)
    session.delete(conversation)
    session.commit()


def create_conversation(
    session: Session,
    seed_title: str | None = None,
    *,
    project_id: str,
    owner_id: str | None = None,
) -> Conversation:
    """Create a new conversation inside a project.

    ``owner_id`` is retained on the row as a legacy trace (it still maps
    to the creator) but authorization is driven by ``project_id`` and
    project membership, not by owner_id.
    """

    title = (seed_title or "New workpad").strip() or "New workpad"
    conversation = Conversation(title=title[:240], owner_id=owner_id, project_id=project_id)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def get_conversation_or_404(
    session: Session,
    conversation_id: str,
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")
    return conversation


def get_conversation_detail(
    session: Session,
    conversation_id: str,
) -> ConversationDetail:
    conversation = get_conversation_or_404(session, conversation_id)
    messages = session.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())).all()
    artifacts = session.scalars(select(Artifact).where(Artifact.conversation_id == conversation_id).order_by(Artifact.updated_at.desc())).all()
    active_artifact_id = artifacts[0].id if artifacts else None
    return ConversationDetail(
        conversation=serialize_conversation(conversation, session),
        messages=[serialize_message(message) for message in messages],
        artifacts=[serialize_artifact(artifact, session) for artifact in artifacts],
        active_artifact_id=active_artifact_id,
    )


def add_message(session: Session, conversation: Conversation, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role=role, content=content)
    session.add(message)
    if conversation.title == "New workpad" and role == "user":
        conversation.title = content.strip().splitlines()[0][:80]
    conversation.updated_at = utcnow()
    session.commit()
    session.refresh(message)
    session.refresh(conversation)
    return message


def get_last_message_by_role(session: Session, conversation: Conversation, role: str) -> Message | None:
    return session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == role)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def delete_messages_after(session: Session, conversation: Conversation, reference: Message) -> None:
    trailing = session.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.created_at > reference.created_at,
        )
        .order_by(Message.created_at.asc())
    ).all()
    for message in trailing:
        if message.id == reference.id:
            continue
        session.delete(message)
    if trailing:
        conversation.updated_at = utcnow()
        session.commit()
        session.refresh(conversation)


def prepare_regenerate(session: Session, conversation: Conversation) -> Message:
    last_user = get_last_message_by_role(session, conversation, "user")
    if last_user is None:
        raise ValueError("No user message to regenerate from.")
    delete_messages_after(session, conversation, last_user)
    return last_user


def apply_edit_to_last_user(session: Session, conversation: Conversation, new_content: str) -> Message:
    last_user = get_last_message_by_role(session, conversation, "user")
    if last_user is None:
        raise ValueError("No user message to edit.")
    cleaned = new_content.strip()
    if not cleaned:
        raise ValueError("Edited message cannot be empty.")
    delete_messages_after(session, conversation, last_user)
    last_user.content = cleaned
    conversation.updated_at = utcnow()
    session.commit()
    session.refresh(last_user)
    session.refresh(conversation)
    return last_user


@dataclass
class ArtifactMutationResult:
    artifact: Artifact
    summary: str
    action: str


def _record_artifact_version(session: Session, artifact: Artifact, summary: str) -> None:
    session.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=artifact.version,
            title=artifact.title,
            content=artifact.content,
            content_type=artifact.content_type,
            summary=summary[:500],
        )
    )


def _apply_patches(content: str, tool_call: CanvasToolCall) -> str:
    next_content = content
    for patch in tool_call.patches or []:
        if patch.search not in next_content:
            if patch.allow_missing:
                continue
            raise ValueError(f"Could not find patch target: {patch.search[:80]}")
        count = -1 if patch.replace_all else 1
        next_content = next_content.replace(patch.search, patch.replace, count)
    return next_content


def apply_canvas_tool(
    session: Session,
    conversation: Conversation,
    tool_call: CanvasToolCall,
    current_artifact_id: str | None = None,
) -> ArtifactMutationResult:
    artifact: Artifact | None = None
    if current_artifact_id:
        artifact = session.get(Artifact, current_artifact_id)

    if artifact is None and tool_call.action != "create":
        artifact = session.scalar(
            select(Artifact).where(Artifact.conversation_id == conversation.id).order_by(Artifact.updated_at.desc()).limit(1)
        )

    if artifact is None:
        artifact = Artifact(
            conversation_id=conversation.id,
            origin_conversation_id=conversation.id,
            title=tool_call.title,
            content="",
            content_type=tool_call.content_type.value,
            version=0,
        )
        session.add(artifact)
        session.flush()

    current_content = artifact.content or ""
    if tool_call.action == "patch":
        next_content = _apply_patches(current_content, tool_call)
    else:
        next_content = tool_call.content or ""

    artifact.title = tool_call.title[:240]
    artifact.content = next_content
    artifact.content_type = tool_call.content_type.value
    artifact.artifact_type = artifact.artifact_type or artifact.spec_type
    artifact.summary = artifact.summary or ""
    artifact.status = artifact.status or ArtifactStatus.DRAFT.value
    artifact.origin_conversation_id = artifact.origin_conversation_id or conversation.id
    artifact.version += 1
    artifact.updated_at = utcnow()
    conversation.updated_at = utcnow()

    _record_artifact_version(session, artifact, tool_call.summary)
    session.commit()
    session.refresh(artifact)
    session.refresh(conversation)

    return ArtifactMutationResult(artifact=artifact, summary=tool_call.summary, action=tool_call.action)


def update_artifact_manually(
    session: Session,
    artifact_id: str,
    payload: ArtifactUpdateRequest,
) -> ArtifactRead:
    artifact = get_artifact_or_404(session, artifact_id)
    if payload.expected_version and artifact.version != payload.expected_version:
        raise ValueError("Artifact version mismatch")

    artifact.title = payload.title[:240]
    artifact.content = payload.content
    artifact.content_type = payload.content_type.value
    if payload.artifact_type is not None:
        artifact.artifact_type = payload.artifact_type.value
        artifact.spec_type = payload.artifact_type.value if payload.artifact_type == ArtifactType.RFC else None
    elif artifact.artifact_type is None and artifact.spec_type is not None:
        artifact.artifact_type = artifact.spec_type
    if payload.status is not None:
        artifact.status = payload.status.value
    elif not artifact.status:
        artifact.status = ArtifactStatus.DRAFT.value
    if payload.summary is not None:
        artifact.summary = payload.summary.strip()
    elif artifact.summary is None:
        artifact.summary = ""
    artifact.origin_conversation_id = artifact.origin_conversation_id or artifact.conversation_id
    artifact.version += 1
    artifact.updated_at = utcnow()
    artifact.conversation.updated_at = utcnow()
    _record_artifact_version(session, artifact, "Manual edit from the workpad editor.")
    session.commit()
    session.refresh(artifact)
    return serialize_artifact(artifact, session)


def create_library_artifact(
    session: Session,
    payload: LibraryArtifactCreateRequest,
    *,
    project_id: str,
    owner_id: str | None = None,
) -> ArtifactRead:
    """Create a library-owned artifact under a project.

    If ``payload.conversation_id`` is given, the artifact attaches to
    that existing conversation; the caller must have verified that
    conversation's project membership before calling this. Otherwise a
    backing conversation is created inside the same project.
    """

    if payload.conversation_id:
        conversation = get_conversation_or_404(session, payload.conversation_id)
    else:
        conversation = Conversation(
            title=payload.title[:240], owner_id=owner_id, project_id=project_id
        )
        session.add(conversation)
        session.flush()

    artifact = Artifact(
        conversation_id=conversation.id,
        origin_conversation_id=conversation.id,
        project_id=project_id,
        title=payload.title[:240],
        content=payload.content,
        content_type=payload.content_type.value,
        spec_type=payload.artifact_type.value if payload.artifact_type == ArtifactType.RFC else None,
        artifact_type=payload.artifact_type.value,
        status=payload.status.value,
        summary=payload.summary.strip(),
        version=1,
    )
    session.add(artifact)
    session.flush()

    _record_artifact_version(session, artifact, "Created from the artifact library.")
    conversation.updated_at = utcnow()
    session.commit()
    session.refresh(artifact)
    return serialize_artifact(artifact, session)


def get_artifact_or_404(
    session: Session,
    artifact_id: str,
) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise ValueError("Artifact not found")
    return artifact


def get_artifact_detail(
    session: Session,
    artifact_id: str,
    *,
    mark_opened: bool = False,
) -> ArtifactRead:
    artifact = get_artifact_or_404(session, artifact_id)
    if mark_opened:
        artifact.last_opened_at = utcnow()
        session.commit()
        session.refresh(artifact)
    return serialize_artifact(artifact, session)


def get_artifact_diff(
    session: Session,
    artifact_id: str,
    *,
    from_version: int | None = None,
    to_version: int | None = None,
) -> dict[str, Any]:
    """Unified diff between two snapshots of an artifact.

    Defaults: diff the most recent two versions. Used by the editor's "Diff"
    mode so the user can see exactly what an AI edit changed.
    """

    import difflib

    artifact = get_artifact_or_404(session, artifact_id)

    versions = list(
        session.scalars(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
            .order_by(ArtifactVersion.version.asc())
        ).all()
    )

    if to_version is None:
        to_version = versions[-1].version if versions else artifact.version
    if from_version is None:
        # Default: previous version if available, else 0 (empty → current).
        prev_candidates = [v.version for v in versions if v.version < to_version]
        from_version = prev_candidates[-1] if prev_candidates else 0

    def body_for(version_num: int) -> tuple[str, str]:
        if version_num <= 0:
            return ("", "")
        match = next((v for v in versions if v.version == version_num), None)
        if match is not None:
            return (match.content or "", match.title or "")
        if artifact.version == version_num:
            return (artifact.content or "", artifact.title or "")
        raise ValueError(f"Artifact version {version_num} not found")

    from_content, from_title = body_for(from_version)
    to_content, to_title = body_for(to_version)

    from_lines = from_content.splitlines(keepends=False)
    to_lines = to_content.splitlines(keepends=False)
    unified = "\n".join(
        difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            lineterm="",
        )
    )

    added = sum(
        1
        for line in unified.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1
        for line in unified.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )

    return {
        "artifact_id": artifact_id,
        "from_version": from_version,
        "to_version": to_version,
        "from_title": from_title,
        "to_title": to_title,
        "unified_diff": unified,
        "added_lines": added,
        "removed_lines": removed,
        "available_versions": [v.version for v in versions] + (
            [artifact.version] if artifact.version not in [v.version for v in versions] else []
        ),
    }


def _safe_filename(name: str) -> str:
    base = re.sub(r"[^\w\s.-]", "", name).strip()
    base = re.sub(r"\s+", "_", base)
    return base or "workpad_export"


_PREVIEW_MD_EXTENSIONS = [
    "extra",
    "sane_lists",
    "smarty",
    "admonition",
    "pymdownx.tasklist",
    "pymdownx.tilde",
    "pymdownx.superfences",
    "pymdownx.betterem",
]

_PREVIEW_MD_EXTENSION_CONFIGS = {
    "pymdownx.tasklist": {"custom_checkbox": True, "clickable_checkbox": False},
}


_PREVIEW_STYLESHEET = """
@page { size: Letter; margin: 0.75in; }
html { font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11pt; color: #1f2937; }
body { margin: 0; }
.doc { max-width: 100%; line-height: 1.65; }
.doc > *:first-child { margin-top: 0; }
.doc h1, .doc h2, .doc h3, .doc h4 { color: #0f172a; font-weight: 600; line-height: 1.25; }
.doc h1 { font-size: 20pt; margin: 0.35in 0 0.12in; }
.doc h2 { font-size: 16pt; margin: 0.28in 0 0.1in; }
.doc h3 { font-size: 13pt; margin: 0.22in 0 0.08in; }
.doc h4 { font-size: 11.5pt; margin: 0.18in 0 0.06in; }
.doc p { margin: 0.09in 0; }
.doc ul, .doc ol { margin: 0.09in 0; padding-left: 0.35in; }
.doc li { margin: 0.03in 0; }
.doc li > p { margin: 0.04in 0; }
.doc blockquote { border-left: 2px solid #cbd5e1; color: #475569; margin: 0.12in 0; padding: 0.02in 0 0.02in 0.18in; }
.doc hr { border: none; border-top: 1px solid #e2e8f0; margin: 0.2in 0; }
.doc a { color: #1d4ed8; text-decoration: underline; }
.doc code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 9.5pt;
  background: #f1f5f9;
  color: #4338ca;
  padding: 0.02in 0.05in;
  border-radius: 3px;
}
.doc pre {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.12in 0.16in;
  overflow-x: auto;
  margin: 0.12in 0;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 9.5pt;
  line-height: 1.5;
  color: #1e293b;
}
.doc pre code { background: transparent; color: inherit; padding: 0; border-radius: 0; font-size: inherit; }
.doc table { border-collapse: collapse; margin: 0.12in 0; width: 100%; font-size: 10pt; }
.doc th, .doc td { border: 1px solid #e2e8f0; padding: 0.04in 0.08in; text-align: left; vertical-align: top; }
.doc th { background: #f8fafc; font-weight: 600; color: #0f172a; }
.doc img { max-width: 100%; height: auto; border-radius: 8px; margin: 0.12in 0; }
.doc-diagram { margin: 0.18in 0; padding: 0.1in; border: 1px solid #e2e8f0; border-radius: 10px; background: #fafafa; text-align: center; page-break-inside: avoid; break-inside: avoid; }
.doc-diagram svg, .doc-diagram img { max-width: 100%; max-height: 8in; width: auto; height: auto; }
.doc strong { font-weight: 600; color: #0f172a; }
.doc em { font-style: italic; }
.doc ul.task-list { list-style: none; padding-left: 0.12in; }
.doc ul.task-list li { padding-left: 0.22in; position: relative; }
.doc ul.task-list li input[type="checkbox"] { position: absolute; left: 0; top: 0.06in; }
.workpad-citation {
  display: inline-block;
  padding: 0 0.06in;
  border-radius: 999px;
  border: 1px solid #c7d9fb;
  background: #eef5ff;
  color: #1d4ed8;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 9pt;
  text-decoration: none;
  line-height: 1.4;
  white-space: nowrap;
}
.workpad-citation--stale { background: #fff7ed; border-color: #fed7aa; color: #9a3412; }
.workpad-citation--missing { background: #fef2f2; border-color: #fecaca; color: #991b1b; text-decoration: line-through; }
"""


def _citation_pill_classes(citation: Citation | None) -> str:
    base = "workpad-citation"
    state = (getattr(citation, "resolved_state", None) or "live").lower() if citation else "live"
    if state == "stale":
        return f"{base} workpad-citation--stale"
    if state == "missing":
        return f"{base} workpad-citation--missing"
    return base


def _citation_pill_html(anchor: str, citation: Citation | None) -> str:
    if citation is None:
        label = anchor
        url = None
    else:
        label = _citation_footnote_label(citation)
        url = _citation_github_url(citation)
    classes = _citation_pill_classes(citation)
    label_html = html_escape(label or anchor)
    if url:
        return f'<a class="{classes}" href="{html_escape(url)}">{label_html}</a>'
    return f'<span class="{classes}">{label_html}</span>'


def _render_markdown_with_citation_pills(
    content: str, citations_by_anchor: dict[str, Citation]
) -> str:
    """Inline citation tokens as HTML pill spans, matching the live preview.

    Unknown anchors are left as literal tokens; markdown parsing of the rest
    of the document still runs because we emit raw inline HTML that
    python-markdown preserves via the `md_in_html` / `extra` extension.
    """

    def _replace(match: re.Match[str]) -> str:
        anchor = match.group(1).lower()
        citation = citations_by_anchor.get(anchor)
        if citation is None:
            return match.group(0)
        return _citation_pill_html(anchor, citation)

    return _CITATION_TOKEN_RE.sub(_replace, content)


def _wrap_preview_document(inner_html: str, title: str) -> str:
    safe_title = html_escape(title or "Untitled")
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8" />'
        f"<title>{safe_title}</title>"
        f"<style>{_PREVIEW_STYLESHEET}</style>"
        f"</head><body>{inner_html}</body></html>"
    )


def _render_preview_html(
    artifact: Artifact,
    markdown_body: str,
    citations_by_anchor: dict[str, Citation],
    *,
    full_document: bool,
) -> str:
    if artifact.content_type == ContentType.MARKDOWN.value:
        source = _render_markdown_with_citation_pills(markdown_body, citations_by_anchor)
        body_html = markdown(
            source,
            extensions=_PREVIEW_MD_EXTENSIONS,
            extension_configs=_PREVIEW_MD_EXTENSION_CONFIGS,
            output_format="html",
        )
    else:
        body_html = f"<pre><code>{html_escape(artifact.content)}</code></pre>"

    inner = f'<article class="doc">{body_html}</article>'
    if not full_document:
        return inner
    return _wrap_preview_document(inner, artifact.title or "")


def _build_docx_from_html(inner_html: str, title: str) -> bytes:
    import pypandoc

    del title  # The document body already contains its own heading; passing
    # a metadata title would make Pandoc render it a second time above.

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        pypandoc.convert_text(
            inner_html,
            to="docx",
            format="html",
            outputfile=tmp_path,
            extra_args=["--standalone"],
        )
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _build_pdf_from_html(inner_html: str, title: str) -> bytes:
    from weasyprint import HTML  # type: ignore[import-untyped]

    return HTML(string=_wrap_preview_document(inner_html, title)).write_pdf()


def _build_docx_bytes(
    artifact: Artifact,
    markdown_body: str,
    citations_by_anchor: dict[str, Citation],
) -> bytes:
    inner_html = _render_preview_html(
        artifact, markdown_body, citations_by_anchor, full_document=False
    )
    return _build_docx_from_html(inner_html, artifact.title or "")


def _build_pdf_bytes(
    artifact: Artifact,
    markdown_body: str,
    citations_by_anchor: dict[str, Citation],
) -> bytes:
    inner_html = _render_preview_html(
        artifact, markdown_body, citations_by_anchor, full_document=False
    )
    return _build_pdf_from_html(inner_html, artifact.title or "")


_CITATION_TOKEN_RE = re.compile(r"\[\[cite:([a-z0-9_-]{2,32})\]\]", re.IGNORECASE)


def _citation_footnote_id(anchor: str) -> str:
    return f"cite-{anchor.lower()}"


def _citation_github_url(citation: Citation) -> str | None:
    target = citation.target or {}
    observed = citation.last_observed or {}
    kind = citation.kind
    if kind == "repo_range":
        repo = str(target.get("repo") or "")
        path = str(target.get("path") or "")
        ref = str(observed.get("at_ref") or target.get("ref_at_draft") or "")
        suggested = observed.get("suggested_range") if isinstance(observed.get("suggested_range"), dict) else None
        ls = (suggested or {}).get("line_start") or target.get("line_start")
        le = (suggested or {}).get("line_end") or target.get("line_end")
        if not (repo and path and ref):
            return None
        anchor_frag = f"#L{ls}-L{le}" if ls and le else ""
        return f"https://github.com/{repo}/blob/{ref}/{path}{anchor_frag}"
    if kind == "repo_pr":
        url = observed.get("html_url")
        if isinstance(url, str) and url:
            return url
        repo = str(target.get("repo") or "")
        number = target.get("number")
        if repo and isinstance(number, int):
            return f"https://github.com/{repo}/pull/{number}"
    if kind == "repo_commit":
        url = observed.get("html_url")
        if isinstance(url, str) and url:
            return url
        repo = str(target.get("repo") or "")
        sha = str(target.get("sha") or "")
        if repo and sha:
            return f"https://github.com/{repo}/commit/{sha}"
    return None


def _citation_footnote_label(citation: Citation) -> str:
    target = citation.target or {}
    kind = citation.kind
    if kind == "repo_range":
        repo = str(target.get("repo") or "")
        path = str(target.get("path") or "")
        ls = target.get("line_start")
        le = target.get("line_end")
        suffix = f"#L{ls}-L{le}" if isinstance(ls, int) and isinstance(le, int) else ""
        return f"{repo} · {path}{suffix}".strip(" ·")
    if kind == "repo_pr":
        repo = str(target.get("repo") or "")
        number = target.get("number")
        title = str(target.get("title_at_draft") or "")
        return f"{repo} · PR #{number} {title}".rstrip()
    if kind == "repo_commit":
        repo = str(target.get("repo") or "")
        sha = str(target.get("sha") or "")
        return f"{repo} · commit {sha[:7]}"
    if kind == "transcript_range":
        start = str(target.get("start") or "")
        end = str(target.get("end") or "")
        return f"transcript {start}–{end}".strip("–")
    return citation.anchor


def _render_markdown_with_footnotes(
    content: str, citations_by_anchor: dict[str, Citation]
) -> str:
    """Rewrite [[cite:<anchor>]] tokens as pandoc footnote refs + emit a footer.

    Anchors that don't match a Citation row are left untouched so the raw
    token survives; missing metadata never silently rewrites content.
    """

    if not citations_by_anchor:
        return content

    used: list[str] = []
    seen: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        anchor = match.group(1).lower()
        if anchor not in citations_by_anchor:
            return match.group(0)
        if anchor not in seen:
            used.append(anchor)
            seen.add(anchor)
        return f"[^{_citation_footnote_id(anchor)}]"

    rewritten = _CITATION_TOKEN_RE.sub(_replace, content)
    if not used:
        return content

    footnotes = ["\n\n---\n"]
    for anchor in used:
        citation = citations_by_anchor[anchor]
        label = _citation_footnote_label(citation)
        url = _citation_github_url(citation)
        line = f"[^{_citation_footnote_id(anchor)}]: {label}"
        if url:
            line += f" <{url}>"
        footnotes.append(line)
    return rewritten + "\n".join(footnotes) + "\n"


def export_artifact(session: Session, artifact_id: str, export_format: str) -> tuple[bytes | str, str, str]:
    artifact = get_artifact_or_404(session, artifact_id)
    safe_name = _safe_filename(artifact.title)

    citations_by_anchor: dict[str, Citation] = {}
    if artifact.spec_type and artifact.content_type == ContentType.MARKDOWN.value:
        citation_rows = session.scalars(
            select(Citation).where(Citation.artifact_id == artifact.id)
        ).all()
        citations_by_anchor = {row.anchor: row for row in citation_rows}

    if export_format in {"html", "docx", "pdf"}:
        if export_format == "html":
            body = _render_preview_html(
                artifact, artifact.content, citations_by_anchor, full_document=True
            )
            return body, "text/html; charset=utf-8", f"{safe_name}.html"
        if export_format == "docx":
            return (
                _build_docx_bytes(artifact, artifact.content, citations_by_anchor),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                f"{safe_name}.docx",
            )
        return (
            _build_pdf_bytes(artifact, artifact.content, citations_by_anchor),
            "application/pdf",
            f"{safe_name}.pdf",
        )

    # Plain-text / raw-markdown paths keep footnote-style citation emission so
    # readers that don't render inline HTML still see the citation metadata.
    if citations_by_anchor and artifact.content_type == ContentType.MARKDOWN.value:
        text_body = _render_markdown_with_footnotes(artifact.content, citations_by_anchor)
    else:
        text_body = artifact.content

    if export_format == "text":
        return text_body, "text/plain; charset=utf-8", f"{safe_name}.txt"
    return text_body, "text/markdown; charset=utf-8", f"{safe_name}.md"


def export_artifact_from_rendered_html(
    session: Session,
    artifact_id: str,
    export_format: str,
    inner_html: str,
) -> tuple[bytes | str, str, str]:
    """Convert client-rendered HTML (with mermaid/KaTeX SVGs baked in) to the
    requested binary format. The caller is responsible for producing HTML that
    matches the live preview; the backend only wraps it in the preview
    stylesheet and hands it to WeasyPrint / Pandoc.
    """

    artifact = get_artifact_or_404(session, artifact_id)
    safe_name = _safe_filename(artifact.title)
    title = artifact.title or ""
    wrapped = f'<article class="doc">{inner_html}</article>'

    if export_format == "docx":
        return (
            _build_docx_from_html(wrapped, title),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{safe_name}.docx",
        )
    if export_format == "pdf":
        return (
            _build_pdf_from_html(wrapped, title),
            "application/pdf",
            f"{safe_name}.pdf",
        )
    if export_format == "html":
        return (
            _wrap_preview_document(wrapped, title),
            "text/html; charset=utf-8",
            f"{safe_name}.html",
        )
    raise ValueError(f"unsupported rendered export format: {export_format}")


def current_artifact_id_from_payload(payload: Any) -> str | None:
    if not payload:
        return None
    artifact_id = getattr(payload, "id", None)
    if artifact_id:
        return artifact_id
    if isinstance(payload, dict):
        return payload.get("id")
    return None


def build_response_input(session: Session, conversation: Conversation) -> list[dict[str, str]]:
    history = session.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.asc())).all()
    return [{"role": message.role, "content": message.content} for message in history]


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True)
