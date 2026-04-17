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
    title: str
    content: str
    content_type: ContentType
    version: int
    updated_at: datetime


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    artifact_count: int = 0


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
