from __future__ import annotations

import hashlib


def content_hash_for_range(content: str | bytes, line_start: int, line_end: int) -> str:
    """Stable SHA-256 of a 1-indexed, inclusive line range.

    Normalizes CRLF / CR to LF so hashes don't shift when the same file is
    checked out with a different line-ending style. The range is clamped to
    the file bounds; an empty slice yields the hash of an empty string.
    """
    if line_start < 1 or line_end < line_start:
        raise ValueError("line_start must be >= 1 and line_end must be >= line_start")

    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    start_index = max(line_start - 1, 0)
    end_index = min(line_end, len(lines))
    slice_text = "\n".join(lines[start_index:end_index])

    return hashlib.sha256(slice_text.encode("utf-8")).hexdigest()
