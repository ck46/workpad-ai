from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.core import Artifact, Citation
from app.github_client import CachedGitHubReader, GitHubClient
from app.rfc_drafter import ModelCall, RFCDrafter, ToolCallResult
from app.sources import (
    KIND_REPO,
    KIND_TRANSCRIPT,
    PadSourceLink,
    Source,
    SourceSnapshot,
)


SAMPLE_FILE = b"def login(user):\n    return True\n\n\ndef logout(user):\n    return None\n"


@dataclass
class _ScriptedAI:
    """Replays a list of ToolCallResults in order. One per call_tool() call."""

    responses: list[ToolCallResult]
    received: list[ModelCall]

    def call_tool(self, call: ModelCall) -> ToolCallResult:
        self.received.append(call)
        if not self.responses:
            raise AssertionError("Scripted AI ran out of responses")
        return self.responses.pop(0)


def _github_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/repos/acme/foo":
        return httpx.Response(200, json={"default_branch": "main"})
    if path == "/repos/acme/foo/branches/main":
        return httpx.Response(200, json={"commit": {"sha": "draft-sha"}})
    if path.endswith("/git/trees/draft-sha"):
        return httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "README.md", "type": "blob"},
                    {"path": "src/auth.py", "type": "blob"},
                    {"path": "src/rate.py", "type": "blob"},
                ]
            },
        )
    if path == "/repos/acme/foo/contents/README.md":
        return httpx.Response(
            200,
            headers={"ETag": "e-readme"},
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"# Foo\nAuth + rate limits.").decode(),
                "sha": "r",
            },
        )
    if path == "/repos/acme/foo/contents/src/auth.py":
        return httpx.Response(
            200,
            headers={"ETag": "e-auth"},
            json={
                "encoding": "base64",
                "content": base64.b64encode(SAMPLE_FILE).decode(),
                "sha": "a",
            },
        )
    return httpx.Response(404, json={"message": "not found"})


def test_end_to_end_draft_persists_artifact_sources_and_citations(session_factory) -> None:
    from app.auth import User, hash_password
    from app.projects import ensure_personal_project

    # Drafter now requires a project_id + user_id. Set one of each up.
    with session_factory() as session:
        user = User(email="e2e@example.com", password_hash=hash_password("correct-horse"))
        session.add(user)
        session.flush()
        project = ensure_personal_project(session, user.id)
        session.commit()
        project_id = project.id
        user_id = user.id

    client = GitHubClient("test-token", transport=httpx.MockTransport(_github_handler))
    reader = CachedGitHubReader(client, session_factory)

    ai = _ScriptedAI(
        received=[],
        responses=[
            ToolCallResult(
                name="pick_relevant_files",
                arguments={
                    "paths": ["src/auth.py", "bogus.py", "src/auth.py"],  # deduped + filtered
                    "reasoning": "auth was the subject",
                },
            ),
            ToolCallResult(
                name="draft_rfc",
                arguments={
                    "title": "Rework authentication",
                    "markdown_body": (
                        "# Rework authentication\n"
                        "The login handler returns True unconditionally [[cite:auth1]]. "
                        "The team discussed this at [[cite:tr1]]."
                    ),
                    "citations": [
                        {
                            "anchor": "auth1",
                            "kind": "repo_range",
                            "repo": "acme/foo",
                            "path": "src/auth.py",
                            "line_start": 1,
                            "line_end": 2,
                            "pr_number": None,
                            "pr_title_at_draft": None,
                            "commit_sha": None,
                            "transcript_start": None,
                            "transcript_end": None,
                        },
                        {
                            "anchor": "tr1",
                            "kind": "transcript_range",
                            "repo": None,
                            "path": None,
                            "line_start": None,
                            "line_end": None,
                            "pr_number": None,
                            "pr_title_at_draft": None,
                            "commit_sha": None,
                            "transcript_start": "00:00:12",
                            "transcript_end": "00:00:45",
                        },
                    ],
                },
            ),
        ],
    )

    drafter = RFCDrafter(
        ai_client=ai,
        github_reader=reader,
        session_factory=session_factory,
        model="test-model",
    )

    transcript = (
        "00:00:12 Alex: The login handler returns True no matter what.\n"
        "00:00:45 Sam: We need proper verification before this ships.\n"
    )
    result = drafter.draft(
        user_id=user_id,
        conversation_id=None,
        project_id=project_id,
        transcript=transcript,
        repo="acme/foo",
    )

    # Model was forced to call each tool in order.
    assert [call.tool_choice_name for call in ai.received] == ["pick_relevant_files", "draft_rfc"]

    # Pinned ref made it into the result.
    assert result.ref_at_draft == "draft-sha"
    # Only src/auth.py survived the file filter.
    assert result.picked_paths == ["src/auth.py"]

    with session_factory() as session:
        artifact = session.get(Artifact, result.artifact_id)
        assert artifact is not None
        assert artifact.spec_type == "rfc"
        assert artifact.title == "Rework authentication"
        assert "login handler" in artifact.content

        links = session.query(PadSourceLink).filter_by(pad_id=artifact.id).all()
        assert len(links) == 2
        assert all(link.added_by_system for link in links)
        sources_by_kind = {
            s.kind: s
            for s in session.query(Source)
            .filter(Source.id.in_([link.source_id for link in links]))
            .all()
        }
        assert set(sources_by_kind) == {KIND_TRANSCRIPT, KIND_REPO}

        # Repo source keeps the draft-time ref on its snapshot.
        repo_source = sources_by_kind[KIND_REPO]
        repo_snapshot = (
            session.query(SourceSnapshot)
            .filter_by(source_id=repo_source.id)
            .one()
        )
        assert repo_snapshot.snapshot_ref == "draft-sha"

        # Transcript source preserves segments in provenance_json.
        transcript_source = sources_by_kind[KIND_TRANSCRIPT]
        assert transcript_source.provenance_json.get("segments") is not None
        assert len(transcript_source.provenance_json["segments"]) == 2

        citations = (
            session.query(Citation)
            .filter(Citation.artifact_id == artifact.id)
            .order_by(Citation.anchor.asc())
            .all()
        )
        assert [c.anchor for c in citations] == ["auth1", "tr1"]

        auth_c = next(c for c in citations if c.anchor == "auth1")
        assert auth_c.kind == "repo_range"
        assert auth_c.target["path"] == "src/auth.py"
        assert auth_c.target["ref_at_draft"] == "draft-sha"
        assert auth_c.target["content_hash_at_draft"]

        tr_c = next(c for c in citations if c.anchor == "tr1")
        assert tr_c.kind == "transcript_range"
        assert tr_c.target["start"] == "00:00:12"
