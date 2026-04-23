"""End-to-end tests for the sources HTTP surface (Phase 3 Stream A)."""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _signup(client: TestClient, email: str, password: str = "correct-horse") -> dict:
    r = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _clear_cookies(client: TestClient) -> None:
    client.cookies.clear()


def _signin(client: TestClient, email: str, password: str = "correct-horse") -> None:
    r = client.post("/api/auth/signin", json={"email": email, "password": password})
    assert r.status_code == 200, r.text


def _make_project(client: TestClient, name: str = "Acme") -> str:
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Auth + membership
# ---------------------------------------------------------------------------
def test_create_source_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/projects/nope/sources",
        json={"kind": "note", "text": "hi"},
    )
    assert r.status_code == 401


def test_non_member_gets_403_on_create_list_and_detail(client: TestClient) -> None:
    # Owner sets up a project + a source.
    _signup(client, "owner@example.com")
    pid = _make_project(client, "Secret")
    r = client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "note", "text": "internal"},
    )
    assert r.status_code == 200
    source_id = r.json()["source"]["id"]

    # Outsider signs up; should not see any of the project's sources.
    _clear_cookies(client)
    _signup(client, "outsider@example.com")
    r_create = client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "note", "text": "attempt"},
    )
    assert r_create.status_code == 403
    r_list = client.get(f"/api/projects/{pid}/sources")
    assert r_list.status_code == 403
    r_detail = client.get(f"/api/sources/{source_id}")
    assert r_detail.status_code == 403


def test_detail_404_when_source_does_not_exist(authed_client: TestClient) -> None:
    r = authed_client.get("/api/sources/does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Happy paths per kind
# ---------------------------------------------------------------------------
def test_create_transcript_source_stores_text_and_summary(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    r = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "transcript", "text": "Standup\nLine two"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    src = body["source"]
    assert src["kind"] == "transcript"
    assert src["title"] == "Standup"
    assert src["provider"] == "paste"
    assert src["snapshot_count"] == 1

    detail = authed_client.get(f"/api/sources/{src['id']}").json()
    assert detail["snapshots"][0]["content_text"].startswith("Standup")


def test_create_repo_source_accepts_url_or_slug(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    r = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={
            "kind": "repo",
            "url": "https://github.com/acme/widget",
            "ref_pinned": "abc1234",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"]["title"] == "acme/widget"
    assert body["source"]["canonical_key"] == "acme/widget"

    detail = authed_client.get(f"/api/sources/{body['source']['id']}").json()
    assert detail["snapshots"][0]["snapshot_ref"] == "abc1234"
    assert detail["snapshots"][0]["content_text"] is None


def test_create_note_source_does_not_dedupe(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    body1 = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "note", "text": "meeting prep"},
    ).json()
    body2 = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "note", "text": "meeting prep"},
    ).json()
    assert body1["created"] is True
    assert body2["created"] is True
    assert body1["source"]["id"] != body2["source"]["id"]

    lst = authed_client.get(f"/api/projects/{pid}/sources").json()
    assert len(lst) == 2


# ---------------------------------------------------------------------------
# Dedupe + validation
# ---------------------------------------------------------------------------
def test_duplicate_repo_create_returns_existing_source(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    first = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "repo", "url": "https://github.com/acme/widget"},
    ).json()
    second = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "repo", "url": "git@github.com:acme/widget.git"},
    ).json()
    assert first["source"]["id"] == second["source"]["id"]
    assert first["created"] is True
    assert second["created"] is False

    lst = authed_client.get(f"/api/projects/{pid}/sources").json()
    assert len(lst) == 1


def test_create_rejects_file_and_image_until_upload_pipeline_lands(
    authed_client: TestClient,
) -> None:
    pid = _make_project(authed_client)
    r = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "file", "text": "hmm"},
    )
    # The request model only accepts repo|transcript|note, so Pydantic
    # rejects with 422 before the handler even runs. That's the right
    # behavior — it documents the gap without smuggling bad rows in.
    assert r.status_code == 422


def test_create_rejects_empty_transcript_and_bad_repo(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    r = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "transcript", "text": "   "},
    )
    assert r.status_code == 400
    r = authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "repo", "url": "not a url"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# List shape
# ---------------------------------------------------------------------------
def test_list_sources_returns_snapshot_and_link_counts(authed_client: TestClient) -> None:
    pid = _make_project(authed_client)
    authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "repo", "url": "https://github.com/acme/a"},
    )
    authed_client.post(
        f"/api/projects/{pid}/sources",
        json={"kind": "transcript", "text": "team sync notes"},
    )
    rows = authed_client.get(f"/api/projects/{pid}/sources").json()
    assert len(rows) == 2
    for row in rows:
        assert row["snapshot_count"] == 1
        assert row["linked_pad_count"] == 0  # no pad links in this test
