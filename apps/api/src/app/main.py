from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .core import (
    archive_conversation,
    delete_conversation,
    export_artifact,
    get_artifact_or_404,
    get_conversation_detail,
    get_session_factory,
    get_settings,
    init_db,
    list_conversations,
    serialize_artifact,
    serialize_conversation,
    unarchive_conversation,
    update_artifact_manually,
)
from .chat_service import WorkpadChatService
from .github_client import GitHubAuthError, GitHubClientError
from .schemas import (
    ArtifactUpdateRequest,
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    EditLastUserRequest,
    ExportFormat,
    ModelInfo,
    RegenerateRequest,
    SpecDraftRequest,
    VerifyCitationsResult,
)
from .spec_service import CitationInsightService, CitationVerifyService, SpecDraftService


settings = get_settings()
session_factory = get_session_factory()
workpad_service = WorkpadChatService()
spec_draft_service = SpecDraftService()
citation_verify_service = CitationVerifyService()
citation_insight_service = CitationInsightService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|host\.docker\.internal)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/models", response_model=list[ModelInfo])
def list_models():
    return workpad_service.available_models()


@app.get(f"{settings.api_prefix}/conversations", response_model=list[ConversationSummary])
def get_conversations(include_archived: bool = False):
    with session_factory() as session:
        return list_conversations(session, include_archived=include_archived)


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/archive", response_model=ConversationSummary)
def archive_conversation_endpoint(conversation_id: str):
    with session_factory() as session:
        try:
            conversation = archive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/unarchive", response_model=ConversationSummary)
def unarchive_conversation_endpoint(conversation_id: str):
    with session_factory() as session:
        try:
            conversation = unarchive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(f"{settings.api_prefix}/conversations/{{conversation_id}}")
def delete_conversation_endpoint(conversation_id: str):
    with session_factory() as session:
        try:
            delete_conversation(session, conversation_id)
            return Response(status_code=204)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations", response_model=ConversationSummary)
def create_conversation():
    from .core import create_conversation as create_db_conversation

    with session_factory() as session:
        conversation = create_db_conversation(session)
        return serialize_conversation(conversation, session)


@app.get(f"{settings.api_prefix}/conversations/{{conversation_id}}", response_model=ConversationDetail)
def get_conversation(conversation_id: str):
    with session_factory() as session:
        try:
            return get_conversation_detail(session, conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(f"{settings.api_prefix}/artifacts/{{artifact_id}}")
def update_artifact(artifact_id: str, payload: ArtifactUpdateRequest):
    with session_factory() as session:
        try:
            artifact = update_artifact_manually(session, artifact_id, payload)
            return artifact
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}")
def get_artifact(artifact_id: str):
    with session_factory() as session:
        try:
            artifact = get_artifact_or_404(session, artifact_id)
            return serialize_artifact(artifact, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}/export")
def download_artifact(artifact_id: str, format: ExportFormat = ExportFormat.MARKDOWN):
    with session_factory() as session:
        try:
            body, media_type, filename = export_artifact(session, artifact_id, format.value)
            return Response(
                content=body,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@app.post(f"{settings.api_prefix}/chat/stream")
def stream_chat(payload: ChatRequest):
    return StreamingResponse(
        workpad_service.stream_chat(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/chat/regenerate")
def regenerate_chat(payload: RegenerateRequest):
    return StreamingResponse(
        workpad_service.regenerate_last(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/chat/edit-last-user")
def edit_last_user_chat(payload: EditLastUserRequest):
    return StreamingResponse(
        workpad_service.rerun_after_edit(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/specs/draft")
def draft_spec(payload: SpecDraftRequest):
    return StreamingResponse(
        spec_draft_service.stream_draft(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(
    f"{settings.api_prefix}/artifacts/{{artifact_id}}/verify-citations",
    response_model=VerifyCitationsResult,
)
def verify_artifact_citations(artifact_id: str, force: bool = False):
    try:
        result = citation_verify_service.verify(artifact_id, force=force)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Reload citations so last_observed/last_checked_at reflect the just-written
    # values (the in-memory outcomes only carry state, not DB-assigned timestamps).
    citations = citation_verify_service.serialize_citations(artifact_id)
    return VerifyCitationsResult(
        artifact_id=artifact_id,
        counts=result.counts_by_state(),
        truncated=result.truncated,
        remaining=result.remaining,
        citations=citations,
    )


@app.get(f"{settings.api_prefix}/citations/{{citation_id}}/preview")
def preview_citation(citation_id: str):
    try:
        return citation_insight_service.preview(citation_id)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/citations/{{citation_id}}/diff")
def diff_citation(citation_id: str):
    try:
        return citation_insight_service.diff(citation_id)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
