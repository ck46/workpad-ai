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
from .projects import (
    InviteInvalid,
    NotAMember,
    NotOwner,
    accept_invite,
    create_invite,
    create_project,
    get_project_for_user,
    list_members,
    list_pending_invites,
    list_projects_for_user,
    require_owner,
)
from .schemas import (
    ArtifactUpdateRequest,
    ArtifactListItem,
    ArtifactRead,
    ArtifactStatus,
    ArtifactType,
    ChatRequest,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    EditLastUserRequest,
    ExportFormat,
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    LibraryArtifactCreateRequest,
    ModelInfo,
    PasswordResetConfirm,
    PasswordResetRequest,
    PendingInviteRead,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectMemberRead,
    ProjectRole,
    ProjectSummary,
    RegenerateRequest,
    RenderedExportRequest,
    ScaffoldRequest,
    ScaffoldResponse,
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


# ---------------------------------------------------------------------------
# Project-scoped resource guards
# ---------------------------------------------------------------------------
def _require_project_member_or_403(session, project_id: str, user: User) -> None:
    """Raise 403 if ``user`` isn't a member of ``project_id``."""

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    try:
        from .projects import require_member as _require_member

        _require_member(session, project_id, user.id)
    except NotAMember as exc:
        raise HTTPException(status_code=403, detail="not a member of this project") from exc


def _require_artifact_access(session, artifact_id: str, user: User):
    """Fetch an artifact and raise 403/404 if the caller can't see it.

    404 when the artifact doesn't exist. 403 when it exists but the
    caller isn't a member of its project. If the artifact has no
    project_id yet (orphan from pre-backfill), treat as 404 — it's not
    visible via the library and was never assigned.
    """

    from .core import Artifact

    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not artifact.project_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    _require_project_member_or_403(session, artifact.project_id, user)
    return artifact


def _require_conversation_access(session, conversation_id: str, user: User):
    from .core import Conversation

    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conv.project_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _require_project_member_or_403(session, conv.project_id, user)
    return conv


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@app.post(f"{settings.api_prefix}/projects", response_model=ProjectSummary)
def projects_create(payload: ProjectCreateRequest, user: CurrentUser):
    with session_factory() as session:
        try:
            project = create_project(session, name=payload.name, owner=user)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ProjectSummary(
            id=project.id,
            name=project.name,
            role=ProjectRole.OWNER,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


@app.get(f"{settings.api_prefix}/projects", response_model=list[ProjectSummary])
def projects_list(user: CurrentUser):
    with session_factory() as session:
        rows = list_projects_for_user(session, user.id)
        return [
            ProjectSummary(
                id=project.id,
                name=project.name,
                role=ProjectRole(role),
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
            for project, role in rows
        ]


@app.get(f"{settings.api_prefix}/projects/{{project_id}}", response_model=ProjectDetail)
def projects_detail(project_id: str, user: CurrentUser):
    with session_factory() as session:
        try:
            project, role = get_project_for_user(session, project_id, user.id)
        except NotAMember as exc:
            raise HTTPException(status_code=403, detail="not a member of this project") from exc

        members = [
            ProjectMemberRead(
                user_id=member_user.id,
                email=member_user.email,
                name=member_user.name,
                role=ProjectRole(member.role),
                created_at=member.created_at,
            )
            for member, member_user in list_members(session, project.id)
        ]
        invites = [
            PendingInviteRead(
                id=invite.id,
                email=invite.email,
                invited_by_user_id=invite.invited_by_user_id,
                expires_at=invite.expires_at,
                created_at=invite.created_at,
            )
            for invite in list_pending_invites(session, project.id)
        ]
        return ProjectDetail(
            id=project.id,
            name=project.name,
            role=ProjectRole(role),
            created_at=project.created_at,
            updated_at=project.updated_at,
            members=members,
            pending_invites=invites,
        )


@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/invites",
    response_model=InviteCreateResponse,
)
def projects_create_invite(
    project_id: str,
    payload: InviteCreateRequest,
    user: CurrentUser,
    request: Request,
):
    with session_factory() as session:
        try:
            project, _role = get_project_for_user(session, project_id, user.id)
        except NotAMember as exc:
            raise HTTPException(status_code=403, detail="not a member of this project") from exc
        try:
            require_owner(session, project.id, user.id)
        except NotOwner as exc:
            raise HTTPException(status_code=403, detail="only owners can invite") from exc
        try:
            record, raw_token = create_invite(
                session, project=project, email=payload.email, invited_by=user
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        base = f"{request.url.scheme}://{request.url.netloc}"
        accept_url = f"{base}/#/invite?token={raw_token}"
        return InviteCreateResponse(
            id=record.id,
            project_id=record.project_id,
            email=record.email,
            token=raw_token,
            accept_url=accept_url,
            expires_at=record.expires_at,
        )


@app.post(f"{settings.api_prefix}/invites/accept", response_model=ProjectSummary)
def invites_accept(payload: InviteAcceptRequest, user: CurrentUser):
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    with session_factory() as session:
        try:
            project, member = accept_invite(session, token=token, user=user)
        except InviteInvalid as exc:
            raise HTTPException(status_code=400, detail="invalid or expired invite") from exc
        return ProjectSummary(
            id=project.id,
            name=project.name,
            role=ProjectRole(member.role),
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


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
def get_conversations(
    user: CurrentUser,
    project_id: str,
    include_archived: bool = False,
):
    with session_factory() as session:
        _require_project_member_or_403(session, project_id, user)
        return list_conversations(
            session, include_archived=include_archived, project_id=project_id
        )


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/archive", response_model=ConversationSummary)
def archive_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_conversation_access(session, conversation_id, user)
        try:
            conversation = archive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/unarchive", response_model=ConversationSummary)
def unarchive_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_conversation_access(session, conversation_id, user)
        try:
            conversation = unarchive_conversation(session, conversation_id)
            return serialize_conversation(conversation, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(f"{settings.api_prefix}/conversations/{{conversation_id}}")
def delete_conversation_endpoint(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_conversation_access(session, conversation_id, user)
        try:
            delete_conversation(session, conversation_id)
            return Response(status_code=204)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(f"{settings.api_prefix}/conversations", response_model=ConversationSummary)
def create_conversation(payload: ConversationCreateRequest, user: CurrentUser):
    from .core import create_conversation as create_db_conversation

    with session_factory() as session:
        _require_project_member_or_403(session, payload.project_id, user)
        conversation = create_db_conversation(
            session,
            seed_title=payload.seed_title,
            project_id=payload.project_id,
            owner_id=user.id,
        )
        return serialize_conversation(conversation, session)


@app.get(f"{settings.api_prefix}/conversations/{{conversation_id}}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_conversation_access(session, conversation_id, user)
        try:
            return get_conversation_detail(session, conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(f"{settings.api_prefix}/artifacts/{{artifact_id}}")
def update_artifact(artifact_id: str, payload: ArtifactUpdateRequest, user: CurrentUser):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
        try:
            artifact = update_artifact_manually(session, artifact_id, payload)
            return artifact
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc).lower() else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def get_artifact(artifact_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
        try:
            return get_artifact_detail(session, artifact_id, mark_opened=True)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/library/artifacts", response_model=list[ArtifactListItem])
def get_library_artifacts(
    user: CurrentUser,
    project_id: str,
    artifact_type: ArtifactType | None = None,
    status: ArtifactStatus | None = None,
    q: str | None = None,
    limit: int = 100,
):
    with session_factory() as session:
        _require_project_member_or_403(session, project_id, user)
        return list_library_artifacts(
            session,
            artifact_type=artifact_type.value if artifact_type else None,
            status=status.value if status else None,
            query_text=q,
            limit=limit,
            project_id=project_id,
        )


@app.post(f"{settings.api_prefix}/library/artifacts", response_model=ArtifactRead)
def create_library_artifact_endpoint(payload: LibraryArtifactCreateRequest, user: CurrentUser):
    with session_factory() as session:
        _require_project_member_or_403(session, payload.project_id, user)
        # If a conversation_id is attached, the caller can only use one
        # that's in the same project they just proved membership for.
        if payload.conversation_id:
            _require_conversation_access(session, payload.conversation_id, user)
            from .core import Conversation

            conv = session.get(Conversation, payload.conversation_id)
            if conv is None or conv.project_id != payload.project_id:
                raise HTTPException(
                    status_code=400,
                    detail="conversation_id belongs to a different project",
                )
        try:
            return create_library_artifact(
                session, payload, project_id=payload.project_id, owner_id=user.id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/library/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def get_library_artifact(artifact_id: str, user: CurrentUser):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
        try:
            return get_artifact_detail(session, artifact_id, mark_opened=True)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(f"{settings.api_prefix}/library/artifacts/{{artifact_id}}", response_model=ArtifactRead)
def update_library_artifact_endpoint(
    artifact_id: str, payload: ArtifactUpdateRequest, user: CurrentUser
):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
        try:
            return update_artifact_manually(session, artifact_id, payload)
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
        _require_artifact_access(session, artifact_id, user)
        try:
            return get_artifact_diff(
                session,
                artifact_id,
                from_version=from_version,
                to_version=to_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}/export")
def download_artifact(
    artifact_id: str, user: CurrentUser, format: ExportFormat = ExportFormat.MARKDOWN
):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
        try:
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
        _require_artifact_access(session, artifact_id, user)
        try:
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
    with session_factory() as session:
        _require_project_member_or_403(session, payload.project_id, user)
        if payload.conversation_id:
            _require_conversation_access(session, payload.conversation_id, user)
    return StreamingResponse(
        spec_draft_service.stream_draft(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post(f"{settings.api_prefix}/scaffold", response_model=ScaffoldResponse)
def scaffold_endpoint(payload: ScaffoldRequest, user: CurrentUser):
    """Scaffold a project + pad from one-step seed input.

    Covers the "first session produces value" design principle — the
    caller hands us some raw material (pasted transcript, repo URL,
    free-form hint) and we return a populated project with an outlined
    pad ready to edit.
    """

    from openai import OpenAI

    from .projects import (
        NotAMember,
        Project,
        ProjectMember,
        ROLE_OWNER,
    )
    from .rfc_drafter import OpenAIResponsesAIClient
    from .scaffold_service import ScaffoldService

    # Rudimentary request validation — the rest happens in the service.
    if not (payload.text or payload.repo_url or payload.hint):
        raise HTTPException(
            status_code=400,
            detail="scaffold requires at least one of text, repo_url, or hint",
        )
    current_settings = get_settings()
    if not current_settings.openai_api_key:
        raise HTTPException(
            status_code=503, detail="OPENAI_API_KEY is not configured on the server"
        )

    # Membership check up front so we don't spend a model call on a
    # request that can't write to the requested project.
    if payload.project_id:
        with session_factory() as session:
            try:
                _require_project_member_or_403(session, payload.project_id, user)
            except HTTPException:
                raise

    try:
        openai_client = OpenAI(api_key=current_settings.openai_api_key)
        ai_client = OpenAIResponsesAIClient(openai_client, current_settings.default_model)
        service = ScaffoldService(
            ai_client=ai_client,
            session_factory=session_factory,
            model=current_settings.default_model,
        )
        result = service.scaffold(
            user_id=user.id,
            text=payload.text,
            repo_url=payload.repo_url,
            hint=payload.hint,
            project_id=payload.project_id,
        )
    except NotAMember as exc:
        raise HTTPException(status_code=403, detail="not a member of this project") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        # Model/network failures — surface as 502 so the frontend can
        # distinguish from validation errors.
        if exc.__class__.__module__.startswith("openai"):
            raise HTTPException(status_code=502, detail=str(exc) or "model error") from exc
        raise

    # Build the ProjectSummary from the DB — need the caller's role.
    with session_factory() as session:
        project = session.get(Project, result.project_id)
        if project is None:
            raise HTTPException(status_code=500, detail="scaffold completed but project is missing")
        member = (
            session.query(ProjectMember)
            .filter_by(project_id=project.id, user_id=user.id)
            .first()
        )
        role = member.role if member else ROLE_OWNER
        project_summary = ProjectSummary(
            id=project.id,
            name=project.name,
            role=ProjectRole(role),
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    return ScaffoldResponse(
        project=project_summary,
        project_created=result.project_created,
        artifact_id=result.artifact_id,
        conversation_id=result.conversation_id,
        pad_type=ArtifactType(result.pad_type),
        pad_title=result.pad_title,
        source_id=result.source_id,
        outline_sections=result.outline_sections,
        detected_repo_urls=result.detected_repo_urls,
    )


@app.post(
    f"{settings.api_prefix}/artifacts/{{artifact_id}}/verify-citations",
    response_model=VerifyCitationsResult,
)
def verify_artifact_citations(artifact_id: str, user: CurrentUser, force: bool = False):
    with session_factory() as session:
        _require_artifact_access(session, artifact_id, user)
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
