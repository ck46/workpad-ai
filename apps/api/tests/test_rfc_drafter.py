from __future__ import annotations

import pytest

from app.rfc_drafter import RFCDrafter, ToolCallResult


class _StubAI:
    def call_tool(self, call):  # pragma: no cover - never invoked by these tests
        return ToolCallResult(name="", arguments={})


@pytest.fixture
def drafter():
    return RFCDrafter(
        ai_client=_StubAI(),
        github_reader=object(),
        session_factory=lambda: None,
        model="test",
    )


FILES = {"src/auth.py": b"line1\nline2\nline3\nline4\nline5\n"}
BODY = "Claim one [[cite:a1]] and two [[cite:b2]] and three [[cite:c3]] and four [[cite:d4]]."


def test_valid_repo_range_keeps_and_enriches_target(drafter) -> None:
    citations = [
        {
            "anchor": "a1",
            "kind": "repo_range",
            "target": {"repo": "acme/foo", "path": "src/auth.py", "line_start": 2, "line_end": 4},
        }
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations,
        markdown_body=BODY,
        ref_at_draft="sha-x",
        fetched_files=FILES,
    )
    assert dropped == []
    assert valid[0]["target"]["ref_at_draft"] == "sha-x"
    assert valid[0]["target"]["content_hash_at_draft"]
    assert valid[0]["target"]["line_end"] == 4


def test_drops_when_anchor_not_in_body(drafter) -> None:
    citations = [
        {
            "anchor": "zz9",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "src/auth.py", "line_start": 1, "line_end": 2},
        }
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert valid == []
    assert [d["reason"] for d in dropped] == ["anchor_not_in_body"]


def test_drops_when_path_missing(drafter) -> None:
    citations = [
        {
            "anchor": "b2",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "nope.py", "line_start": 1, "line_end": 2},
        }
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert valid == []
    assert [d["reason"] for d in dropped] == ["path_not_in_snapshot"]


def test_drops_line_start_past_eof(drafter) -> None:
    citations = [
        {
            "anchor": "c3",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "src/auth.py", "line_start": 999, "line_end": 1001},
        }
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert valid == []
    assert [d["reason"] for d in dropped] == ["line_start_past_eof"]


def test_clamps_line_end_to_eof(drafter) -> None:
    citations = [
        {
            "anchor": "a1",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "src/auth.py", "line_start": 3, "line_end": 999},
        }
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert dropped == []
    assert valid[0]["target"]["line_end"] == 5  # file has 5 lines


def test_drops_duplicate_anchors_keeping_first(drafter) -> None:
    citations = [
        {
            "anchor": "a1",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "src/auth.py", "line_start": 1, "line_end": 2},
        },
        {
            "anchor": "a1",
            "kind": "repo_range",
            "target": {"repo": "r", "path": "src/auth.py", "line_start": 3, "line_end": 4},
        },
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert len(valid) == 1 and valid[0]["target"]["line_start"] == 1
    assert [d["reason"] for d in dropped] == ["duplicate_anchor"]


def test_transcript_range_requires_start_and_end(drafter) -> None:
    citations = [
        {"anchor": "a1", "kind": "transcript_range", "target": {"start": "00:00:10", "end": "00:00:30"}},
        {"anchor": "b2", "kind": "transcript_range", "target": {"start": None, "end": "00:00:30"}},
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert len(valid) == 1 and valid[0]["anchor"] == "a1"
    assert [d["reason"] for d in dropped] == ["incomplete_transcript_range"]


def test_repo_pr_requires_positive_integer(drafter) -> None:
    citations = [
        {"anchor": "a1", "kind": "repo_pr", "target": {"repo": "r", "number": 42, "title_at_draft": "Fix"}},
        {"anchor": "b2", "kind": "repo_pr", "target": {"repo": "r", "number": 0, "title_at_draft": "Bad"}},
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert len(valid) == 1 and valid[0]["target"]["number"] == 42
    assert [d["reason"] for d in dropped] == ["invalid_pr_number"]


def test_repo_commit_requires_7_plus_char_sha(drafter) -> None:
    citations = [
        {"anchor": "a1", "kind": "repo_commit", "target": {"repo": "r", "sha": "abcdef1"}},
        {"anchor": "b2", "kind": "repo_commit", "target": {"repo": "r", "sha": "short"}},
    ]
    valid, dropped = drafter._validate_citations(
        citations=citations, markdown_body=BODY, ref_at_draft="sha", fetched_files=FILES
    )
    assert len(valid) == 1 and valid[0]["target"]["sha"] == "abcdef1"
    assert [d["reason"] for d in dropped] == ["invalid_commit_sha"]
