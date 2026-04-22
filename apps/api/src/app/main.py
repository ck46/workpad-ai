from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .auth import (
    User,
    clear_session_cookie,
    confirm_password_reset,
    create_session,
    create_user,
    find_user_by_email,
    get_current_user,
    request_password_reset,
    revoke_session,
    set_session_cookie,
    verify_password,
    SESSION_COOKIE,
)
from .core import (
    archive_conversation,
    create_library_artifact,
    delete_conversation,
    export_artifact,
    export_artifact_from_rendered_html,
    get_artifact_detail,
    get_artifact_diff,
    get_conversation_detail,
    get_conversation_or_404,
    get_session_factory,
    get_settings,
    init_db,
    list_library_artifacts,
    list_conversations,
    serialize_conversation,
    unarchive_conversation,
    update_artifact_manually,
)
from .chat_service import WorkpadChatService
from .github_client import GitHubAuthError, GitHubClientError
from .schemas import (
    ArtifactUpdateRequest,
    ArtifactListItem,
    ArtifactRead,
    ArtifactStatus,
    ArtifactType,
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    EditLastUserRequest,
    ExportFormat,
    LibraryArtifactCreateRequest,
    ModelInfo,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegenerateRequest,
    RenderedExportRequest,
    SignInRequest,
    SignUpRequest,
    SpecDraftRequest,
    UserRead,
    VerifyCitationsResult,
)
from .spec_service import CitationInsightService, CitationVerifyService, SpecDraftService

CurrentUser = Annotated[User, Depends(get_current_user)]


logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _user_to_read(user: User) -> UserRead:
    return UserRead(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


@app.post(f"{settings.api_prefix}/auth/signup", response_model=UserRead)
def signup(payload: SignUpRequest, request: Request):
    email = (payload.email or "").strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="email and password are required")
    with session_factory() as session:
        try:
            user = create_user(
                session,
                email=email,
                password=payload.password,
                name=(payload.name or "").strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session_record = create_session(session, user.id)
        user_read = _user_to_read(user)
        sid = session_record.id
    response = JSONResponse(content=user_read.model_dump(mode="json"))
    set_session_cookie(request, response, sid)
    return response


@app.post(f"{settings.api_prefix}/auth/signin", response_model=UserRead)
def signin(payload: SignInRequest, request: Request):
    email = (payload.email or "").strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="email and password are required")
    with session_factory() as session:
        user = find_user_by_email(session, email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="that email and password don't match")
        session_record = create_session(session, user.id)
        user_read = _user_to_read(user)
        sid = session_record.id
    response = JSONResponse(content=user_read.model_dump(mode="json"))
    set_session_cookie(request, response, sid)
    return response


@app.post(f"{settings.api_prefix}/auth/signout")
def signout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        with session_factory() as session:
            revoke_session(session, sid)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@app.get(f"{settings.api_prefix}/auth/me", response_model=UserRead)
def me(user: CurrentUser):
    return _user_to_read(user)


@app.post(f"{settings.api_prefix}/auth/reset-request", status_code=202)
def auth_reset_request(payload: PasswordResetRequest, request: Request):
    """Ask for a password reset link.

    Returns 202 regardless of whether the email corresponds to a real user —
    this is deliberate so callers can't enumerate accounts. When a matching
    user exists and no recent token was issued, log the reset URL. In v1
    there is no mailer; the URL lands in the server log for the operator.
    """

    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    with session_factory() as session:
        result = request_password_reset(session, email)
    if result is not None:
        _user, raw_token = result
        base = f"{request.url.scheme}://{request.url.netloc}"
        reset_url = f"{base}/#/reset?token={raw_token}"
        logger.info("password-reset-url email=%s url=%s", email, reset_url)
    return {"status": "ok"}


@app.post(f"{settings.api_prefix}/auth/reset-confirm", status_code=204)
def auth_reset_confirm(payload: PasswordResetConfirm):
    token = (payload.token or "").strip()
    new_password = payload.new_password or ""
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="token and new_password are required")
    with session_factory() as session:
        try:
            user = confirm_password_reset(session, token, new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    return Response(status_code=204)


@app.get(f"{settings.api_prefix}/settings/info")
def settings_info() -> dict[str, bool]:
    current = get_settings()
    return {
        "has_github_default_token": bool(current.github_default_token),
        "has_openai_api_key": bool(current.openai_api_key),
    }


@app.get(f"{settings.api_prefix}/models", response_model=list[ModelInfo])
def list_models():
    return workpad_service.available_models()


@app.get(f"{settings.api_prefix}/conversations", response_model=list[ConversationSummary])
def get_conversations(user: CurrentUser, include_archived: bool = False):
    with session_factory() as session:
        return list_conversations(session, include_archived=include_archived, owner_id=user.id)


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/archive", response_model=ConversationSummary)
def archive_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            get_conversation_or_404(session, conversation_id, owner_id=user.id)
            conversation = archive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/unarchive", response_model=ConversationSummary)
def unarchive_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            get_conversation_or_404(session, conversation_id, owner_id=user.id)
            conversation = unarchive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(f"{settings.api_prefix}/conversations/{{conversation_id}}")
def delete_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            get_conversation_or_404(session, conversation_id, owner_id=user.id)
            delete_conversation(session, conversation_id)
            return Response(status_code=204)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations", response_model=ConversationSummary)
def create_conversation(user: CurrentUser):
    from .core import create_conversation as create_db_conversation

    with session_factory() as session:
        conversation = create_db_conversation(session, owner_id=user.id)
        return serialize_conversation(conversation, session)


@app.get(f"{settings.api_prefix}/conversations/{{conversation_id}}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            return get_conversation_detail(session, conversation_id, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(f"{settings.api_prefix}/artifacts/{{artifact_id}}")
def update_artifact(artifact_id: str, payload: ArtifactUpdateRequest, user: CurrentUser):
    with session_factory() as session:
        try:
            artifact = update_artifact_manually(session, artifact_id, payload, owner_id=user.id)
            return artifact
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc).lower() else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def get_artifact(artifact_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            return get_artifact_detail(session, artifact_id, mark_opened=True, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/library/artifacts", response_model=list[ArtifactListItem])
def get_library_artifacts(
    user: CurrentUser,
    artifact_type: ArtifactType | None = None,
    status: ArtifactStatus | None = None,
    q: str | None = None,
    limit: int = 100,
):
    with session_factory() as session:
        return list_library_artifacts(
            session,
            artifact_type=artifact_type.value if artifact_type else None,
            status=status.value if status else None,
            query_text=q,
            limit=limit,
            owner_id=user.id,
        )


@app.post(f"{settings.api_prefix}/library/artifacts", response_model=ArtifactRead)
def create_library_artifact_endpoint(payload: LibraryArtifactCreateRequest, user: CurrentUser):
    with session_factory() as session:
        try:
            return create_library_artifact(session, payload, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/library/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def get_library_artifact(artifact_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            return get_artifact_detail(session, artifact_id, mark_opened=True, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(f"{settings.api_prefix}/library/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def update_library_artifact_endpoint(
    artifact_id: str, payload: ArtifactUpdateRequest, user: CurrentUser
):
    with session_factory() as session:
        try:
            return update_artifact_manually(session, artifact_id, payload, owner_id=user.id)
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc).lower() else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}/diff")
def diff_artifact(
    artifact_id: str,
    user: CurrentUser,
    from_version: int | None = None,
    to_version: int | None = None,
):
    with session_factory() as session:
        try:
            return get_artifact_diff(
                session,
                artifact_id,
                from_version=from_version,
                to_version=to_version,
                owner_id=user.id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}/export")
def download_artifact(
    artifact_id: str, user: CurrentUser, format: ExportFormat = ExportFormat.MARKDOWN
):
    with session_factory() as session:
        try:
            get_artifact_detail(session, artifact_id, owner_id=user.id)
            body, media_type, filename = export_artifact(session, artifact_id, format.value)
            return Response(
                content=body,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/artifacts/{{artifact_id}}/export-rendered")
def download_artifact_from_rendered_html(
    artifact_id: str, payload: RenderedExportRequest, user: CurrentUser
):
    with session_factory() as session:
        try:
            get_artifact_detail(session, artifact_id, owner_id=user.id)
            body, media_type, filename = export_artifact_from_rendered_html(
                session, artifact_id, payload.format, payload.html
            )
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
def stream_chat(payload: ChatRequest, user: CurrentUser):
    return StreamingResponse(
        workpad_service.stream_chat(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/chat/regenerate")
def regenerate_chat(payload: RegenerateRequest, user: CurrentUser):
    return StreamingResponse(
        workpad_service.regenerate_last(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/chat/edit-last-user")
def edit_last_user_chat(payload: EditLastUserRequest, user: CurrentUser):
    return StreamingResponse(
        workpad_service.rerun_after_edit(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/specs/draft")
def draft_spec(payload: SpecDraftRequest, user: CurrentUser):
    return StreamingResponse(
        spec_draft_service.stream_draft(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(
    f"{settings.api_prefix}/artifacts/{{artifact_id}}/verify-citations",
    response_model=VerifyCitationsResult,
)
def verify_artifact_citations(artifact_id: str, user: CurrentUser, force: bool = False):
    with session_factory() as session:
        try:
            get_artifact_detail(session, artifact_id, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
def preview_citation(citation_id: str, user: CurrentUser):
    try:
        return citation_insight_service.preview(citation_id)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/citations/{{citation_id}}/diff")
def diff_citation(citation_id: str, user: CurrentUser):
    try:
        return citation_insight_service.diff(citation_id)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
