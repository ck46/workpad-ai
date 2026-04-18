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
    """What a completed draft produces. Populated in later commits."""

    artifact_id: str
    citations: list[dict[str, Any]] = field(default_factory=list)


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
        """Entry point for the two-pass draft flow. Implemented later."""

        raise NotImplementedError("RFCDrafter.draft is wired in subsequent commits.")

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


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


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
