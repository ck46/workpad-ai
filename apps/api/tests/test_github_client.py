from __future__ import annotations

import httpx
import pytest

from app.github_client import (
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    RATE_LIMIT_BUFFER,
)


def _make(handler) -> GitHubClient:
    return GitHubClient("test-token", transport=httpx.MockTransport(handler))


def test_rate_limit_headers_are_captured_on_success() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Reset": "1700000000"},
            json={"tree": []},
        )

    with _make(handler) as client:
        client.get_tree("a/b", "main")
        assert client.rate_limit_remaining == 4999
        assert client.rate_limit_reset == 1700000000


def test_403_with_remaining_zero_raises_rate_limit_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
            json={"message": "API rate limit exceeded"},
        )

    with _make(handler) as client, pytest.raises(GitHubRateLimitError):
        client.get_tree("a/b", "main")


def test_403_without_rate_limit_headers_is_auth_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "bad token"})

    with _make(handler) as client, pytest.raises(GitHubAuthError):
        client.get_tree("a/b", "main")


def test_preemptive_guard_fails_fast_below_buffer() -> None:
    call_count = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Remaining": str(RATE_LIMIT_BUFFER - 1),
                "X-RateLimit-Reset": "1700000000",
            },
            json={"tree": []},
        )

    with _make(handler) as client:
        client.get_tree("a/b", "main")  # first call returns; now below buffer
        with pytest.raises(GitHubRateLimitError):
            client.get_tree("a/b", "main")

    # The second call must be blocked BEFORE the HTTP request fires.
    assert call_count["n"] == 1


def test_404_maps_to_not_found() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with _make(handler) as client, pytest.raises(GitHubNotFoundError):
        client.get_tree("a/b", "does-not-exist")
