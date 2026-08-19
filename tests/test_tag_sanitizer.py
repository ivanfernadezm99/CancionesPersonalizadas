"""Tests for app/tag_sanitizer.py — shared reference-song sanitizer.

Strict TDD for SDD change suno-tag-validation (RQ-TAG-01/02/03, RQ-TAG-04
input layer). The module under test is pure: no I/O, no app imports.
"""

from __future__ import annotations

import pytest

from app.tag_sanitizer import (
    ARTIST_BLOCKLIST,
    ARTIST_REJECTION_MESSAGE,
    sanitize_reference_song,
)


class TestSanitizeReferenceSong:
    """Parametrized sanitizer behavior table (RQ-TAG-01)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # RQ-TAG-01 strip patterns
            ("Bachata Rosa - Juan Luis Guerra", "Bachata Rosa"),
            ("Bailando de Enrique Iglesias", "Bailando"),
            ("La Bamba (Los Lobos)", "La Bamba"),
            # "Artist - Song" input (tasks 6.3): the song token is the last side
            # when no blocklist entry disambiguates
            ("Coldplay - Yellow", "Yellow"),
            # whitespace-trimmed input
            ("  Despacito  ", "Despacito"),
            # song-only input untouched
            ("Despacito", "Despacito"),
            # design decision 4: strip separators BEFORE blocklist check,
            # so a valid song following an artist token stays usable
            ("Los Palmeras - Mi Amor", "Mi Amor"),
            # Suno-rejected artist as one side — the song side survives
            ("Michael Jackson - Billie Jean", "Billie Jean"),
            ("Billie Jean de Michael Jackson", "Billie Jean"),
            ("Human Nature (Michael Jackson)", "Human Nature"),
        ],
    )
    def test_strips_artist_token(self, raw: str, expected: str) -> None:
        """Safe patterns strip to the song token; clean songs pass through."""
        assert sanitize_reference_song(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            # RQ-TAG-02: exact blocklist match
            "Los Palmeras",
            # RQ-TAG-02: case-insensitive match
            "los palmeras",
            # RQ-TAG-02: blocklist name embedded in longer input
            "Grupo Los Palmeras",
            # RQ-TAG-03: artist-only after strip (blocklist + non-blocklist)
            "Juan Luis Guerra",
            "La Mona Jiménez",
            # Suno-rejected high-profile artists, artist-only → drop reference
            "Michael Jackson",
            "michael jackson",
            "Shakira",
            "Luis Miguel",
            "Elvis Presley",
            "The Beatles",
            "Madonna",
            "Daddy Yankee",
            "Bad Bunny",
            "Queen",
        ],
    )
    def test_artist_only_returns_none(self, raw: str) -> None:
        """No usable reference signal (artist-only or blocklist hit)."""
        assert sanitize_reference_song(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            "Bachata Rosa - Juan Luis Guerra",
            "La Bamba (Los Lobos)",
            "Despacito",
            "Billie Jean - Michael Jackson",
        ],
    )
    def test_idempotent(self, raw: str) -> None:
        """Re-sanitizing a sanitized value must not change it (defense in depth)."""
        once = sanitize_reference_song(raw)
        assert once is not None
        assert sanitize_reference_song(once) == once


class TestBlocklistContract:
    """Blocklist seed and shared message (RQ-TAG-02/03, design decisions 5/6)."""

    def test_blocklist_contains_seed_entries(self) -> None:
        """Seed blocklist per RQ-TAG-02/03: los palmeras, la mona jiménez, juan luis guerra."""
        assert "los palmeras" in ARTIST_BLOCKLIST
        assert "la mona jiménez" in ARTIST_BLOCKLIST
        assert "juan luis guerra" in ARTIST_BLOCKLIST

    def test_blocklist_contains_suno_rejected_artists(self) -> None:
        """High-profile artists Suno rejects by name are covered (e.g. michael jackson)."""
        assert "michael jackson" in ARTIST_BLOCKLIST
        assert "shakira" in ARTIST_BLOCKLIST
        assert "luis miguel" in ARTIST_BLOCKLIST

    def test_rejection_message_is_spanish_artist_instruction(self) -> None:
        """Shared Spanish message reused by validator and Suno translator."""
        message = ARTIST_REJECTION_MESSAGE.lower()
        assert "artista" in message
        assert "quitá" in message
        assert "canción" in message
