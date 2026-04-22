"""
User accounts and session cookies.

One-user-per-workspace is the v1 intent, but the schema supports multiple
users so that future sharing / multi-device work doesn't need a rewrite.

Storage: SQLite tables ``users`` and ``user_sessions``. Sessions are
opaque IDs in an HttpOnly ``wp_session`` cookie — signed cookies or JWTs
are overkill for a single-server single-SQLite deployment.

Password hashing: stdlib ``hashlib.scrypt``. Keeps the dep footprint zero.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Cookie, HTTPException, Request, Response
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .core import Base, get_session_factory, utcnow


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16
_MAX_PASSWORD_BYTES = 1024

SESSION_COOKIE = "wp_session"
SESSION_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


# ---------------------------------------------------------------------------
# Password hashing (scrypt, stdlib)
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    if not plain or len(plain.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValueError("password missing or too long")
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    if not plain or not stored:
        return False
    if len(plain.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        return False
    try:
        kind, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, MemoryError):
        return False
    return secrets.compare_digest(digest, expected)


# ---------------------------------------------------------------------------
# User + session helpers
# ---------------------------------------------------------------------------
def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(session: Session, *, email: str, password: str, name: str = "") -> User:
    clean_email = normalize_email(email)
    if not clean_email or "@" not in clean_email:
        raise ValueError("invalid email")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if find_user_by_email(session, clean_email) is not None:
        raise ValueError("email already in use")
    user = User(email=clean_email, name=name.strip()[:240], password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_session(session: Session, user_id: str) -> UserSession:
    sid = secrets.token_urlsafe(32)
    now = utcnow()
    record = UserSession(
        id=sid,
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def resolve_session(session: Session, sid: str | None) -> User | None:
    if not sid:
        return None
    record = session.get(UserSession, sid)
    if record is None or record.revoked_at is not None:
        return None
    if record.expires_at.replace(tzinfo=UTC) < utcnow():
        return None
    return session.get(User, record.user_id)


def revoke_session(session: Session, sid: str) -> None:
    record = session.get(UserSession, sid)
    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()
        session.commit()


# ---------------------------------------------------------------------------
# FastAPI dependencies + cookie helpers
# ---------------------------------------------------------------------------
def get_current_user(
    wp_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    factory = get_session_factory()
    with factory() as session:
        user = resolve_session(session, wp_session)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def get_current_user_optional(
    wp_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User | None:
    factory = get_session_factory()
    with factory() as session:
        return resolve_session(session, wp_session)


def set_session_cookie(request: Request, response: Response, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# Public accessor so callers don't need to import private helpers
def read_cookie_session_id(wp_session: str | None) -> str | None:
    return wp_session or None
