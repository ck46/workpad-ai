"""Scaffold service — first-session-produces-value machinery.

The scaffold endpoint is how a new user gets from "blank shell" to "a
populated project with a real pad" in one step. It accepts some seed
input (pasted text, a repo URL, a free-form hint) and calls the model
to infer:

  * A sensible project name (if the caller didn't already pick one).
  * The pad type that matches the input (RFC / ADR / design note /
    run note).
  * A pad title.
  * A short outline of section headings.
  * Any GitHub repo URLs mentioned in the input.

Given the inference, the service creates a Project (if none was
supplied), attaches the seed input as a ``SpecSource`` row, and writes
a stub ``Artifact`` whose body is the outline. No full drafting happens
here — that's the job of the RFC drafter or a future generalized
drafter invoked separately.

The module mirrors ``rfc_drafter.py``'s dependency-injected shape so
tests can swap in a scripted AI client without touching the OpenAI SDK.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .rfc_drafter import AIClient, ModelCall
from .schemas import ArtifactStatus, ArtifactType, ContentType, SpecType

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker, Session


log = logging.getLogger(__name__)


VALID_PAD_TYPES = ("rfc", "adr", "design_note", "run_note")


SCAFFOLD_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "infer_scaffold",
    "description": (
        "Given some seed input from a new user (pasted transcript or "
        "notes, a GitHub repo URL, and/or a free-form hint), infer what "
        "kind of pad they are about to write and produce a named project "
        "plus a short outline so they can see immediate value in the "
        "product. Prefer 'rfc' when the input reads like a proposal or "
        "design discussion, 'adr' when it is a decision record, "
        "'design_note' for exploratory shape sketches, 'run_note' for "
        "what-happened-in-an-incident / session logs. Detect any GitHub "
        "repo URLs you see in the input and return them verbatim."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "project_name": {
                "type": "string",
                "description": (
                    "Short, human-readable project name derived from the "
                    "input. Six words or fewer. No trailing punctuation."
                ),
            },
            "pad_type": {
                "type": "string",
                "enum": list(VALID_PAD_TYPES),
                "description": "Which of the four pad types best fits.",
            },
            "pad_title": {
                "type": "string",
                "description": (
                    "A working title for the pad. Sentence case, no "
                    "trailing period."
                ),
            },
            "outline_sections": {
                "type": "array",
                "description": (
                    "Markdown section headings (without the leading #) "
                    "that a user could reasonably start filling in. Four "
                    "to eight sections is ideal; never more than twelve."
                ),
                "items": {"type": "string"},
                "maxItems": 12,
            },
            "detected_repo_urls": {
                "type": "array",
                "description": (
                    "GitHub repo URLs or owner/name pairs mentioned in "
                    "the input, verbatim."
                ),
                "items": {"type": "string"},
            },
        },
        "required": [
            "project_name",
            "pad_type",
            "pad_title",
            "outline_sections",
            "detected_repo_urls",
        ],
    },
}


_SCAFFOLD_SYSTEM_PROMPT = (
    "You are helping a new user start their first pad in Workpad. Workpad is "
    "a tool for engineering teams to keep durable technical pads (RFCs, "
    "ADRs, design notes, run notes) wired to their sources. Given the "
    "user's seed input, call the ``infer_scaffold`` tool exactly once. "
    "Keep project names and titles concrete and specific — never use "
    "filler like 'Untitled' or 'New project'. Prefer the user's own "
    "phrasing where possible."
)


@dataclass
class ScaffoldInference:
    """Structured result from the model's single tool call."""

    project_name: str
    pad_type: str
    pad_title: str
    outline_sections: list[str]
    detected_repo_urls: list[str]

    @classmethod
    def from_tool_args(cls, raw: dict[str, Any]) -> "ScaffoldInference":
        pad_type = str(raw.get("pad_type") or "").strip()
        if pad_type not in VALID_PAD_TYPES:
            pad_type = "design_note"  # safest default: exploration, low commitment
        outline = raw.get("outline_sections") or []
        if not isinstance(outline, list):
            outline = []
        return cls(
            project_name=str(raw.get("project_name") or "").strip()[:240],
            pad_type=pad_type,
            pad_title=str(raw.get("pad_title") or "").strip()[:240],
            outline_sections=[str(s).strip() for s in outline if str(s).strip()],
            detected_repo_urls=[
                str(u).strip() for u in (raw.get("detected_repo_urls") or []) if str(u).strip()
            ],
        )


@dataclass
class ScaffoldResult:
    """What the scaffold service returns to the caller."""

    project_id: str
    project_name: str
    project_created: bool
    artifact_id: str
    conversation_id: str
    pad_type: str
    pad_title: str
    source_id: str | None
    outline_sections: list[str]
    detected_repo_urls: list[str]


def render_outline_markdown(title: str, outline_sections: list[str]) -> str:
    """Turn the inferred title + section list into a stub markdown body.

    The H1 is the pad title (so the chrome's H1-derived title stays in
    sync). Each outline section becomes a level-2 heading with a short
    italicized prompt underneath so empty pads don't look abandoned.
    """

    parts: list[str] = [f"# {title.strip() or 'Untitled pad'}", ""]
    if not outline_sections:
        parts.extend(
            [
                "## Context",
                "",
                "_What question is this pad trying to answer?_",
                "",
                "## Notes",
                "",
                "_Capture what you know so far. Wire sources in as you go._",
                "",
            ]
        )
        return "\n".join(parts).rstrip() + "\n"

    for section in outline_sections:
        parts.extend([f"## {section}", "", "_Fill this in._", ""])
    return "\n".join(parts).rstrip() + "\n"


def build_scaffold_prompt(
    *, text: str | None, repo_url: str | None, hint: str | None
) -> str:
    """Compose the user-message content for the inference call."""

    pieces: list[str] = []
    if hint and hint.strip():
        pieces.append(f"## User hint\n{hint.strip()}")
    if repo_url and repo_url.strip():
        pieces.append(f"## Repo URL\n{repo_url.strip()}")
    if text and text.strip():
        pieces.append(
            "## Pasted input\n"
            + text.strip()[:16000]  # cap token usage; infer doesn't need all of it
        )
    if not pieces:
        raise ValueError("scaffold requires at least one of text, repo_url, or hint")
    return "\n\n".join(pieces)


_GITHUB_URL_RE = re.compile(r"(https?://github\.com/[^\s/]+/[^\s/]+)", re.IGNORECASE)


def fallback_detect_repo_urls(*inputs: str | None) -> list[str]:
    """Extract repo URLs from raw input as a safety net.

    The model generally returns these cleanly via detected_repo_urls,
    but when it doesn't we still want to anchor a repo source so the
    pad is usable.
    """

    found: list[str] = []
    for item in inputs:
        if not item:
            continue
        for match in _GITHUB_URL_RE.findall(item):
            cleaned = match.rstrip(").,;:'\"")
            if cleaned not in found:
                found.append(cleaned)
    return found


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ScaffoldService:
    """Run a single model inference + persist the resulting scaffold.

    Dependencies are injected so tests can substitute:

    * ``ai_client`` — any :class:`AIClient` (the real one wraps OpenAI
      Responses; a scripted fake replays a captured ``ToolCallResult``).
    * ``session_factory`` — SQLAlchemy session factory for the
      project + source + artifact writes.
    """

    def __init__(
        self,
        *,
        ai_client: AIClient,
        session_factory: "sessionmaker[Session]",
        model: str,
    ) -> None:
        self._ai_client = ai_client
        self._session_factory = session_factory
        self._model = model

    def infer(
        self, *, text: str | None, repo_url: str | None, hint: str | None
    ) -> ScaffoldInference:
        user_message = build_scaffold_prompt(text=text, repo_url=repo_url, hint=hint)
        call = ModelCall(
            instructions=_SCAFFOLD_SYSTEM_PROMPT,
            user_message=user_message,
            tool=SCAFFOLD_TOOL,
            tool_choice_name="infer_scaffold",
        )
        outcome = self._ai_client.call_tool(call)
        return ScaffoldInference.from_tool_args(outcome.arguments)

    def scaffold(
        self,
        *,
        user_id: str,
        text: str | None = None,
        repo_url: str | None = None,
        hint: str | None = None,
        project_id: str | None = None,
    ) -> ScaffoldResult:
        # Local imports to keep the module import graph shallow (core +
        # projects both import from each other indirectly via SQLAlchemy
        # relationship back-refs).
        from .core import Artifact, Conversation, SpecSource, utcnow
        from .projects import (
            Project,
            ProjectMember,
            ROLE_OWNER,
            require_member,
        )

        inference = self.infer(text=text, repo_url=repo_url, hint=hint)
        # Safety net: if the model didn't return repo URLs but we can
        # regex one out of the input, use that so the scaffold still
        # produces a source row.
        detected_repos = inference.detected_repo_urls or fallback_detect_repo_urls(
            text, repo_url, hint
        )

        with self._session_factory() as session:
            project_created = False
            if project_id:
                # Caller supplied an existing project; verify membership
                # and use it. Name is left alone.
                require_member(session, project_id, user_id)
                project = session.get(Project, project_id)
                if project is None:
                    raise ValueError("project not found")
                project_name = project.name
            else:
                project_name = inference.project_name or "Untitled project"
                project = Project(name=project_name, created_by_user_id=user_id)
                session.add(project)
                session.flush()
                session.add(
                    ProjectMember(
                        project_id=project.id, user_id=user_id, role=ROLE_OWNER
                    )
                )
                project_created = True

            # Backing conversation so existing pad-inside-conversation
            # invariants still hold (messages can attach, selectConversation
            # works as-is on the frontend).
            conversation = Conversation(
                title=inference.pad_title or "Untitled pad",
                owner_id=user_id,
                project_id=project.id,
            )
            session.add(conversation)
            session.flush()

            markdown_body = render_outline_markdown(
                inference.pad_title, inference.outline_sections
            )

            artifact_type = inference.pad_type
            artifact = Artifact(
                conversation_id=conversation.id,
                origin_conversation_id=conversation.id,
                project_id=project.id,
                title=inference.pad_title[:240] or "Untitled pad",
                content=markdown_body,
                content_type=ContentType.MARKDOWN.value,
                spec_type=SpecType.RFC.value if artifact_type == "rfc" else None,
                artifact_type=ArtifactType(artifact_type).value,
                status=ArtifactStatus.DRAFT.value,
                summary="",
                version=1,
            )
            session.add(artifact)
            session.flush()

            # Attach any provided seed as a SpecSource. v1 keeps this
            # simple: one row per kind, payload carries the raw input
            # so later drafting can pick it up.
            source_id: str | None = None
            if text and text.strip():
                src = SpecSource(
                    artifact_id=artifact.id,
                    kind="transcript",
                    payload={"text": text.strip()[:32000], "origin": "scaffold"},
                )
                session.add(src)
                session.flush()
                source_id = src.id

            anchor_repo = repo_url or (detected_repos[0] if detected_repos else None)
            if anchor_repo:
                src = SpecSource(
                    artifact_id=artifact.id,
                    kind="repo",
                    payload={"url": anchor_repo, "origin": "scaffold"},
                )
                session.add(src)
                session.flush()
                if source_id is None:
                    source_id = src.id

            conversation.updated_at = utcnow()
            project.updated_at = utcnow()
            session.commit()

            log.info(
                "scaffold: user=%s project=%s(%s) pad=%s type=%s sections=%d",
                user_id,
                project.id,
                "created" if project_created else "existing",
                artifact.id,
                inference.pad_type,
                len(inference.outline_sections),
            )

            return ScaffoldResult(
                project_id=project.id,
                project_name=project.name,
                project_created=project_created,
                artifact_id=artifact.id,
                conversation_id=conversation.id,
                pad_type=inference.pad_type,
                pad_title=inference.pad_title,
                source_id=source_id,
                outline_sections=inference.outline_sections,
                detected_repo_urls=detected_repos,
            )
