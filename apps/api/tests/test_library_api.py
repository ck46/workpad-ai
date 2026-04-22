from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import Artifact, Conversation


def test_create_library_artifact_creates_backing_conversation(
    authed_client: TestClient,
    authed_project: dict[str, str],
    authed_user: dict[str, str],
    session_factory,
) -> None:
    response = authed_client.post(
        "/api/library/artifacts",
        json={
            "project_id": authed_project["id"],
            "title": "Authentication ADR",
            "content": "# Decision\n\nMove auth to a shared service.",
            "content_type": "markdown",
            "artifact_type": "adr",
            "status": "draft",
            "summary": "Initial ADR draft for auth.",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["artifact_type"] == "adr"
    assert payload["status"] == "draft"
    assert payload["summary"] == "Initial ADR draft for auth."
    assert payload["origin_conversation_id"] == payload["conversation_id"]

    with session_factory() as session:
        artifact = session.get(Artifact, payload["id"])
        assert artifact is not None
        assert artifact.artifact_type == "adr"
        assert artifact.spec_type is None
        assert artifact.summary == "Initial ADR draft for auth."
        assert artifact.origin_conversation_id == artifact.conversation_id
        assert artifact.project_id == authed_project["id"]

        conversation = session.get(Conversation, artifact.conversation_id)
        assert conversation is not None
        assert conversation.title == "Authentication ADR"
        assert conversation.owner_id == authed_user["id"]
        assert conversation.project_id == authed_project["id"]


def test_list_library_artifacts_supports_filters_and_legacy_rfc_fallback(
    authed_client: TestClient,
    authed_project: dict[str, str],
    session_factory,
) -> None:
    project_id = authed_project["id"]
    with session_factory() as session:
        legacy_conversation = Conversation(title="Legacy auth RFC", project_id=project_id)
        design_conversation = Conversation(title="Design exploration", project_id=project_id)
        session.add_all([legacy_conversation, design_conversation])
        session.flush()

        session.add(
            Artifact(
                conversation_id=legacy_conversation.id,
                origin_conversation_id=legacy_conversation.id,
                project_id=project_id,
                title="Legacy auth RFC",
                content="Auth flow and migration notes.",
                content_type="markdown",
                spec_type="rfc",
                artifact_type=None,
                status="active",
                summary="Legacy auth work.",
                version=1,
            )
        )
        session.add(
            Artifact(
                conversation_id=design_conversation.id,
                origin_conversation_id=design_conversation.id,
                project_id=project_id,
                title="Agent memory design note",
                content="Ideas for the design-note flow.",
                content_type="markdown",
                artifact_type="design_note",
                status="draft",
                summary="Memory-system notes.",
                version=1,
            )
        )
        session.commit()

    response = authed_client.get(
        "/api/library/artifacts",
        params={"project_id": project_id, "artifact_type": "rfc", "q": "auth"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Legacy auth RFC"
    assert payload[0]["artifact_type"] == "rfc"
    assert payload[0]["spec_type"] == "rfc"
    assert payload[0]["status"] == "active"


def test_library_detail_marks_open_and_update_writes_generalized_metadata(
    authed_client: TestClient,
    authed_project: dict[str, str],
    session_factory,
) -> None:
    project_id = authed_project["id"]
    with session_factory() as session:
        conversation = Conversation(title="Run notes", project_id=project_id)
        session.add(conversation)
        session.flush()

        artifact = Artifact(
            conversation_id=conversation.id,
            origin_conversation_id=conversation.id,
            project_id=project_id,
            title="Session notes",
            content="Initial notes.",
            content_type="markdown",
            artifact_type="run_note",
            status="draft",
            summary="Raw notes.",
            version=1,
        )
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id

    detail = authed_client.get(f"/api/library/artifacts/{artifact_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["last_opened_at"] is not None

    update = authed_client.put(
        f"/api/library/artifacts/{artifact_id}",
        json={
            "title": "Authentication RFC",
            "content": "# Context\n\nUpdated notes.",
            "content_type": "markdown",
            "expected_version": 1,
            "artifact_type": "rfc",
            "status": "active",
            "summary": "Promoted into an RFC.",
        },
    )

    assert update.status_code == 200
    update_payload = update.json()
    assert update_payload["artifact_type"] == "rfc"
    assert update_payload["spec_type"] == "rfc"
    assert update_payload["status"] == "active"
    assert update_payload["summary"] == "Promoted into an RFC."
    assert update_payload["version"] == 2

    with session_factory() as session:
        artifact = session.get(Artifact, artifact_id)
        assert artifact is not None
        assert artifact.last_opened_at is not None
        assert artifact.artifact_type == "rfc"
        assert artifact.spec_type == "rfc"
        assert artifact.status == "active"
        assert artifact.summary == "Promoted into an RFC."
        assert artifact.version == 2


def test_library_list_requires_auth(client: TestClient) -> None:
    response = client.get("/api/library/artifacts", params={"project_id": "any"})
    assert response.status_code == 401


def test_library_list_requires_project_id(authed_client: TestClient) -> None:
    response = authed_client.get("/api/library/artifacts")
    assert response.status_code == 422  # FastAPI: missing required query param


def test_library_list_is_project_scoped(
    client: TestClient,
    session_factory,
) -> None:
    """User A can't list pads in user B's project even if they pass its id."""

    # User A creates a project and a pad in it.
    a = client.post(
        "/api/auth/signup", json={"email": "owner-a@example.com", "password": "correct-horse"}
    ).json()
    project_a = client.post("/api/projects", json={"name": "A project"}).json()

    with session_factory() as session:
        conv = Conversation(title="A convo", owner_id=a["id"], project_id=project_a["id"])
        session.add(conv)
        session.flush()
        session.add(
            Artifact(
                conversation_id=conv.id,
                origin_conversation_id=conv.id,
                project_id=project_a["id"],
                title="A pad",
                content="secret",
                content_type="markdown",
                artifact_type="rfc",
                status="active",
                version=1,
            )
        )
        session.commit()

    # User B signs up fresh and tries to read user A's project.
    client.cookies.clear()
    client.post(
        "/api/auth/signup", json={"email": "stranger@example.com", "password": "correct-horse"}
    )
    response = client.get("/api/library/artifacts", params={"project_id": project_a["id"]})
    assert response.status_code == 403
