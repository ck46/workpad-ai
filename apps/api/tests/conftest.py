from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import core
from app.core import Base


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate module-level lru_caches so each test picks up fresh settings."""

    core.get_settings.cache_clear()
    core.get_engine.cache_clear()
    core.get_session_factory.cache_clear()
    yield
    core.get_settings.cache_clear()
    core.get_engine.cache_clear()
    core.get_session_factory.cache_clear()


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
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
