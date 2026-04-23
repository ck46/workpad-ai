"""Tests for the scaffold service + POST /api/scaffold endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import Artifact, Conversation, SpecSource
from app.projects import Project, ProjectMember, ROLE_OWNER
from app.rfc_drafter import ModelCall, ToolCallResult
from app.scaffold_service import (
    ScaffoldInference,
    ScaffoldService,
    build_scaffold_prompt,
    fallback_detect_repo_urls,
    render_outline_markdown,
)


# ---------------------------------------------------------------------------
# Pure helpers (no DB / no model)
# ---------------------------------------------------------------------------
def test_render_outline_markdown_produces_h1_plus_h2_per_section() -> None:
    body = render_outline_markdown(
        "Rate limiting",
        ["Context", "Approach", "Open questions"],
    )
    assert body.startswith("# Rate limiting\n")
    assert "## Context" in body
    assert "## Approach" in body
    assert "## Open questions" in body
    assert body.count("## ") == 3
    assert body.endswith("\n")


def test_render_outline_markdown_without_sections_uses_fallback_scaffold() -> None:
    body = render_outline_markdown("My pad", [])
    assert "## Context" in body
    assert "## Notes" in body


def test_build_scaffold_prompt_requires_some_input() -> None:
    with pytest.raises(ValueError):
        build_scaffold_prompt(text=None, repo_url=None, hint=None)
    with pytest.raises(ValueError):
        build_scaffold_prompt(text="   ", repo_url=None, hint="")


def test_build_scaffold_prompt_composes_all_three_parts() -> None:
    prompt = build_scaffold_prompt(
        text="Alex: we should rate-limit the signup endpoint.",
        repo_url="https://github.com/acme/api",
        hint="RFC on rate limiting",
    )
    assert "## User hint" in prompt
    assert "## Repo URL" in prompt
    assert "## Pasted input" in prompt
    assert "rate-limit the signup" in prompt


def test_build_scaffold_prompt_caps_long_text() -> None:
    long_text = "line\n" * 10000
    prompt = build_scaffold_prompt(text=long_text, repo_url=None, hint=None)
    # 16000 char cap + the "## Pasted input\n" prefix
    assert len(prompt) < 17000


def test_fallback_detect_repo_urls_pulls_from_any_input() -> None:
    found = fallback_detect_repo_urls(
        "See https://github.com/acme/api for context.",
        None,
        "ref https://github.com/acme/web.",
    )
    assert found == ["https://github.com/acme/api", "https://github.com/acme/web"]


def test_fallback_detect_repo_urls_dedupes() -> None:
    found = fallback_detect_repo_urls(
        "https://github.com/acme/api",
        "https://github.com/acme/api",
    )
    assert found == ["https://github.com/acme/api"]


def test_scaffold_inference_defaults_unknown_pad_type_to_design_note() -> None:
    inference = ScaffoldInference.from_tool_args(
        {
            "project_name": "Payments",
            "pad_type": "something-weird",
            "pad_title": "Untitled",
            "outline_sections": ["Context"],
            "detected_repo_urls": [],
        }
    )
    assert inference.pad_type == "design_note"


# ---------------------------------------------------------------------------
# ScaffoldService (scripted AI, real DB)
# ---------------------------------------------------------------------------
@dataclass
class _ScriptedAI:
    """Replays one ToolCallResult. Captures the ModelCall for assertions."""

    response: ToolCallResult
    received: list[ModelCall]

    def call_tool(self, call: ModelCall) -> ToolCallResult:
        self.received.append(call)
        return self.response


def _make_user(session, email: str) -> str:
    from app.auth import User, hash_password

    user = User(email=email, password_hash=hash_password("correct-horse"))
    session.add(user)
    session.flush()
    return user.id


def _rfc_inference_args() -> dict[str, Any]:
    return {
        "project_name": "Auth hardening",
        "pad_type": "rfc",
        "pad_title": "Rework session verification",
        "outline_sections": [
            "Context",
            "Current behavior",
            "Proposed change",
            "Rollout plan",
        ],
        "detected_repo_urls": ["https://github.com/acme/auth"],
    }


def test_scaffold_creates_project_pad_and_sources_for_new_user(
    session_factory,
) -> None:
    with session_factory() as session:
        user_id = _make_user(session, "scaffold-a@example.com")
        session.commit()

    ai = _ScriptedAI(
        received=[],
        response=ToolCallResult(name="infer_scaffold", arguments=_rfc_inference_args()),
    )
    service = ScaffoldService(
        ai_client=ai, session_factory=session_factory, model="test-model"
    )

    result = service.scaffold(
        user_id=user_id,
        text="Alex: the login handler always returns True.\nSam: yeah, we need real verification.",
        repo_url="https://github.com/acme/auth",
        hint="RFC on auth hardening",
    )

    # The model received the composed prompt.
    assert len(ai.received) == 1
    call = ai.received[0]
    assert call.tool_choice_name == "infer_scaffold"
    assert "Alex: the login handler" in call.user_message
    assert "https://github.com/acme/auth" in call.user_message
    assert "RFC on auth hardening" in call.user_message

    # Result carries what the frontend needs to route into the new pad.
    assert result.project_created is True
    assert result.project_name == "Auth hardening"
    assert result.pad_type == "rfc"
    assert result.pad_title == "Rework session verification"
    assert result.outline_sections == [
        "Context",
        "Current behavior",
        "Proposed change",
        "Rollout plan",
    ]
    assert result.detected_repo_urls == ["https://github.com/acme/auth"]
    assert result.source_id is not None

    # DB shape: project + owner membership + conversation + artifact.
    with session_factory() as session:
        project = session.get(Project, result.project_id)
        assert project is not None
        assert project.name == "Auth hardening"
        assert project.created_by_user_id == user_id

        member = session.query(ProjectMember).filter_by(project_id=project.id).one()
        assert member.user_id == user_id
        assert member.role == ROLE_OWNER

        artifact = session.get(Artifact, result.artifact_id)
        assert artifact is not None
        assert artifact.project_id == project.id
        assert artifact.artifact_type == "rfc"
        assert artifact.spec_type == "rfc"  # RFC maps to both for library filters
        assert artifact.status == "draft"
        assert "# Rework session verification" in artifact.content
        assert "## Rollout plan" in artifact.content

        conv = session.get(Conversation, result.conversation_id)
        assert conv is not None
        assert conv.project_id == project.id
        assert conv.owner_id == user_id

        sources = (
            session.query(SpecSource).filter_by(artifact_id=artifact.id).all()
        )
        kinds = {s.kind for s in sources}
        assert kinds == {"transcript", "repo"}


def test_scaffold_reuses_existing_project_when_project_id_given(
    session_factory,
) -> None:
    with session_factory() as session:
        user_id = _make_user(session, "existing@example.com")
        project = Project(name="My project", created_by_user_id=user_id)
        session.add(project)
        session.flush()
        session.add(
            ProjectMember(project_id=project.id, user_id=user_id, role=ROLE_OWNER)
        )
        session.commit()
        project_id = project.id

    ai = _ScriptedAI(
        received=[],
        response=ToolCallResult(name="infer_scaffold", arguments=_rfc_inference_args()),
    )
    service = ScaffoldService(
        ai_client=ai, session_factory=session_factory, model="test-model"
    )
    result = service.scaffold(
        user_id=user_id,
        text="Some notes.",
        repo_url=None,
        hint=None,
        project_id=project_id,
    )

    assert result.project_created is False
    assert result.project_id == project_id
    assert result.project_name == "My project"  # existing name wins

    with session_factory() as session:
        # Exactly one project exists for this user.
        projects = session.query(Project).filter_by(created_by_user_id=user_id).all()
        assert len(projects) == 1


def test_scaffold_rejects_empty_input(session_factory) -> None:
    with session_factory() as session:
        user_id = _make_user(session, "empty@example.com")
        session.commit()

    ai = _ScriptedAI(
        received=[],
        response=ToolCallResult(name="infer_scaffold", arguments=_rfc_inference_args()),
    )
    service = ScaffoldService(
        ai_client=ai, session_factory=session_factory, model="test-model"
    )
    with pytest.raises(ValueError):
        service.scaffold(user_id=user_id, text="", repo_url="  ", hint=None)


def test_scaffold_rejects_non_member_on_existing_project(session_factory) -> None:
    from app.projects import NotAMember

    with session_factory() as session:
        owner_id = _make_user(session, "owner@example.com")
        project = Project(name="Locked", created_by_user_id=owner_id)
        session.add(project)
        session.flush()
        session.add(
            ProjectMember(project_id=project.id, user_id=owner_id, role=ROLE_OWNER)
        )
        session.commit()
        project_id = project.id

        stranger_id = _make_user(session, "stranger@example.com")
        session.commit()

    ai = _ScriptedAI(
        received=[],
        response=ToolCallResult(name="infer_scaffold", arguments=_rfc_inference_args()),
    )
    service = ScaffoldService(
        ai_client=ai, session_factory=session_factory, model="test-model"
    )

    with pytest.raises(NotAMember):
        service.scaffold(
            user_id=stranger_id,
            text="anything",
            project_id=project_id,
        )


def test_scaffold_falls_back_to_regex_repo_detection(session_factory) -> None:
    """If the model returns no detected_repo_urls, regex-extract from input."""

    with session_factory() as session:
        user_id = _make_user(session, "regex@example.com")
        session.commit()

    ai = _ScriptedAI(
        received=[],
        response=ToolCallResult(
            name="infer_scaffold",
            arguments={
                **_rfc_inference_args(),
                "detected_repo_urls": [],  # model forgot
            },
        ),
    )
    service = ScaffoldService(
        ai_client=ai, session_factory=session_factory, model="test-model"
    )
    result = service.scaffold(
        user_id=user_id,
        text="Discussion referenced https://github.com/acme/foo several times.",
        repo_url=None,
        hint=None,
    )
    assert result.detected_repo_urls == ["https://github.com/acme/foo"]


# ---------------------------------------------------------------------------
# HTTP endpoint (uses the FastAPI TestClient fixture + a patched
# ScaffoldService so we don't hit OpenAI in tests).
# ---------------------------------------------------------------------------
def test_post_scaffold_requires_auth(client: TestClient) -> None:
    r = client.post("/api/scaffold", json={"text": "anything"})
    assert r.status_code == 401


def test_post_scaffold_rejects_empty_request(authed_client: TestClient) -> None:
    r = authed_client.post("/api/scaffold", json={})
    assert r.status_code == 400


def test_post_scaffold_surfaces_missing_openai_key_as_503(
    authed_client: TestClient,
) -> None:
    from app import core

    # Clear whatever OPENAI_API_KEY the local env may have set so the
    # endpoint behaves like a fresh install.
    core.get_settings.cache_clear()
    with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
        core.get_settings.cache_clear()
        r = authed_client.post(
            "/api/scaffold", json={"text": "some notes", "hint": "RFC"}
        )
        assert r.status_code == 503
    core.get_settings.cache_clear()


def test_post_scaffold_happy_path_with_mocked_service(
    authed_client: TestClient, authed_user: dict[str, str], session_factory
) -> None:
    """End-to-end happy path: POST returns ScaffoldResponse; DB has the
    new project + pad attributed to the caller."""

    from app import main as main_module
    from app.scaffold_service import ScaffoldResult

    # Pretend the server has a key so the endpoint doesn't 503 on us.
    settings = main_module.get_settings()
    original_key = settings.openai_api_key
    settings.openai_api_key = "test-key"

    fake_result = ScaffoldResult(
        project_id="",  # filled in below
        project_name="Payments rate limiting",
        project_created=True,
        artifact_id="",  # filled in below
        conversation_id="",
        pad_type="rfc",
        pad_title="Rate-limit the signup endpoint",
        source_id=None,
        outline_sections=["Context", "Proposed change"],
        detected_repo_urls=[],
    )

    # Actually create rows so the endpoint's post-service DB lookups
    # succeed, but intercept the OpenAI-construction path.
    from app.auth import User
    from app.projects import Project, ProjectMember, ROLE_OWNER

    with session_factory() as session:
        caller = session.query(User).filter_by(email=authed_user["email"]).one()
        project = Project(name=fake_result.project_name, created_by_user_id=caller.id)
        session.add(project)
        session.flush()
        session.add(ProjectMember(project_id=project.id, user_id=caller.id, role=ROLE_OWNER))
        conv = Conversation(
            title=fake_result.pad_title, owner_id=caller.id, project_id=project.id
        )
        session.add(conv)
        session.flush()
        artifact = Artifact(
            conversation_id=conv.id,
            origin_conversation_id=conv.id,
            project_id=project.id,
            title=fake_result.pad_title,
            content="# " + fake_result.pad_title,
            content_type="markdown",
            artifact_type="rfc",
            status="draft",
            version=1,
        )
        session.add(artifact)
        session.commit()
        fake_result = ScaffoldResult(
            **{**fake_result.__dict__, "project_id": project.id,
               "artifact_id": artifact.id, "conversation_id": conv.id},
        )

    class _FakeService:
        def scaffold(self, **_kwargs: Any) -> ScaffoldResult:
            return fake_result

    # Patch the OpenAI construction inside the endpoint so it returns
    # our fake service; ScaffoldService call isn't actually executed.
    with patch("app.scaffold_service.ScaffoldService", return_value=_FakeService()):
        with patch("openai.OpenAI", return_value=object()):
            r = authed_client.post(
                "/api/scaffold",
                json={
                    "text": "we should rate-limit the signup endpoint",
                    "hint": "RFC on rate limits",
                },
            )

    # Restore
    settings.openai_api_key = original_key

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_created"] is True
    assert body["project"]["name"] == fake_result.project_name
    assert body["project"]["role"] == "owner"
    assert body["pad_type"] == "rfc"
    assert body["pad_title"] == fake_result.pad_title
    assert body["artifact_id"] == fake_result.artifact_id
    assert body["conversation_id"] == fake_result.conversation_id
    assert body["outline_sections"] == fake_result.outline_sections
