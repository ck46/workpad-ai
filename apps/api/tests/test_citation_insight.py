from __future__ import annotations

import base64
from contextlib import contextmanager

import httpx
import pytest

from app.core import Artifact, Citation, Conversation
from app.github_client import CachedGitHubReader, GitHubClient
from app.spec_service import CitationInsightService


PINNED_BYTES = (
    b"import os\n"
    b"\n"
    b"def login(user):\n"
    b"    return True\n"
    b"\n"
    b"def logout(user):\n"
    b"    return None\n"
)

HEAD_BYTES = (
    b"import os\n"
    b"import logging\n"
    b"\n"
    b"logger = logging.getLogger(__name__)\n"
    b"\n"
    b"def login(user):\n"
    b"    return True\n"
    b"\n"
    b"def logout(user):\n"
    b"    return None\n"
)


def _seed(session, *, observed_at_ref="sha-head", suggested=None) -> tuple[str, str]:
    conv = Conversation(title="RFC")
    session.add(conv)
    session.flush()
    artifact = Artifact(
        conversation_id=conv.id,
        title="Login RFC",
        content="body [[cite:login1]]",
        content_type="markdown",
        spec_type="rfc",
        version=1,
    )
    session.add(artifact)
    session.flush()
    citation = Citation(
        artifact_id=artifact.id,
        anchor="login1",
        kind="repo_range",
        target={
            "repo": "acme/foo",
            "path": "src/auth.py",
            "line_start": 3,
            "line_end": 4,
            "ref_at_draft": "sha-pinned",
            "content_hash_at_draft": "dead",
        },
        resolved_state="stale",
        last_observed={
            "at_ref": observed_at_ref,
            "suggested_range": suggested,
        } if suggested else {"at_ref": observed_at_ref},
    )
    session.add(citation)
    session.commit()
    return artifact.id, citation.id


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/repos/acme/foo/contents/src/auth.py":
        ref = request.url.params.get("ref")
        content = PINNED_BYTES if ref == "sha-pinned" else HEAD_BYTES
        return httpx.Response(
            200,
            headers={"ETag": f"e-{ref}"},
            json={
                "encoding": "base64",
                "content": base64.b64encode(content).decode(),
                "sha": f"blob-{ref}",
            },
        )
    return httpx.Response(404, json={"message": "not found"})


@contextmanager
def _swap_reader(service, session_factory):
    """Replace the service's _reader() with one wired to a MockTransport."""

    client = GitHubClient("test-token", transport=httpx.MockTransport(_handler))
    reader = CachedGitHubReader(client, session_factory)
    original = service._reader
    service._reader = lambda: (reader, client)
    service._settings.github_default_token = "test-token"
    try:
        yield
    finally:
        client.close()
        service._reader = original


def test_preview_repo_range_returns_highlighted_window(session_factory):
    with session_factory() as session:
        _, citation_id = _seed(
            session,
            observed_at_ref="sha-head",
            suggested={"line_start": 6, "line_end": 7},
        )

    service = CitationInsightService()
    service._session_factory = session_factory

    with _swap_reader(service, session_factory):
        result = service.preview(citation_id)

    assert result["kind"] == "repo_range"
    assert result["at_ref"] == "sha-head"
    assert result["target_start"] == 6
    assert result["target_end"] == 7
    assert result["context_start"] == 3
    assert result["context_end"] == 10
    highlighted = [line for line in result["lines"] if line["highlighted"]]
    assert len(highlighted) == 2
    assert all("def login" in line["text"] or "return True" in line["text"] for line in highlighted)


def test_diff_returns_unified_diff_and_slices(session_factory):
    with session_factory() as session:
        # Point the pinned range at "import os" (line 1) and the observed range
        # at "import logging" (line 2 in HEAD) so the slices actually diverge.
        _, citation_id = _seed(
            session,
            observed_at_ref="sha-head",
            suggested={"line_start": 2, "line_end": 2},
        )
        citation = session.get(Citation, citation_id)
        citation.target = {
            **(citation.target or {}),
            "line_start": 1,
            "line_end": 1,
        }
        session.commit()

    service = CitationInsightService()
    service._session_factory = session_factory

    with _swap_reader(service, session_factory):
        result = service.diff(citation_id)

    assert result["kind"] == "repo_range"
    assert result["pinned_ref"] == "sha-pinned"
    assert result["head_ref"] == "sha-head"
    assert result["pinned_range"] == {"line_start": 1, "line_end": 1}
    assert result["head_range"] == {"line_start": 2, "line_end": 2}
    # Divergent slices -> unified diff contains both old and new content.
    assert "-import os" in result["unified_diff"]
    assert "+import logging" in result["unified_diff"]
    assert result["pinned_lines"][0]["text"] == "import os"
    assert result["head_lines"][0]["text"] == "import logging"


def test_diff_raises_for_non_repo_range_citations(session_factory):
    with session_factory() as session:
        conv = Conversation(title="RFC")
        session.add(conv)
        session.flush()
        artifact = Artifact(
            conversation_id=conv.id,
            title="RFC",
            content="body",
            content_type="markdown",
            spec_type="rfc",
            version=1,
        )
        session.add(artifact)
        session.flush()
        citation = Citation(
            artifact_id=artifact.id,
            anchor="tr1",
            kind="transcript_range",
            target={"start": "00:00:10", "end": "00:00:30"},
            resolved_state="live",
        )
        session.add(citation)
        session.commit()
        citation_id = citation.id

    service = CitationInsightService()
    service._session_factory = session_factory
    service._settings.github_default_token = "test-token"

    with pytest.raises(ValueError):
        service.diff(citation_id)
