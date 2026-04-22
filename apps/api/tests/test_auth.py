"""End-to-end tests for the auth surface.

Covers: signup, signin, signout, me, session expiry, reset-request (including
enumeration + cooldown behavior), and reset-confirm (including token reuse,
expiry, and session revocation side-effect).
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.auth import (
    PasswordResetToken,
    SESSION_COOKIE,
    UserSession,
    hash_password,
    verify_password,
)
from app.core import utcnow


# ---------------------------------------------------------------------------
# signup + signin + me + signout
# ---------------------------------------------------------------------------
def test_signup_creates_user_and_sets_cookie(client: TestClient, session_factory) -> None:
    r = client.post(
        "/api/auth/signup",
        json={"email": "NewUser@Example.com", "password": "correct-horse", "name": "Newt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "newuser@example.com"  # normalized
    assert body["name"] == "Newt"
    assert "wp_session" in client.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]


def test_signup_rejects_duplicate_email(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "password": "correct-horse"}
    first = client.post("/api/auth/signup", json=payload)
    assert first.status_code == 200
    # Same email, clear cookies so we're unauthenticated for the second attempt.
    client.cookies.clear()
    second = client.post("/api/auth/signup", json=payload)
    assert second.status_code == 400
    assert "already" in second.json()["detail"].lower()


def test_signup_rejects_short_password(client: TestClient) -> None:
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short"})
    assert r.status_code == 400


def test_signin_with_wrong_password_fails(client: TestClient) -> None:
    client.post("/api/auth/signup", json={"email": "x@y.com", "password": "correct-horse"})
    client.cookies.clear()
    r = client.post("/api/auth/signin", json={"email": "x@y.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_signin_with_correct_password_issues_new_cookie(client: TestClient) -> None:
    client.post("/api/auth/signup", json={"email": "x@y.com", "password": "correct-horse"})
    first_cookie = client.cookies.get("wp_session")
    client.cookies.clear()

    r = client.post("/api/auth/signin", json={"email": "x@y.com", "password": "correct-horse"})
    assert r.status_code == 200
    assert "wp_session" in client.cookies
    # Should be a fresh session, not the signup cookie.
    assert client.cookies.get("wp_session") != first_cookie


def test_signout_revokes_and_clears_cookie(
    authed_client: TestClient, session_factory
) -> None:
    cookie = authed_client.cookies.get("wp_session")
    assert cookie

    r = authed_client.post("/api/auth/signout")
    assert r.status_code == 204

    # Subsequent /me must be unauthenticated.
    authed_client.cookies.set("wp_session", cookie)
    me = authed_client.get("/api/auth/me")
    assert me.status_code == 401

    # And the DB row is marked revoked.
    with session_factory() as session:
        record = session.get(UserSession, cookie)
        assert record is not None
        assert record.revoked_at is not None


def test_me_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_treated_as_anonymous(
    authed_client: TestClient, session_factory
) -> None:
    cookie = authed_client.cookies.get("wp_session")
    with session_factory() as session:
        record = session.get(UserSession, cookie)
        assert record is not None
        record.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()

    assert authed_client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# Password utilities (sanity checks in the public module surface)
# ---------------------------------------------------------------------------
def test_hash_password_round_trips() -> None:
    stored = hash_password("correct-horse")
    assert verify_password("correct-horse", stored)
    assert not verify_password("wrong-pass", stored)
    assert not verify_password("", stored)


# ---------------------------------------------------------------------------
# reset-request
# ---------------------------------------------------------------------------
def test_reset_request_returns_202_for_unknown_email(client: TestClient, caplog) -> None:
    caplog.set_level("INFO", logger="app.main")
    r = client.post("/api/auth/reset-request", json={"email": "nobody@example.com"})
    assert r.status_code == 202
    # Must NOT log a reset URL for an unknown email.
    assert not any("password-reset-url" in rec.message for rec in caplog.records)


def test_reset_request_is_neutral_for_existing_email_and_logs_url(
    client: TestClient, session_factory, caplog
) -> None:
    caplog.set_level("INFO", logger="app.main")
    client.post("/api/auth/signup", json={"email": "real@example.com", "password": "correct-horse"})
    client.cookies.clear()

    r = client.post("/api/auth/reset-request", json={"email": "real@example.com"})
    assert r.status_code == 202
    assert r.json() == {"status": "ok"}

    # URL must be logged (the local-operator mailer substitute).
    logged = [rec.message for rec in caplog.records if "password-reset-url" in rec.message]
    assert logged, "expected password-reset-url to be logged"
    assert "real@example.com" in logged[0]
    assert "token=" in logged[0]

    # A token row exists for the user.
    with session_factory() as session:
        rows = session.query(PasswordResetToken).all()
        assert len(rows) == 1
        assert rows[0].used_at is None


def test_reset_request_rejects_missing_email(client: TestClient) -> None:
    r = client.post("/api/auth/reset-request", json={"email": "  "})
    assert r.status_code == 400


def test_reset_request_cooldown_suppresses_second_issue(
    client: TestClient, session_factory, caplog
) -> None:
    caplog.set_level("INFO", logger="app.main")
    client.post("/api/auth/signup", json={"email": "cd@example.com", "password": "correct-horse"})
    client.cookies.clear()

    assert client.post("/api/auth/reset-request", json={"email": "cd@example.com"}).status_code == 202
    first_count = sum("password-reset-url" in r.message for r in caplog.records)
    assert first_count == 1

    # Immediately re-request: endpoint still returns 202 (neutral), but no
    # new token is created and no URL is logged.
    assert client.post("/api/auth/reset-request", json={"email": "cd@example.com"}).status_code == 202
    second_count = sum("password-reset-url" in r.message for r in caplog.records)
    assert second_count == 1  # unchanged

    with session_factory() as session:
        assert session.query(PasswordResetToken).count() == 1


# ---------------------------------------------------------------------------
# reset-confirm
# ---------------------------------------------------------------------------
def _issue_reset_token(client: TestClient, session_factory, email: str, password: str) -> str:
    """Sign up a user, request a reset, and return the raw token.

    We can't read the raw token out of the DB (only the hash is stored) so we
    parse it from the logged URL in auth.main.
    """

    import logging

    client.post("/api/auth/signup", json={"email": email, "password": password})
    client.cookies.clear()

    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda rec: records.append(rec.getMessage())  # type: ignore[assignment]
    logger = logging.getLogger("app.main")
    logger.addHandler(handler)
    try:
        logger.setLevel(logging.INFO)
        r = client.post("/api/auth/reset-request", json={"email": email})
        assert r.status_code == 202
    finally:
        logger.removeHandler(handler)

    line = next((m for m in records if "password-reset-url" in m), None)
    assert line is not None, records
    token = line.split("token=", 1)[1].strip()
    return token


def test_reset_confirm_updates_password_and_revokes_sessions(
    client: TestClient, session_factory
) -> None:
    email = "reset@example.com"
    token = _issue_reset_token(client, session_factory, email, "correct-horse")

    # Also create a "live" session for this user (simulate a signed-in
    # device that should be kicked out by the reset).
    client.post("/api/auth/signin", json={"email": email, "password": "correct-horse"})
    live_cookie = client.cookies.get("wp_session")
    assert live_cookie

    r = client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "new_password": "new-strong-pass"},
    )
    assert r.status_code == 204

    # Old password no longer works.
    client.cookies.clear()
    bad = client.post("/api/auth/signin", json={"email": email, "password": "correct-horse"})
    assert bad.status_code == 401

    # New password does.
    good = client.post("/api/auth/signin", json={"email": email, "password": "new-strong-pass"})
    assert good.status_code == 200

    # The previously-live session is revoked.
    with session_factory() as session:
        old = session.get(UserSession, live_cookie)
        assert old is not None
        assert old.revoked_at is not None


def test_reset_confirm_marks_token_used_and_rejects_reuse(
    client: TestClient, session_factory
) -> None:
    token = _issue_reset_token(client, session_factory, "once@example.com", "correct-horse")

    first = client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "new_password": "first-new-pass"},
    )
    assert first.status_code == 204

    # Same token can't be replayed.
    second = client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "new_password": "second-attempt"},
    )
    assert second.status_code == 400


def test_reset_confirm_rejects_expired_token(
    client: TestClient, session_factory
) -> None:
    token = _issue_reset_token(client, session_factory, "exp@example.com", "correct-horse")

    with session_factory() as session:
        row = session.query(PasswordResetToken).one()
        row.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()

    r = client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "new_password": "new-strong-pass"},
    )
    assert r.status_code == 400


def test_reset_confirm_rejects_bogus_token(client: TestClient) -> None:
    r = client.post(
        "/api/auth/reset-confirm",
        json={"token": "not-a-real-token", "new_password": "new-strong-pass"},
    )
    assert r.status_code == 400


def test_reset_confirm_rejects_short_password(
    client: TestClient, session_factory
) -> None:
    token = _issue_reset_token(client, session_factory, "short@example.com", "correct-horse")
    r = client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "new_password": "short"},
    )
    assert r.status_code == 400
