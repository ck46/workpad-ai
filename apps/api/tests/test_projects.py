"""End-to-end tests for the projects + invites surface."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import utcnow
from app.projects import Invite, Project, ProjectMember, ROLE_MEMBER, ROLE_OWNER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _signup(client: TestClient, email: str, password: str = "correct-horse") -> dict[str, str]:
    r = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _clear_cookies(client: TestClient) -> None:
    client.cookies.clear()


def _signin(client: TestClient, email: str, password: str = "correct-horse") -> None:
    r = client.post("/api/auth/signin", json={"email": email, "password": password})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Create / list / detail
# ---------------------------------------------------------------------------
def test_create_project_requires_auth(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "Secret"})
    assert r.status_code == 401


def test_create_project_makes_caller_owner_and_lists_it(
    authed_client: TestClient, authed_user: dict[str, str], session_factory
) -> None:
    r = authed_client.post("/api/projects", json={"name": "Acme"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme"
    assert body["role"] == "owner"

    lst = authed_client.get("/api/projects")
    assert lst.status_code == 200
    payload = lst.json()
    assert len(payload) == 1
    assert payload[0]["id"] == body["id"]
    assert payload[0]["role"] == "owner"

    with session_factory() as session:
        project = session.get(Project, body["id"])
        assert project is not None
        assert project.created_by_user_id == authed_user["id"]
        member = session.query(ProjectMember).filter_by(project_id=project.id).one()
        assert member.user_id == authed_user["id"]
        assert member.role == ROLE_OWNER


def test_create_project_rejects_blank_name(authed_client: TestClient) -> None:
    r = authed_client.post("/api/projects", json={"name": "   "})
    assert r.status_code == 400


def test_list_projects_is_scoped_to_caller(client: TestClient) -> None:
    # User A creates a project.
    _signup(client, "a@example.com")
    r = client.post("/api/projects", json={"name": "A's project"})
    assert r.status_code == 200

    # User B signs up fresh; must not see A's project.
    _clear_cookies(client)
    _signup(client, "b@example.com")
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_project_detail_requires_membership(
    client: TestClient, authed_user: dict[str, str]
) -> None:
    # Create a project owned by authed_user (tester@example.com).
    r = authed_client_helper(client, "Owned by A")

    # Sign in as a different user — must get 403 on the detail endpoint.
    _clear_cookies(client)
    _signup(client, "stranger@example.com")
    r2 = client.get(f"/api/projects/{r['id']}")
    assert r2.status_code == 403


def authed_client_helper(client: TestClient, name: str) -> dict[str, str]:
    """Create a project using the already-signed-in client and return its row."""

    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def test_project_detail_includes_members_and_pending_invites(
    authed_client: TestClient,
) -> None:
    proj = authed_client_helper(authed_client, "Detail test")
    # Issue a pending invite.
    inv = authed_client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "newcomer@example.com"},
    )
    assert inv.status_code == 200

    detail = authed_client.get(f"/api/projects/{proj['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["role"] == "owner"
    assert len(body["members"]) == 1
    assert body["members"][0]["role"] == "owner"
    assert len(body["pending_invites"]) == 1
    assert body["pending_invites"][0]["email"] == "newcomer@example.com"


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------
def test_create_invite_requires_owner_role(
    client: TestClient, session_factory
) -> None:
    # Owner creates project + invite.
    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Teamwork")
    inv = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "friend@example.com"},
    )
    assert inv.status_code == 200
    token = inv.json()["token"]

    # Friend accepts → becomes member (not owner).
    _clear_cookies(client)
    _signup(client, "friend@example.com")
    accept = client.post("/api/invites/accept", json={"token": token})
    assert accept.status_code == 200
    assert accept.json()["role"] == "member"

    # Member tries to issue a new invite — must 403.
    r = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "third@example.com"},
    )
    assert r.status_code == 403


def test_create_invite_returns_accept_url_with_raw_token(
    authed_client: TestClient,
) -> None:
    proj = authed_client_helper(authed_client, "URL test")
    r = authed_client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "u@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["accept_url"].endswith(f"token={body['token']}")
    assert "/#/invite?token=" in body["accept_url"]


def test_create_invite_rejects_invalid_email(authed_client: TestClient) -> None:
    proj = authed_client_helper(authed_client, "Bad email test")
    r = authed_client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "not-an-email"},
    )
    assert r.status_code == 400


def test_accept_invite_adds_caller_as_member_and_marks_used(
    client: TestClient, session_factory
) -> None:
    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Shared")
    inv = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "teammate@example.com"},
    )
    token = inv.json()["token"]

    _clear_cookies(client)
    _signup(client, "teammate@example.com")
    r = client.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == proj["id"]
    assert body["role"] == "member"

    # Teammate now sees the project in their list.
    lst = client.get("/api/projects")
    assert [p["id"] for p in lst.json()] == [proj["id"]]

    with session_factory() as session:
        invite = session.query(Invite).one()
        assert invite.accepted_at is not None

    # Teammate can read the detail endpoint.
    detail = client.get(f"/api/projects/{proj['id']}")
    assert detail.status_code == 200
    assert detail.json()["role"] == "member"


def test_accept_invite_twice_is_rejected(
    client: TestClient,
) -> None:
    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Reuse test")
    token = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "x@example.com"},
    ).json()["token"]

    _clear_cookies(client)
    _signup(client, "x@example.com")
    first = client.post("/api/invites/accept", json={"token": token})
    assert first.status_code == 200

    _clear_cookies(client)
    _signup(client, "y@example.com")
    second = client.post("/api/invites/accept", json={"token": token})
    assert second.status_code == 400


def test_accept_invite_rejects_expired_token(
    client: TestClient, session_factory
) -> None:
    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Expiry test")
    token = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "late@example.com"},
    ).json()["token"]

    # Age the invite past its expiry.
    with session_factory() as session:
        record = session.query(Invite).one()
        record.expires_at = utcnow() - timedelta(hours=1)
        session.commit()

    _clear_cookies(client)
    _signup(client, "late@example.com")
    r = client.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 400


def test_accept_invite_rejects_bogus_token(authed_client: TestClient) -> None:
    r = authed_client.post("/api/invites/accept", json={"token": "not-a-token"})
    assert r.status_code == 400


def test_accept_invite_preserves_existing_membership_role(
    client: TestClient, session_factory
) -> None:
    """If a user is already a member (as owner!), accepting a new invite
    into the same project must not downgrade them to member."""

    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Self-invite test")

    # Owner creates an invite and also has the raw token. (In practice
    # this'd be a second owner doing so, but we only need to simulate the
    # edge case where an owner accepts an invite to their own project.)
    token = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "owner@example.com"},
    ).json()["token"]

    r = client.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 200
    # Role stays owner.
    assert r.json()["role"] == "owner"

    with session_factory() as session:
        members = session.query(ProjectMember).filter_by(project_id=proj["id"]).all()
        assert len(members) == 1
        assert members[0].role == ROLE_OWNER


def test_accept_invite_requires_auth(
    client: TestClient,
) -> None:
    _signup(client, "owner@example.com")
    proj = authed_client_helper(client, "Auth guard test")
    token = client.post(
        f"/api/projects/{proj['id']}/invites",
        json={"email": "a@example.com"},
    ).json()["token"]

    _clear_cookies(client)
    r = client.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 401
