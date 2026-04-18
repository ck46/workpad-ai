"""Two-pass RFC drafter used by the v1 spec flow.

Pass 1 sends the model a cheap repo *index* (tree + README + manifest) and
a ``pick_relevant_files`` tool. The model returns up to 15 paths it thinks
matter for drafting. Pass 2 fetches those files in full and calls
``draft_rfc`` to produce a citation-annotated RFC.

This module holds only the tool schemas for now; the class that drives the
two passes is added in subsequent commits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from .github_client import CachedGitHubReader
    from .transcripts import TranscriptPayload


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


# ---------------------------------------------------------------------------
# AI client protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallResult:
    """Outcome of a single tool-forced model call."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelCall:
    """Inputs for a single model round trip."""

    instructions: str
    user_message: str
    tool: dict[str, Any]
    #: When set, the model is forced to call this tool (by name). When
    #: ``None`` the model is free to reply conversationally, which the
    #: drafter never wants today.
    tool_choice_name: str | None = None


class AIClient(Protocol):
    """Minimal drafter-facing client interface.

    Kept narrow so (a) the drafter doesn't couple to any SDK surface and
    (b) tests can substitute a fake that replays captured tool calls.
    Real implementations wrap ``openai.OpenAI().responses.create``.
    """

    def call_tool(self, call: ModelCall) -> ToolCallResult:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# Drafter
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    """What a completed draft produces."""

    artifact_id: str
    conversation_id: str
    title: str
    markdown_body: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    dropped_citations: list[dict[str, Any]] = field(default_factory=list)
    ref_at_draft: str = ""
    picked_paths: list[str] = field(default_factory=list)


class RFCDrafter:
    """Two-pass RFC drafter.

    Construction is dependency-injected so the same class drives the real
    FastAPI flow and the offline test suite:

    * ``ai_client``      - any object implementing :class:`AIClient`.
    * ``github_reader``  - :class:`CachedGitHubReader` that routes reads
                           through ``RepoCache``.
    * ``session_factory``- SQLAlchemy session factory used for persistence.
    * ``model``          - identifier forwarded to the AI client.

    The class methods (repo index, pass 1, pass 2, validation, persistence)
    are added in subsequent commits; this scaffold only wires the
    dependencies and surfaces a ``draft`` entry point that raises until
    implemented.
    """

    def __init__(
        self,
        *,
        ai_client: AIClient,
        github_reader: CachedGitHubReader,
        session_factory: "sessionmaker[Session]",
        model: str,
    ) -> None:
        self._ai_client = ai_client
        self._github_reader = github_reader
        self._session_factory = session_factory
        self._model = model

    def draft(
        self,
        *,
        conversation_id: str | None,
        transcript: str,
        repo: str,
    ) -> DraftResult:
        """Run the full two-pass draft flow and persist the result.

        Parses *transcript*, pins the current HEAD of *repo* as the draft
        ref, runs pass 1 + pass 2 + citation validation, then writes a new
        Artifact (spec_type="rfc") with accompanying SpecSource rows and
        Citation rows in a single transaction. If *conversation_id* is
        None, a new conversation is created with a title derived from the
        RFC title.
        """

        from .core import (
            Artifact,
            Citation,
            Conversation,
            SpecSource,
            create_conversation,
            get_conversation_or_404,
            utcnow,
        )
        from .schemas import SpecType
        from .transcripts import parse_transcript

        transcript_payload = parse_transcript(transcript)
        ref_at_draft = self._github_reader.client.resolve_head(repo)
        repo_index = self._build_repo_index(repo, ref_at_draft)

        picked_paths = self._pass1_pick_files(
            transcript=transcript_payload, repo_index=repo_index
        )
        pass2 = self._pass2_draft(
            transcript=transcript_payload,
            repo=repo,
            ref=ref_at_draft,
            picked_paths=picked_paths,
        )
        valid_citations, dropped_citations = self._validate_citations(
            citations=pass2["citations"],
            markdown_body=pass2["markdown_body"],
            ref_at_draft=ref_at_draft,
            fetched_files=pass2["fetched_files"],
        )

        with self._session_factory() as session:
            if conversation_id:
                conversation = get_conversation_or_404(session, conversation_id)
            else:
                conversation = create_conversation(session, pass2["title"])

            artifact = Artifact(
                conversation_id=conversation.id,
                title=pass2["title"][:240],
                content=pass2["markdown_body"],
                content_type="markdown",
                spec_type=SpecType.RFC.value,
                version=1,
            )
            session.add(artifact)
            session.flush()

            session.add(
                SpecSource(
                    artifact_id=artifact.id,
                    kind="transcript",
                    payload=transcript_payload.as_storage_dict(),
                )
            )
            session.add(
                SpecSource(
                    artifact_id=artifact.id,
                    kind="repo",
                    payload={"repo": repo, "ref_pinned": ref_at_draft},
                )
            )
            for entry in valid_citations:
                session.add(
                    Citation(
                        artifact_id=artifact.id,
                        anchor=entry["anchor"],
                        kind=entry["kind"],
                        target=entry["target"],
                        resolved_state="live",
                    )
                )

            conversation.updated_at = utcnow()
            session.commit()
            session.refresh(artifact)

            return DraftResult(
                artifact_id=artifact.id,
                conversation_id=conversation.id,
                title=artifact.title,
                markdown_body=artifact.content,
                citations=valid_citations,
                dropped_citations=dropped_citations,
                ref_at_draft=ref_at_draft,
                picked_paths=picked_paths,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_repo_index(self, repo: str, ref: str) -> dict[str, Any]:
        """Return a cheap pass-1 context bundle for *repo* at *ref*.

        Contains everything the model needs to *decide* which files matter,
        without actually fetching their full contents:

        * ``tree``       - list of blob paths from :meth:`GitHubClient.get_tree`
        * ``top_dirs``   - sorted, deduped set of immediate subdirectories
        * ``readme``     - first README file found at repo root, decoded to
                           text, truncated to a soft budget (8 KB)
        * ``manifest``   - first recognized manifest file at repo root
                           (``pyproject.toml`` / ``package.json`` / ``go.mod`` /
                           ``Cargo.toml`` / ``requirements.txt``) decoded to
                           text, truncated to a soft budget (4 KB)
        """

        client = self._github_reader.client
        tree = client.get_tree(repo, ref)

        top_dirs = sorted({path.split("/", 1)[0] for path in tree if "/" in path})

        readme_path = _first_match(tree, _README_CANDIDATES)
        manifest_path = _first_match(tree, _MANIFEST_CANDIDATES)

        readme_text = _safe_fetch_text(self._github_reader, repo, ref, readme_path, limit=8_000)
        manifest_text = _safe_fetch_text(
            self._github_reader, repo, ref, manifest_path, limit=4_000
        )

        return {
            "repo": repo,
            "ref": ref,
            "tree": tree,
            "top_dirs": top_dirs,
            "readme_path": readme_path,
            "readme": readme_text,
            "manifest_path": manifest_path,
            "manifest": manifest_text,
        }

    def _pass1_pick_files(
        self,
        *,
        transcript: TranscriptPayload,
        repo_index: dict[str, Any],
    ) -> list[str]:
        """Run the pass-1 model call and return up to 15 validated file paths.

        Paths the model picks that don't appear in ``repo_index['tree']`` are
        dropped (hallucinations); the list is truncated to
        :data:`MAX_RELEVANT_FILES`.
        """

        user_message = _render_pass1_user_message(transcript=transcript, repo_index=repo_index)
        result = self._ai_client.call_tool(
            ModelCall(
                instructions=PASS1_INSTRUCTIONS,
                user_message=user_message,
                tool=PICK_RELEVANT_FILES_TOOL,
                tool_choice_name="pick_relevant_files",
            )
        )
        raw_paths = result.arguments.get("paths") or []
        tree_set = set(repo_index.get("tree") or [])
        validated = [path for path in raw_paths if isinstance(path, str) and path in tree_set]
        # Preserve model order but dedupe.
        seen: set[str] = set()
        unique: list[str] = []
        for path in validated:
            if path not in seen:
                unique.append(path)
                seen.add(path)
        return unique[:MAX_RELEVANT_FILES]

    def _pass2_draft(
        self,
        *,
        transcript: TranscriptPayload,
        repo: str,
        ref: str,
        picked_paths: list[str],
    ) -> dict[str, Any]:
        """Fetch picked files and run the pass-2 model call.

        Returns the parsed tool arguments with the flat citations reshaped
        into ``{anchor, kind, target}``. Files that fail to fetch are
        silently skipped - the draft can still reference the transcript and
        the successfully fetched files.
        """

        files: list[dict[str, Any]] = []
        fetched_bytes: dict[str, bytes] = {}
        for path in picked_paths:
            try:
                file_content = self._github_reader.get_file(repo, ref, path)
            except Exception:
                continue
            raw = file_content.content[:PASS2_FILE_BYTES_LIMIT]
            fetched_bytes[path] = file_content.content
            files.append(
                {
                    "path": path,
                    "content": raw.decode("utf-8", errors="replace"),
                    "truncated": len(file_content.content) > PASS2_FILE_BYTES_LIMIT,
                }
            )

        user_message = _render_pass2_user_message(
            transcript=transcript, repo=repo, ref=ref, files=files
        )
        result = self._ai_client.call_tool(
            ModelCall(
                instructions=PASS2_INSTRUCTIONS,
                user_message=user_message,
                tool=DRAFT_RFC_TOOL,
                tool_choice_name="draft_rfc",
            )
        )
        args = result.arguments
        raw_citations = args.get("citations") or []
        return {
            "title": str(args.get("title") or "Untitled RFC"),
            "markdown_body": str(args.get("markdown_body") or ""),
            "citations": [normalize_citation(item) for item in raw_citations],
            "fetched_files": fetched_bytes,
        }

    def _validate_citations(
        self,
        *,
        citations: list[dict[str, Any]],
        markdown_body: str,
        ref_at_draft: str,
        fetched_files: dict[str, bytes],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate citations against the repo snapshot + markdown body.

        Returns ``(valid, dropped)``. Dropped entries include a ``reason`` key
        so prompt iteration can learn from them. Valid entries are returned
        unchanged in shape except ``repo_range`` targets gain ``ref_at_draft``
        and ``content_hash_at_draft`` so drift detection has something stable
        to compare against later.
        """

        from .hashing import content_hash_for_range

        valid: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []
        seen_anchors: set[str] = set()

        for citation in citations:
            anchor = citation.get("anchor")
            if not isinstance(anchor, str) or not anchor:
                dropped.append({"citation": citation, "reason": "missing_anchor"})
                continue
            if anchor in seen_anchors:
                dropped.append({"citation": citation, "reason": "duplicate_anchor"})
                continue
            token = f"[[cite:{anchor}]]"
            if token not in markdown_body:
                dropped.append({"citation": citation, "reason": "anchor_not_in_body"})
                continue

            kind = citation.get("kind")
            target = dict(citation.get("target") or {})

            if kind == "repo_range":
                path = target.get("path")
                line_start = target.get("line_start")
                line_end = target.get("line_end")
                if path not in fetched_files:
                    dropped.append({"citation": citation, "reason": "path_not_in_snapshot"})
                    continue
                if not isinstance(line_start, int) or not isinstance(line_end, int):
                    dropped.append({"citation": citation, "reason": "non_integer_line_range"})
                    continue
                if line_start < 1 or line_end < line_start:
                    dropped.append({"citation": citation, "reason": "invalid_line_range"})
                    continue
                file_bytes = fetched_files[path]
                file_line_count = file_bytes.count(b"\n") + (
                    0 if file_bytes.endswith(b"\n") or not file_bytes else 1
                )
                if line_start > file_line_count:
                    dropped.append({"citation": citation, "reason": "line_start_past_eof"})
                    continue
                # Clamp line_end to EOF rather than dropping; the pinned
                # content hash captures the actual observed lines.
                clamped_end = min(line_end, file_line_count)
                target["line_end"] = clamped_end
                target["ref_at_draft"] = ref_at_draft
                target["content_hash_at_draft"] = content_hash_for_range(
                    file_bytes, line_start, clamped_end
                )
            elif kind == "repo_pr":
                number = target.get("number")
                if not isinstance(number, int) or number < 1:
                    dropped.append({"citation": citation, "reason": "invalid_pr_number"})
                    continue
                target["ref_at_draft"] = ref_at_draft
            elif kind == "repo_commit":
                sha = target.get("sha")
                if not isinstance(sha, str) or len(sha) < 7:
                    dropped.append({"citation": citation, "reason": "invalid_commit_sha"})
                    continue
                target["ref_at_draft"] = ref_at_draft
            elif kind == "transcript_range":
                start = target.get("start")
                end = target.get("end")
                if not start or not end:
                    dropped.append({"citation": citation, "reason": "incomplete_transcript_range"})
                    continue
            else:
                dropped.append({"citation": citation, "reason": f"unknown_kind:{kind}"})
                continue

            seen_anchors.add(anchor)
            valid.append({"anchor": anchor, "kind": kind, "target": target})

        return valid, dropped


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


#: Each picked file is truncated to this many bytes before going into the
#: pass-2 prompt. 20 KB per file keeps the combined context bounded even at
#: MAX_RELEVANT_FILES=15.
PASS2_FILE_BYTES_LIMIT = 20_000


PASS2_INSTRUCTIONS = (
    "You are the pass-2 drafter for Workpad RFCs. You receive a transcript "
    "and a small set of repo files. Produce an RFC that captures the "
    "motivation, the proposed approach, the trade-offs discussed, and the "
    "open questions. Every claim that references code, a PR, a commit, or "
    "a point in the transcript must carry a [[cite:<anchor>]] token in "
    "markdown_body and a matching entry in citations.\n\n"
    "Rules:\n"
    "- Anchor slugs are short (4-12 lowercase alnum); each is used exactly "
    "once in markdown_body.\n"
    "- repo_range citations must point at code present in the provided "
    "files and at line numbers within that file.\n"
    "- Never invent file paths, PR numbers, or commit SHAs that weren't "
    "shown.\n"
    "- transcript_range citations use HH:MM:SS timestamps when they appear "
    "in the transcript; otherwise character offsets into the transcript.\n"
    "- Fill every property on each citation item (null for the ones that "
    "don't apply to the kind)."
)


PASS1_INSTRUCTIONS = (
    "You are the pass-1 file selector for the Workpad RFC drafter. Read the "
    "meeting transcript and the repo index, then call pick_relevant_files "
    "with the paths the drafter must fetch in pass 2. Only return paths "
    "that appear verbatim in <repo_tree>. Prefer implementation files over "
    "tests unless the discussion focuses on tests. Skip vendored, "
    "generated, or lock files. Do not exceed 15 paths."
)


_README_CANDIDATES = ("README.md", "README.rst", "README", "readme.md")
_MANIFEST_CANDIDATES = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "requirements.txt",
    "Gemfile",
    "build.gradle",
    "pom.xml",
)


def _first_match(tree: list[str], candidates: tuple[str, ...]) -> str | None:
    """Return the first path in *tree* whose basename matches any candidate."""

    lowered = {name.lower() for name in candidates}
    for path in tree:
        basename = path.rsplit("/", 1)[-1]
        if basename.lower() in lowered and "/" not in path:
            return path
    return None


def _render_pass1_user_message(
    *, transcript: TranscriptPayload, repo_index: dict[str, Any]
) -> str:
    """Render the pass-1 XML-tagged user message.

    XML-ish tags make it easy for the model to respect section boundaries
    without dragging in a real templating system.
    """

    # Cap the tree so we never ship a 50k-path blob to the model.
    tree_sample = "\n".join((repo_index.get("tree") or [])[:500])
    readme = repo_index.get("readme") or "(no README)"
    manifest = repo_index.get("manifest") or "(no manifest)"
    manifest_path = repo_index.get("manifest_path") or "(none)"
    readme_path = repo_index.get("readme_path") or "(none)"

    return (
        f"<repo repo=\"{repo_index['repo']}\" ref=\"{repo_index['ref']}\">\n"
        f"<tree>\n{tree_sample}\n</tree>\n"
        f"<readme path=\"{readme_path}\">\n{readme}\n</readme>\n"
        f"<manifest path=\"{manifest_path}\">\n{manifest}\n</manifest>\n"
        "</repo>\n"
        "<transcript>\n"
        f"{transcript.text}\n"
        "</transcript>"
    )


def _render_pass2_user_message(
    *,
    transcript: TranscriptPayload,
    repo: str,
    ref: str,
    files: list[dict[str, Any]],
) -> str:
    """Render the pass-2 user message with the transcript and picked files."""

    file_blocks: list[str] = []
    for entry in files:
        suffix = " truncated=\"true\"" if entry.get("truncated") else ""
        file_blocks.append(
            f"<file path=\"{entry['path']}\"{suffix}>\n{entry['content']}\n</file>"
        )
    files_section = "\n".join(file_blocks) if file_blocks else "<files/>"
    return (
        f"<repo repo=\"{repo}\" ref=\"{ref}\">\n"
        f"{files_section}\n"
        "</repo>\n"
        "<transcript>\n"
        f"{transcript.text}\n"
        "</transcript>"
    )


def _safe_fetch_text(
    reader: CachedGitHubReader,
    repo: str,
    ref: str,
    path: str | None,
    *,
    limit: int,
) -> str | None:
    """Fetch *path* via *reader* and return UTF-8 text truncated to *limit* bytes.

    Returns ``None`` when *path* is falsy or the file cannot be fetched.
    Errors are deliberately swallowed - the repo index is best-effort
    context; a missing README shouldn't sink a draft.
    """

    if not path:
        return None
    try:
        file = reader.get_file(repo, ref, path)
    except Exception:
        return None
    text = file.content[:limit].decode("utf-8", errors="replace")
    if len(file.content) > limit:
        text += "\n… (truncated)"
    return text
