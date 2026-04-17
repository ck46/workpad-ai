from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core import RepoCache, utcnow
from app.github_client import CachedGitHubReader, GitHubClient, GitHubRequestError


ETAG = 'W/"etag-1"'


def _client(handler) -> GitHubClient:
    return GitHubClient("test-token", transport=httpx.MockTransport(handler))


def test_cache_miss_populates_row(session_factory) -> None:
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("if-none-match"))
        return httpx.Response(
            200,
            headers={"ETag": ETAG},
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"hello").decode(),
                "sha": "blob-1",
            },
        )

    reader = CachedGitHubReader(_client(handler), session_factory)
    result = reader.get_file("acme/foo", "main", "README.md")

    assert result.content == b"hello"
    assert calls == [None]

    with session_factory() as session:
        row = session.query(RepoCache).one()
        assert row.repo == "acme/foo"
        assert row.ref == "main"
        assert row.path == "README.md"
        assert row.etag == ETAG
        assert row.content == b"hello"


def test_cache_hit_revalidates_with_etag_and_serves_cached_on_304(session_factory) -> None:
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        incoming = request.headers.get("if-none-match")
        calls.append(incoming)
        if incoming == ETAG:
            return httpx.Response(304, headers={"ETag": ETAG})
        return httpx.Response(
            200,
            headers={"ETag": ETAG},
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"hello").decode(),
                "sha": "blob-1",
            },
        )

    reader = CachedGitHubReader(_client(handler), session_factory)

    first = reader.get_file("acme/foo", "main", "README.md")
    second = reader.get_file("acme/foo", "main", "README.md")

    assert first.content == b"hello"
    assert second.content == b"hello"
    assert calls == [None, ETAG]


def test_cache_hit_overwrites_row_when_server_returns_200(session_factory) -> None:
    state = {"phase": "first"}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["phase"] == "first":
            state["phase"] = "second"
            return httpx.Response(
                200,
                headers={"ETag": ETAG},
                json={
                    "encoding": "base64",
                    "content": base64.b64encode(b"v1").decode(),
                    "sha": "blob-1",
                },
            )
        return httpx.Response(
            200,
            headers={"ETag": 'W/"etag-2"'},
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"v2").decode(),
                "sha": "blob-2",
            },
        )

    reader = CachedGitHubReader(_client(handler), session_factory)
    first = reader.get_file("acme/foo", "main", "README.md")
    second = reader.get_file("acme/foo", "main", "README.md")

    assert first.content == b"v1"
    assert second.content == b"v2"

    with session_factory() as session:
        row = session.query(RepoCache).one()
        assert row.content == b"v2"
        assert row.etag == 'W/"etag-2"'


def test_ttl_shortcircuits_etag_less_entries(session_factory) -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"fresh").decode(),
                "sha": "blob",
            },
        )

    with session_factory() as session:
        session.add(
            RepoCache(
                repo="acme/foo",
                ref="main",
                path="x.md",
                content=b"cached-bytes",
                content_hash="h",
                etag=None,
                fetched_at=utcnow(),
            )
        )
        session.commit()

    reader = CachedGitHubReader(_client(handler), session_factory)
    within_ttl = reader.get_file("acme/foo", "main", "x.md")
    assert within_ttl.content == b"cached-bytes"
    assert hits == []

    with session_factory() as session:
        row = session.query(RepoCache).one()
        row.fetched_at = datetime.now(UTC) - timedelta(days=2)
        session.commit()

    expired = reader.get_file("acme/foo", "main", "x.md")
    assert expired.content == b"fresh"
    assert hits == ["/repos/acme/foo/contents/x.md"]


def test_304_without_cache_raises(session_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304)

    reader = CachedGitHubReader(_client(handler), session_factory)
    with pytest.raises(GitHubRequestError):
        reader.get_file("acme/foo", "main", "ghost.md")
