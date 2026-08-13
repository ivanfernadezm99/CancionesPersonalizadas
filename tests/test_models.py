"""Tests for Pydantic validator behavior on reference_song.

Strict TDD for SDD change suno-tag-validation (RQ-PRJ-01/02, RQ-RS-05).
The validators live on SongProjectCreate and SongProjectUpdate only —
GenerateRequest stays untouched for legacy backward compatibility.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import GenerateRequest, SongProjectCreate, SongProjectUpdate
from app.tag_sanitizer import ARTIST_REJECTION_MESSAGE


def make_create(**overrides: object) -> dict[str, object]:
    """Minimal valid SongProjectCreate payload plus overrides."""
    params: dict[str, object] = {
        "recipient": "María",
        "relationship": "pareja",
        "genre": "bachata",
        "mood": "romántica",
        "voice": "female",
    }
    params.update(overrides)
    return params


class TestSongProjectCreateReferenceSong:
    """Validator behavior on POST /api/projects (RQ-PRJ-01)."""

    def test_strips_artist_token_on_create(self) -> None:
        """Safe 'Song - Artist' pattern is stripped before storing."""
        model = SongProjectCreate(
            **make_create(reference_song="Bachata Rosa - Juan Luis Guerra"),
        )
        assert model.reference_song == "Bachata Rosa"

    def test_artist_only_raises_spanish_message(self) -> None:
        """Artist-only value raises ValueError → 422 with friendly Spanish."""
        with pytest.raises(ValidationError) as exc:
            SongProjectCreate(**make_create(reference_song="Los Palmeras"))
        assert ARTIST_REJECTION_MESSAGE in str(exc.value)

    def test_empty_string_passes_through(self) -> None:
        """Empty reference_song remains valid (RQ-PRJ-01 empty-accepted)."""
        model = SongProjectCreate(**make_create(reference_song=""))
        assert model.reference_song == ""

    def test_absent_passes_through(self) -> None:
        """Absent reference_song remains None."""
        model = SongProjectCreate(**make_create())
        assert model.reference_song is None


class TestSongProjectUpdateReferenceSong:
    """Validator behavior on PATCH /api/projects/{id} (RQ-PRJ-02)."""

    def test_strips_artist_token_on_patch(self) -> None:
        """Safe 'Song de Artist' pattern is stripped on patch too."""
        model = SongProjectUpdate(reference_song="Bailando de Enrique Iglesias")
        assert model.reference_song == "Bailando"

    def test_artist_only_raises_spanish_message(self) -> None:
        """Artist-only value on patch raises ValueError → 422, change not stored."""
        with pytest.raises(ValidationError) as exc:
            SongProjectUpdate(reference_song="La Mona Jiménez")
        assert ARTIST_REJECTION_MESSAGE in str(exc.value)

    def test_empty_string_passes_through(self) -> None:
        """Empty reference_song on patch remains valid."""
        model = SongProjectUpdate(reference_song="")
        assert model.reference_song == ""


class TestGenerateRequestUntouched:
    """RQ-RS-05: legacy GenerateRequest must keep raw values (backward compat)."""

    def test_generate_request_keeps_raw_artist_format(self) -> None:
        """No validator on GenerateRequest — raw 'Song - Artist' preserved."""
        request = GenerateRequest(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
            voice="female",
            reference_song="Bachata Rosa - Juan Luis Guerra",
        )
        assert request.reference_song == "Bachata Rosa - Juan Luis Guerra"
