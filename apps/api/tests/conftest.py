from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import core
from app.core import Base

# Import side-effect: register auth models on Base.metadata so the in-memory
# schema includes ``users`` and ``user_sessions`` tables.
from app import auth  # noqa: F401


def _clear_cached(fn) -> None:
    # The ``client`` fixture monkey-patches ``core.get_session_factory`` with a
    # plain lambda, which loses ``cache_clear``. Be defensive so the autouse
    # teardown still works when cleanup runs before monkeypatch.undo.
    clear = getattr(fn, "cache_clear", None)
    if clear is not None:
        clear()


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate module-level lru_caches so each test picks up fresh settings."""

    _clear_cached(core.get_settings)
    _clear_cached(core.get_engine)
    _clear_cached(core.get_session_factory)
    yield
    _clear_cached(core.get_settings)
    _clear_cached(core.get_engine)
    _clear_cached(core.get_session_factory)


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


# ---------------------------------------------------------------------------
# HTTP test client + auth helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def client(session_factory, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A FastAPI TestClient wired to the in-memory session factory.

    Does NOT authenticate. Endpoints guarded by ``get_current_user`` will
    return 401. Use ``authed_client`` or ``authed_user`` for tests that
    need a signed-in caller.
    """

    from app import auth as auth_module
    from app import core as core_module
    from app import main as main_module

    # Replace the cached getter on both ``core`` and ``auth`` (auth rebinds it
    # at import time, so patching core alone isn't enough) plus the module-
    # level ``session_factory`` in main. Without all three, the auth dependency
    # would resolve sessions against a different in-memory DB than the one the
    # route handlers write to.
    factory_getter = lambda: session_factory  # noqa: E731
    monkeypatch.setattr(core_module, "get_session_factory", factory_getter)
    monkeypatch.setattr(auth_module, "get_session_factory", factory_getter)
    monkeypatch.setattr(main_module, "session_factory", session_factory)
    monkeypatch.setattr(main_module, "init_db", lambda: None)

    with TestClient(main_module.app) as api_client:
        yield api_client


@pytest.fixture
def authed_user(client: TestClient) -> dict[str, str]:
    """Sign up a default test user and leave the TestClient's cookies set.

    Returns the user payload so tests can assert against ``id`` / ``email``.
    After this fixture runs, ``client`` will carry a valid session cookie
    on subsequent requests.
    """

    response = client.post(
        "/api/auth/signup",
        json={"email": "tester@example.com", "password": "correct-horse", "name": "Tester"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def authed_client(client: TestClient, authed_user: dict[str, str]) -> TestClient:
    """A TestClient already signed in as ``authed_user``."""

    return client
