from __future__ import annotations

import base64

import httpx

from app.citation_verifier import CitationVerifier
from app.core import Artifact, Citation, Conversation
from app.github_client import CachedGitHubReader, GitHubClient
from app.hashing import content_hash_for_range


PINNED_BYTES = (
    b"import os\n\n"
    b"def login(user):\n"
    b"    return True\n\n"
    b"def logout(user):\n"
    b"    return None\n"
)
# login moved down 3 lines after inserting an import + logger setup.
HEAD_BYTES = (
    b"import os\n"
    b"import logging\n\n"
    b"logger = logging.getLogger(__name__)\n\n"
    b"def login(user):\n"
    b"    return True\n\n"
    b"def logout(user):\n"
    b"    return None\n"
)


def _seed_artifact(session, *, ref_at_draft: str, pinned_hash: str) -> tuple[str, str]:
    conversation = Conversation(title="Login RFC")
    session.add(conversation)
    session.flush()

    artifact = Artifact(
        conversation_id=conversation.id,
        title="Login RFC",
        content="Body [[cite:login1]] and [[cite:missing1]]",
        content_type="markdown",
        spec_type="rfc",
        version=1,
    )
    session.add(artifact)
    session.flush()

    session.add(
        Citation(
            artifact_id=artifact.id,
            anchor="login1",
            kind="repo_range",
            target={
                "repo": "acme/foo",
                "path": "src/auth.py",
                "line_start": 3,
                "line_end": 4,
                "ref_at_draft": ref_at_draft,
                "content_hash_at_draft": pinned_hash,
            },
            resolved_state="unknown",
        )
    )
    session.add(
        Citation(
            artifact_id=artifact.id,
            anchor="missing1",
            kind="repo_range",
            target={
                "repo": "acme/foo",
                "path": "src/gone.py",
                "line_start": 1,
                "line_end": 2,
                "ref_at_draft": ref_at_draft,
                "content_hash_at_draft": "deadbeef" * 8,
            },
            resolved_state="unknown",
        )
    )
    session.commit()
    return artifact.id, conversation.id


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/repos/acme/foo":
        return httpx.Response(200, json={"default_branch": "main"})
    if path == "/repos/acme/foo/branches/main":
        return httpx.Response(200, json={"commit": {"sha": "sha-head"}})
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
    if path == "/repos/acme/foo/contents/src/gone.py":
        return httpx.Response(404, json={"message": "not found"})
    return httpx.Response(404, json={"message": "not found"})


def test_drift_detection_marks_stale_with_suggested_range_and_missing_paths(session_factory):
    pinned_hash = content_hash_for_range(PINNED_BYTES, 3, 4)

    with session_factory() as session:
        artifact_id, _ = _seed_artifact(session, ref_at_draft="sha-pinned", pinned_hash=pinned_hash)

    client = GitHubClient("test-token", transport=httpx.MockTransport(_handler))
    reader = CachedGitHubReader(client, session_factory)
    verifier = CitationVerifier(github_reader=reader)

    with session_factory() as session:
        citations = (
            session.query(Citation)
            .filter(Citation.artifact_id == artifact_id)
            .order_by(Citation.anchor.asc())
            .all()
        )
        result = verifier.verify(artifact_id=artifact_id, citations=citations, session=session)

    assert result.counts_by_state() == {"live": 0, "stale": 1, "missing": 1, "unknown": 0}
    assert result.truncated is False
    assert result.remaining == 0

    with session_factory() as session:
        rows = {
            row.anchor: row
            for row in session.query(Citation)
            .filter(Citation.artifact_id == artifact_id)
            .all()
        }

    stale = rows["login1"]
    assert stale.resolved_state == "stale"
    assert stale.last_checked_at is not None
    assert stale.last_observed is not None
    assert stale.last_observed["suggested_range"] == {"line_start": 6, "line_end": 7}

    missing = rows["missing1"]
    assert missing.resolved_state == "missing"
    assert missing.last_observed["reason"] == "path_gone"
