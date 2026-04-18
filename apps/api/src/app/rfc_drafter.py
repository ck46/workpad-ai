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
