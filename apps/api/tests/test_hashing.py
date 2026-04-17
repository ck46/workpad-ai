from __future__ import annotations

import hashlib

import pytest

from app.hashing import content_hash_for_range


SAMPLE = "alpha\nbeta\ngamma\ndelta\nepsilon\n"


def test_stable_across_newline_styles() -> None:
    lf = SAMPLE
    crlf = SAMPLE.replace("\n", "\r\n")
    cr = SAMPLE.replace("\n", "\r")
    assert (
        content_hash_for_range(lf, 2, 4)
        == content_hash_for_range(crlf, 2, 4)
        == content_hash_for_range(cr, 2, 4)
    )


def test_accepts_bytes_input() -> None:
    assert content_hash_for_range(SAMPLE.encode("utf-8"), 1, 2) == content_hash_for_range(SAMPLE, 1, 2)


def test_hash_matches_manual_sha256() -> None:
    expected = hashlib.sha256("beta\ngamma".encode("utf-8")).hexdigest()
    assert content_hash_for_range(SAMPLE, 2, 3) == expected


def test_out_of_bounds_range_clamps() -> None:
    assert content_hash_for_range(SAMPLE, 1, 99) == content_hash_for_range(SAMPLE, 1, 6)


def test_range_past_end_is_empty_hash() -> None:
    empty_hash = hashlib.sha256(b"").hexdigest()
    assert content_hash_for_range(SAMPLE, 100, 200) == empty_hash


@pytest.mark.parametrize(
    "line_start,line_end",
    [(0, 1), (-3, 5), (5, 2)],
)
def test_invalid_ranges_raise(line_start: int, line_end: int) -> None:
    with pytest.raises(ValueError):
        content_hash_for_range(SAMPLE, line_start, line_end)
