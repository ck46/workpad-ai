"""Cross-project isolation + project_id validation at endpoint boundaries.

These tests sit on top of the project-scoping refactor (Phase 1D-3). They
verify that a user who knows a pad/conversation/project id in a project
they aren't a member of gets 403, that create endpoints reject
non-existent or non-member project_ids, and that missing project_id on
list endpoints is rejected by FastAPI before reaching our handlers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _signup(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/auth/signup", json={"email": email, "password": "correct-horse"})
    assert r.status_code == 200, r.text
    return r.json()


def _create_project(client: TestClient, name: str) -> dict[str, str]:
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _create_pad(client: TestClient, project_id: str, title: str = "A pad") -> dict[str, str]:
    r = client.post(
        "/api/library/artifacts",
        json={
            "project_id": project_id,
            "title": title,
            "content": "body",
            "content_type": "markdown",
            "artifact_type": "adr",
            "status": "draft",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Cross-project pad isolation
# ---------------------------------------------------------------------------
def test_non_member_cannot_read_pad_in_foreign_project(client: TestClient) -> None:
    """Holding a pad id from another project is not enough — the project
    membership check trumps 'I know the id'."""

    _signup(client, "a@example.com")
    project_a = _create_project(client, "A")
    pad = _create_pad(client, project_a["id"], "Secret pad")
    pad_id = pad["id"]

    # User B signs up fresh and tries every pad-level endpoint.
    client.cookies.clear()
    _signup(client, "b@example.com")

    assert client.get(f"/api/library/artifacts/{pad_id}").status_code == 403
    assert client.get(f"/api/artifacts/{pad_id}").status_code == 403
    assert (
        client.put(
            f"/api/library/artifacts/{pad_id}",
            json={
                "title": "Hijacked",
                "content": "pwned",
                "content_type": "markdown",
                "expected_version": pad["version"],
            },
        ).status_code
        == 403
    )
    assert client.get(f"/api/artifacts/{pad_id}/diff").status_code == 403
    assert (
        client.get(f"/api/artifacts/{pad_id}/export", params={"format": "markdown"}).status_code
        == 403
    )


def test_non_member_cannot_read_conversation_in_foreign_project(
    client: TestClient,
) -> None:
    _signup(client, "a@example.com")
    project_a = _create_project(client, "A")
    conv_resp = client.post(
        "/api/conversations",
        json={"project_id": project_a["id"], "seed_title": "Private"},
    )
    assert conv_resp.status_code == 200
    conv_id = conv_resp.json()["id"]

    client.cookies.clear()
    _signup(client, "b@example.com")

    assert client.get(f"/api/conversations/{conv_id}").status_code == 403
    assert client.post(f"/api/conversations/{conv_id}/archive").status_code == 403
    assert client.post(f"/api/conversations/{conv_id}/unarchive").status_code == 403
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 403


# ---------------------------------------------------------------------------
# Create-time project_id validation
# ---------------------------------------------------------------------------
def test_create_pad_in_foreign_project_403s(client: TestClient) -> None:
    _signup(client, "a@example.com")
    project_a = _create_project(client, "A")

    client.cookies.clear()
    _signup(client, "b@example.com")

    r = client.post(
        "/api/library/artifacts",
        json={
            "project_id": project_a["id"],
            "title": "Smuggled",
            "content": "",
            "content_type": "markdown",
            "artifact_type": "adr",
            "status": "draft",
        },
    )
    assert r.status_code == 403


def test_create_conversation_in_unknown_project_403s(authed_client: TestClient) -> None:
    """A project_id that doesn't exist is 403 (the same outcome as non-
    member — no need to distinguish, and it avoids leaking existence)."""

    r = authed_client.post(
        "/api/conversations",
        json={"project_id": "00000000-0000-0000-0000-000000000000", "seed_title": "x"},
    )
    assert r.status_code == 403


def test_create_pad_with_conversation_from_other_project_400s(client: TestClient) -> None:
    """Attaching a pad to a conversation that's in a different project
    must not smuggle it across projects."""

    # User A owns two projects and a conversation in project 1.
    _signup(client, "a@example.com")
    project_1 = _create_project(client, "One")
    project_2 = _create_project(client, "Two")
    conv_1 = client.post(
        "/api/conversations",
        json={"project_id": project_1["id"], "seed_title": "conv-in-one"},
    ).json()

    # User A is in both. Try to create a pad *in project_2* but link to
    # the conversation from project_1.
    r = client.post(
        "/api/library/artifacts",
        json={
            "project_id": project_2["id"],
            "conversation_id": conv_1["id"],
            "title": "Confused pad",
            "content": "",
            "content_type": "markdown",
            "artifact_type": "adr",
            "status": "draft",
        },
    )
    assert r.status_code == 400
    assert "different project" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Query-string contract
# ---------------------------------------------------------------------------
def test_conversations_list_requires_project_id(authed_client: TestClient) -> None:
    r = authed_client.get("/api/conversations")
    assert r.status_code == 422


def test_conversations_list_for_foreign_project_403s(client: TestClient) -> None:
    _signup(client, "a@example.com")
    project_a = _create_project(client, "A")

    client.cookies.clear()
    _signup(client, "b@example.com")

    r = client.get("/api/conversations", params={"project_id": project_a["id"]})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Invited-member can read everything in the project
# ---------------------------------------------------------------------------
def test_invited_member_can_read_project_library_and_conversations(
    client: TestClient,
) -> None:
    _signup(client, "owner@example.com")
    project = _create_project(client, "Team project")
    pad = _create_pad(client, project["id"], "Team pad")
    invite_token = client.post(
        f"/api/projects/{project['id']}/invites",
        json={"email": "member@example.com"},
    ).json()["token"]

    # Member joins.
    client.cookies.clear()
    _signup(client, "member@example.com")
    accept = client.post("/api/invites/accept", json={"token": invite_token})
    assert accept.status_code == 200

    # And can read everything the owner put in.
    library = client.get("/api/library/artifacts", params={"project_id": project["id"]})
    assert library.status_code == 200
    assert [p["id"] for p in library.json()] == [pad["id"]]

    detail = client.get(f"/api/library/artifacts/{pad['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Team pad"
