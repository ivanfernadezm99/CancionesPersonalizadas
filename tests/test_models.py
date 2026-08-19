"""Tests for Pydantic validator behavior on reference_song.

Strict TDD for SDD change suno-tag-validation (RQ-PRJ-01/02, RQ-RS-05).
The validators live on SongProjectCreate and SongProjectUpdate only —
GenerateRequest stays untouched for legacy backward compatibility.
"""

from __future__ import annotations

from app.models import GenerateRequest, SongProjectCreate, SongProjectUpdate


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
    """Validator behavior on POST /api/projects (RQ-PRJ-01, RQ-TAG-05)."""

    def test_keeps_reference_together(self) -> None:
        """reference_song (even 'Song - Artist') is kept so the translator can map it."""
        model = SongProjectCreate(
            **make_create(reference_song="Bachata Rosa - Juan Luis Guerra"),
        )
        assert model.reference_song == "Bachata Rosa - Juan Luis Guerra"

    def test_artist_only_accepted(self) -> None:
        """Artist-only value is now ACCEPTED (generation-time translates it)."""
        model = SongProjectCreate(**make_create(reference_song="Los Palmeras"))
        assert model.reference_song == "Los Palmeras"

    def test_empty_string_passes_through(self) -> None:
        """Empty reference_song remains valid (RQ-PRJ-01 empty-accepted)."""
        model = SongProjectCreate(**make_create(reference_song=""))
        assert model.reference_song == ""

    def test_absent_passes_through(self) -> None:
        """Absent reference_song remains None."""
        model = SongProjectCreate(**make_create())
        assert model.reference_song is None

    def test_whitespace_only_is_trimmed_to_empty(self) -> None:
        """Whitespace-only reference_song is trimmed to an empty string."""
        model = SongProjectCreate(**make_create(reference_song="   "))
        assert model.reference_song == ""


class TestSongProjectUpdateReferenceSong:
    """Validator behavior on PATCH /api/projects/{id} (RQ-PRJ-02, RQ-TAG-05)."""

    def test_keeps_reference_together_on_patch(self) -> None:
        """Raw 'Song de Artist' is preserved so the translator can map it."""
        model = SongProjectUpdate(reference_song="Bailando de Enrique Iglesias")
        assert model.reference_song == "Bailando de Enrique Iglesias"

    def test_artist_only_accepted(self) -> None:
        """Artist-only value on patch is accepted and stored (no 422)."""
        model = SongProjectUpdate(reference_song="La Mona Jiménez")
        assert model.reference_song == "La Mona Jiménez"

    def test_empty_string_passes_through(self) -> None:
        """Empty reference_song on patch remains valid."""
        model = SongProjectUpdate(reference_song="")
        assert model.reference_song == ""

    def test_whitespace_only_is_trimmed_to_empty(self) -> None:
        """Whitespace-only reference on patch is trimmed to an empty string."""
        model = SongProjectUpdate(reference_song="   ")
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
