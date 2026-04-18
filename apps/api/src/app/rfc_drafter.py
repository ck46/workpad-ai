"""Two-pass RFC drafter used by the v1 spec flow.

Pass 1 sends the model a cheap repo *index* (tree + README + manifest) and
a ``pick_relevant_files`` tool. The model returns up to 15 paths it thinks
matter for drafting. Pass 2 fetches those files in full and calls
``draft_rfc`` to produce a citation-annotated RFC.

This module holds only the tool schemas for now; the class that drives the
two passes is added in subsequent commits.
"""

from __future__ import annotations

from typing import Any


#: How many file paths Pass 1 is allowed to return. Keeps Pass 2 prompts
#: bounded regardless of repo size.
MAX_RELEVANT_FILES = 15


PICK_RELEVANT_FILES_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "pick_relevant_files",
    "description": (
        "Given a meeting transcript and a repo index (file tree, README, "
        "manifest), return the file paths most likely to matter for "
        "drafting an RFC. Include paths mentioned explicitly, paths that "
        "implement features discussed, and paths the RFC is likely to "
        "modify. Do not guess - only return paths that appear in the "
        "provided tree."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "paths": {
                "type": "array",
                "description": (
                    f"Up to {MAX_RELEVANT_FILES} repo-relative file paths "
                    "taken verbatim from the provided tree."
                ),
                "items": {"type": "string"},
                "maxItems": MAX_RELEVANT_FILES,
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "One or two sentences explaining why these paths are "
                    "the right context for the RFC. Used for debugging "
                    "prompt quality; never shown to end users."
                ),
            },
        },
        "required": ["paths", "reasoning"],
    },
}


#: All possible citation fields, flattened so the OpenAI strict schema can
#: declare every property up front and the model fills the ones relevant to
#: its ``kind``. Fields unused by a given kind must be ``null``. The server
#: reshapes this into a typed ``target`` dict at parse time.
_CITATION_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "anchor": {"type": "string", "description": "Short slug used by [[cite:<anchor>]]."},
        "kind": {
            "type": "string",
            "enum": ["repo_range", "repo_pr", "repo_commit", "transcript_range"],
        },
        "repo": {"type": ["string", "null"], "description": "<owner>/<name> for repo_*."},
        "path": {"type": ["string", "null"], "description": "Repo-relative path for repo_range."},
        "line_start": {"type": ["integer", "null"]},
        "line_end": {"type": ["integer", "null"]},
        "pr_number": {"type": ["integer", "null"]},
        "pr_title_at_draft": {"type": ["string", "null"]},
        "commit_sha": {"type": ["string", "null"]},
        "transcript_start": {
            "type": ["string", "null"],
            "description": "HH:MM:SS or character offset (for transcript_range).",
        },
        "transcript_end": {"type": ["string", "null"]},
    },
    "required": [
        "anchor",
        "kind",
        "repo",
        "path",
        "line_start",
        "line_end",
        "pr_number",
        "pr_title_at_draft",
        "commit_sha",
        "transcript_start",
        "transcript_end",
    ],
}


DRAFT_RFC_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "draft_rfc",
    "description": (
        "Produce an RFC from the provided transcript and repo files. "
        "Every claim that references code, a PR, a commit, or a point "
        "in the transcript must be backed by a [[cite:<anchor>]] token "
        "in markdown_body and a matching entry in citations. Anchors are "
        "short lowercase slugs; each is used at most once."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {
                "type": "string",
                "description": "Short human-readable title for the RFC.",
            },
            "markdown_body": {
                "type": "string",
                "description": (
                    "The RFC body as markdown. Contains inline "
                    "[[cite:<anchor>]] tokens wherever a claim is cited. "
                    "Do not emit raw URLs or numeric citations - only "
                    "the [[cite:<anchor>]] form."
                ),
            },
            "citations": {
                "type": "array",
                "description": "One entry per distinct anchor used in markdown_body.",
                "items": _CITATION_ITEM,
            },
        },
        "required": ["title", "markdown_body", "citations"],
    },
}


def normalize_citation(item: dict[str, Any]) -> dict[str, Any]:
    """Reshape a flat ``draft_rfc`` citation into ``{anchor, kind, target}``.

    The model emits every possible field; we pick the ones relevant to the
    declared ``kind`` so the persisted ``target`` stays compact and typed.
    """

    kind = item["kind"]
    anchor = item["anchor"]
    if kind == "repo_range":
        target = {
            "repo": item["repo"],
            "path": item["path"],
            "line_start": item["line_start"],
            "line_end": item["line_end"],
        }
    elif kind == "repo_pr":
        target = {
            "repo": item["repo"],
            "number": item["pr_number"],
            "title_at_draft": item["pr_title_at_draft"],
        }
    elif kind == "repo_commit":
        target = {
            "repo": item["repo"],
            "sha": item["commit_sha"],
        }
    elif kind == "transcript_range":
        target = {
            "start": item["transcript_start"],
            "end": item["transcript_end"],
        }
    else:  # pragma: no cover - enum is enforced by strict schema
        raise ValueError(f"Unknown citation kind: {kind}")
    return {"anchor": anchor, "kind": kind, "target": target}
