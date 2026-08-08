"""Tests for app/projects/draft.py — normalize_draft output validation (RQ-DRAFT-03).

Covers:
- Strips empty lines
- Total lines < 10 raises LyricsGenerationError
- Forces language='es'
"""

from __future__ import annotations

import pytest

from app.lyrics.providers import LyricsGenerationError
from app.models import LyricsResult
from app.projects.draft import normalize_draft


def _make_result(
    language: str = "es",
    bridge: bool = True,
    empty_line: bool = False,
) -> LyricsResult:
    """Build a valid LyricsResult with a given language and optional quirks."""
    chorus_lines = ["coro uno", "coro dos", "coro tres", "coro cuatro"]
    if empty_line:
        chorus_lines.append("")
    return LyricsResult(
        verses=[
            {"number": 1, "lines": ["v1 a", "v1 b", "v1 c", "v1 d"]},
            {"number": 2, "lines": ["v2 a", "v2 b", "v2 c", "v2 d"]},
        ],
        chorus={"lines": chorus_lines},
        bridge={"lines": ["puente uno", "puente dos"]} if bridge else None,
        language=language,
        title_suggestion="Mi Canción",
        provider="mock",
    )


class TestNormalizeDraft:
    """normalize_draft() behavior (RQ-DRAFT-03)."""

    def test_strips_empty_lines(self) -> None:
        """normalize_draft should drop empty/whitespace-only lines."""
        result = _make_result(empty_line=True)
        normalized = normalize_draft(result)
        # Original chorus had a trailing "" which must be removed
        chorus_lines = [line for line in normalized.chorus.lines]
        assert "" not in chorus_lines
        assert all(line.strip() == line for line in chorus_lines)

    def test_raises_when_total_lines_below_ten(self) -> None:
        """normalize_draft should raise LyricsGenerationError when total lines < 10."""
        short = LyricsResult(
            verses=[{"number": 1, "lines": ["a", "b", "c"]}],
            chorus={"lines": ["x", "y", "z"]},
            bridge=None,
            language="es",
            title_suggestion="Corta",
            provider="mock",
        )
        with pytest.raises(LyricsGenerationError):
            normalize_draft(short)

    def test_forces_language_es(self) -> None:
        """normalize_draft should pin language='es' (RQ-DRAFT-03)."""
        result = _make_result(language="en")
        normalized = normalize_draft(result)
        assert normalized.language == "es"

    def test_keeps_language_es_when_already_es(self) -> None:
        """normalize_draft should keep language='es' when already es."""
        result = _make_result(language="es")
        normalized = normalize_draft(result)
        assert normalized.language == "es"

    def test_valid_draft_is_unchanged_structurally(self) -> None:
        """normalize_draft should keep a valid draft's structure and >= 10 total lines."""
        result = _make_result()
        normalized = normalize_draft(result)
        assert len(normalized.verses) == 2
        assert normalized.chorus is not None
        assert normalized.bridge is not None
        assert normalized.title_suggestion == "Mi Canción"

    def test_total_line_count_at_least_ten_after_strip(self) -> None:
        """normalize_draft should produce >= 10 total lines after stripping empties."""
        result = _make_result(empty_line=True)
        normalized = normalize_draft(result)
        total = sum(len(v.lines) for v in normalized.verses)
        total += len(normalized.chorus.lines)
        if normalized.bridge is not None:
            total += len(normalized.bridge.lines)
        assert total >= 10
