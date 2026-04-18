from __future__ import annotations

from app.transcripts import parse_transcript


OTTER_STYLE = """00:00:12 Alex: We should move auth out of the legacy service.
00:00:45 Sam: Agreed. Let me check the current handler.
  It's sitting in src/legacy/auth_middleware.py right now.
00:01:20 Alex: Let's plan the migration this sprint.
"""

GRANOLA_STYLE = """[0:00] Priya: Opening the design review.
[0:42] Dan: The rate limiter change landed in PR 412.
[1:15] Priya: Any regressions?
[1:20] Dan: One - #PR-419 rolled it back partially.
"""

ROUGH_PASTE = """We talked about moving auth out of the legacy service.
Sam pointed out the current handler is in auth_middleware.py.
Alex agreed we'll plan a migration next sprint.
"""


def test_otter_style_yields_three_segments_with_normalized_stamps() -> None:
    payload = parse_transcript(OTTER_STYLE)
    assert payload.segments is not None
    assert [segment.start for segment in payload.segments] == ["00:00:12", "00:00:45", "00:01:20"]
    # Continuation line is folded into the Sam segment.
    assert "auth_middleware.py" in payload.segments[1].text
    # Each segment's end is the next segment's start; last is open-ended.
    assert payload.segments[0].end == "00:00:45"
    assert payload.segments[-1].end is None


def test_granola_style_normalizes_mm_ss_into_hh_mm_ss() -> None:
    payload = parse_transcript(GRANOLA_STYLE)
    assert payload.segments is not None
    starts = [segment.start for segment in payload.segments]
    assert starts == ["00:00:00", "00:00:42", "00:01:15", "00:01:20"]
    assert "PR 412" in payload.segments[1].text


def test_rough_paste_has_no_segments_and_preserves_text() -> None:
    payload = parse_transcript(ROUGH_PASTE)
    assert payload.segments is None
    assert payload.text == ROUGH_PASTE


def test_hash_is_stable_across_calls() -> None:
    assert parse_transcript(OTTER_STYLE).hash == parse_transcript(OTTER_STYLE).hash


def test_storage_dict_shape_is_json_serializable() -> None:
    import json

    payload = parse_transcript(OTTER_STYLE)
    serialized = json.dumps(payload.as_storage_dict())
    # Round-trip through JSON without losing the segment shape.
    rehydrated = json.loads(serialized)
    assert rehydrated["hash"] == payload.hash
    assert rehydrated["segments"][0]["start"] == "00:00:12"
