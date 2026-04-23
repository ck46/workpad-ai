from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ContentType(StrEnum):
    MARKDOWN = "markdown"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    HTML = "html"
    JSON = "json"
    TEXT = "text"


class SpecType(StrEnum):
    RFC = "rfc"


class ArtifactType(StrEnum):
    RFC = "rfc"
    ADR = "adr"
    DESIGN_NOTE = "design_note"
    RUN_NOTE = "run_note"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CitationKind(StrEnum):
    REPO_RANGE = "repo_range"
    REPO_PR = "repo_pr"
    REPO_COMMIT = "repo_commit"
    TRANSCRIPT_RANGE = "transcript_range"


class ResolvedState(StrEnum):
    LIVE = "live"
    STALE = "stale"
    MISSING = "missing"
    UNKNOWN = "unknown"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageRead(BaseModel):
    id: str
    role: MessageRole
    content: str
    created_at: datetime


class ArtifactRead(BaseModel):
    id: str
    conversation_id: str
    origin_conversation_id: str | None = None
    title: str
    content: str
    content_type: ContentType
    version: int
    artifact_type: ArtifactType | None = None
    updated_at: datetime
    last_opened_at: datetime | None = None
    summary: str = ""
    status: ArtifactStatus = ArtifactStatus.DRAFT
    spec_type: SpecType | None = None
    citations: list[CitationRead] = []


class ArtifactListItem(BaseModel):
    id: str
    conversation_id: str
    origin_conversation_id: str | None = None
    title: str
    content_type: ContentType
    version: int
    artifact_type: ArtifactType | None = None
    updated_at: datetime
    last_opened_at: datetime | None = None
    summary: str = ""
    status: ArtifactStatus = ArtifactStatus.DRAFT
    spec_type: SpecType | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    artifact_count: int = 0
    archived_at: datetime | None = None


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    messages: list[MessageRead]
    artifacts: list[ArtifactRead]
    active_artifact_id: str | None = None


class CurrentArtifactState(BaseModel):
    id: str | None = None
    title: str
    content: str
    content_type: ContentType
    version: int | None = None


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=24_000)
    current_artifact: CurrentArtifactState | None = None
    model: str | None = None


class RegenerateRequest(BaseModel):
    conversation_id: str
    current_artifact: CurrentArtifactState | None = None
    model: str | None = None


class EditLastUserRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=24_000)
    current_artifact: CurrentArtifactState | None = None
    model: str | None = None


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: Literal["openai", "anthropic"]
    available: bool


class ArtifactUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=500_000)
    content_type: ContentType
    expected_version: int | None = None
    artifact_type: ArtifactType | None = None
    status: ArtifactStatus | None = None
    summary: str | None = Field(default=None, max_length=4_000)


class LibraryArtifactCreateRequest(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(default="", max_length=500_000)
    content_type: ContentType = ContentType.MARKDOWN
    artifact_type: ArtifactType
    status: ArtifactStatus = ArtifactStatus.DRAFT
    summary: str = Field(default="", max_length=4_000)
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    project_id: str
    seed_title: str | None = None


class SearchReplacePatch(BaseModel):
    search: str
    replace: str
    replace_all: bool = False
    allow_missing: bool = False


class CanvasToolCall(BaseModel):
    action: Literal["create", "replace", "patch"]
    title: str
    content_type: ContentType
    summary: str
    content: str | None = None
    patches: list[SearchReplacePatch] | None = None


class ExportFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    DOCX = "docx"
    PDF = "pdf"


class RenderedExportRequest(BaseModel):
    format: Literal["docx", "pdf", "html"]
    html: str


class SpecSourceRead(BaseModel):
    id: str
    artifact_id: str
    kind: Literal["transcript", "repo"]
    payload: dict
    created_at: datetime


class CitationRead(BaseModel):
    id: str
    artifact_id: str
    anchor: str
    kind: CitationKind
    target: dict
    resolved_state: ResolvedState
    last_checked_at: datetime | None = None
    last_observed: dict | None = None


class SpecDraftRequest(BaseModel):
    project_id: str
    conversation_id: str | None = None
    transcript: str = Field(min_length=1, max_length=200_000)
    repo: str = Field(min_length=3, max_length=240)
    # Optional per-request PAT. When omitted the backend uses GITHUB_DEFAULT_TOKEN.
    github_token: str | None = None


class SpecDraftResult(BaseModel):
    artifact_id: str
    conversation_id: str
    title: str
    ref_at_draft: str
    picked_paths: list[str]
    citation_count: int
    dropped_count: int


class VerifyCitationsResult(BaseModel):
    artifact_id: str
    counts: dict[str, int]
    truncated: bool
    remaining: int
    citations: list[CitationRead]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class SignUpRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class SignInRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class ProjectRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class ProjectCreateRequest(BaseModel):
    name: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    role: ProjectRole
    created_at: datetime
    updated_at: datetime


class ProjectMemberRead(BaseModel):
    user_id: str
    email: str
    name: str
    role: ProjectRole
    created_at: datetime


class PendingInviteRead(BaseModel):
    id: str
    email: str
    invited_by_user_id: str
    expires_at: datetime
    created_at: datetime


class ProjectDetail(BaseModel):
    id: str
    name: str
    role: ProjectRole
    created_at: datetime
    updated_at: datetime
    members: list[ProjectMemberRead]
    pending_invites: list[PendingInviteRead]


class InviteCreateRequest(BaseModel):
    email: str


class InviteCreateResponse(BaseModel):
    id: str
    project_id: str
    email: str
    token: str  # raw; the caller uses this to build a copy-paste URL
    accept_url: str
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------
class ScaffoldRequest(BaseModel):
    text: str | None = None
    repo_url: str | None = None
    hint: str | None = None
    # Optional. When set, the scaffold attaches to that existing project
    # (caller must be a member). When absent, a new project is created.
    project_id: str | None = None


class ScaffoldResponse(BaseModel):
    project: ProjectSummary
    project_created: bool
    artifact_id: str
    conversation_id: str
    pad_type: ArtifactType
    pad_title: str
    source_id: str | None
    outline_sections: list[str]
    detected_repo_urls: list[str]


# ---------------------------------------------------------------------------
# Sources (Phase 3)
# ---------------------------------------------------------------------------
class SourceKind(StrEnum):
    REPO = "repo"
    TRANSCRIPT = "transcript"
    NOTE = "note"
    FILE = "file"
    IMAGE = "image"


class SourceCreateRequest(BaseModel):
    # ``file`` and ``image`` are intentionally not accepted here yet —
    # they need the Stream B upload pipeline. The handler rejects them
    # with a 400 until that lands.
    kind: Literal["repo", "transcript", "note"]
    title: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2_000)
    text: str | None = Field(default=None, max_length=500_000)
    ref_pinned: str | None = Field(default=None, max_length=128)
    provenance: dict | None = None


class SourceSnapshotRead(BaseModel):
    id: str
    snapshot_ref: str
    content_hash: str
    content_text: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class SourceSummary(BaseModel):
    id: str
    project_id: str
    kind: SourceKind
    title: str
    provider: str
    canonical_key: str | None = None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime
    snapshot_count: int = 0
    linked_pad_count: int = 0


class SourceDetail(SourceSummary):
    provenance: dict = Field(default_factory=dict)
    snapshots: list[SourceSnapshotRead] = []
    linked_pad_ids: list[str] = []


class SourceCreateResponse(BaseModel):
    source: SourceSummary
    snapshot_id: str
    created: bool  # False when an existing source was returned (dedupe hit)
