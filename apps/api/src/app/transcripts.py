"""Transcript normalization for the v1 spec drafter.

Callers paste transcripts from any source (Otter, Granola, Fireflies, a
raw copy of a Zoom auto-caption dump, …). We accept them all as opaque
text and ``parse_transcript`` produces a stable payload that:

* stores the full text and a content hash, so drifted transcripts can
  be detected across sessions;
* parses timestamp markers into structured segments when present,
  letting ``transcript_range`` citations point at real ``HH:MM:SS``
  windows;
* falls back to ``None`` segments when timestamps are absent, so the
  drafter can still cite by character offsets without reinventing
  timestamp guesses.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass


# Matches HH:MM:SS or MM:SS at the start of a line, optionally wrapped in
# [] or (), optionally followed by a "Speaker:" prefix.
_TIMESTAMP_LINE = re.compile(
    r"""
    ^\s*                       # leading whitespace
    [\[\(]?                    # optional opening bracket/paren
    (?P<stamp>
        (?:\d{1,2}:)?          # optional hours
        \d{1,2}:\d{2}          # minutes:seconds
    )
    [\]\)]?                    # optional closing bracket/paren
    \s*                        # whitespace between stamp and text
    (?::|-\s|–\s|\u2013\s)?    # optional separator
    \s*
    (?P<body>.*?)              # message body (may be empty)
    \s*$
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class TranscriptSegment:
    """A single timestamp-bounded segment in a parsed transcript."""

    start: str
    end: str | None
    text: str


@dataclass(frozen=True)
class TranscriptPayload:
    """Normalized transcript ready for storage as SpecSource.payload."""

    text: str
    hash: str
    segments: list[TranscriptSegment] | None

    def as_storage_dict(self) -> dict:
        return {
            "text": self.text,
            "hash": self.hash,
            "segments": (
                [asdict(segment) for segment in self.segments]
                if self.segments is not None
                else None
            ),
        }


def _normalize_stamp(stamp: str) -> str:
    """Return a canonical ``HH:MM:SS`` rendering for *stamp*."""

    parts = stamp.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return f"00:{int(minutes):02d}:{int(seconds):02d}"
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    return stamp  # pragma: no cover - the regex already constrains this


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_transcript(text: str) -> TranscriptPayload:
    """Parse *text* into a :class:`TranscriptPayload`.

    The input is preserved verbatim in ``text`` (and in segment bodies); the
    parser only normalizes timestamps into ``HH:MM:SS``. If the text contains
    no recognizable timestamp markers ``segments`` is ``None`` and callers
    should fall back to character-offset citations.
    """

    if not text:
        raise ValueError("Transcript text must not be empty.")

    raw_segments: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = _TIMESTAMP_LINE.match(line)
        if not match:
            if raw_segments:
                # Continuation of the previous segment's body.
                stamp, body = raw_segments[-1]
                joined = f"{body}\n{line}".strip("\n")
                raw_segments[-1] = (stamp, joined)
            continue
        stamp = _normalize_stamp(match.group("stamp"))
        body = match.group("body") or ""
        raw_segments.append((stamp, body))

    if not raw_segments:
        return TranscriptPayload(text=text, hash=_hash_text(text), segments=None)

    segments: list[TranscriptSegment] = []
    for index, (stamp, body) in enumerate(raw_segments):
        end = raw_segments[index + 1][0] if index + 1 < len(raw_segments) else None
        segments.append(TranscriptSegment(start=stamp, end=end, text=body.strip()))

    return TranscriptPayload(text=text, hash=_hash_text(text), segments=segments)
