"""Tests for app/voice/__init__.py — prompt builder."""

from __future__ import annotations

import pytest

from app.models import VoiceConfig
from app.voice import build_prompt, get_available_voices


class TestBuildPrompt:
    """Tests for build_prompt()."""

    def test_female_prompt_contains_female_descriptor(self) -> None:
        """build_prompt('female', ...) should include female voice descriptor."""
        prompt = build_prompt("female", "bachata", "romántica")
        assert "femenina" in prompt.lower() or "cantante femenina" in prompt.lower()

    def test_male_prompt_contains_male_descriptor(self) -> None:
        """build_prompt('male', ...) should include male voice descriptor."""
        prompt = build_prompt("male", "balada", "romántica")
        assert "masculino" in prompt.lower() or "cantante masculino" in prompt.lower()

    def test_prompt_includes_genre(self) -> None:
        """Prompt should contain the genre."""
        prompt = build_prompt("female", "reggaetón", "festiva")
        assert "reggaetón" in prompt.lower() or "reggaeton" in prompt.lower()

    def test_prompt_includes_mood(self) -> None:
        """Prompt should contain the mood."""
        prompt = build_prompt("female", "bachata", "romántica")
        assert "romántica" in prompt.lower()

    def test_prompt_is_spanish(self) -> None:
        """Prompt should be a natural Spanish sentence."""
        prompt = build_prompt("female", "salsa", "festiva")
        assert "canción" in prompt.lower()
        assert "melodía" in prompt.lower()

    def test_invalid_voice_raises_valueerror(self) -> None:
        """Invalid voice_id should raise ValueError with valid options."""
        with pytest.raises(ValueError, match="unknown_voice"):
            build_prompt("unknown_voice", "bachata", "romántica")

    def test_invalid_voice_message_lists_options(self) -> None:
        """Error message should list valid voice options."""
        with pytest.raises(ValueError) as exc:
            build_prompt("robot", "bachata", "romántica")
        assert "female" in str(exc.value)
        assert "male" in str(exc.value)

    def test_empty_voice_id_raises_valueerror(self) -> None:
        """Empty voice_id should raise ValueError."""
        with pytest.raises(ValueError):
            build_prompt("", "bachata", "romántica")

    def test_with_reference_song_includes_style_text(self) -> None:
        """build_prompt with a song reference sanitizes and includes the song."""
        prompt = build_prompt(
            "female", "bachata", "romántica",
            reference_song="Coldplay - Yellow",
        )
        assert "Inspirada en el estilo de" in prompt
        assert "Yellow" in prompt
        assert "Coldplay" not in prompt

    def test_known_artist_uses_curated_style_descriptor(self) -> None:
        """A blocklisted artist maps to a Suno-safe descriptor (RQ-TAG-05)."""
        prompt = build_prompt(
            "male", "pop", "energética",
            reference_song="Michael Jackson - Bad",
        )
        # The curated descriptor replaces the meaningless stripped token:
        assert "Inspirada en el estilo de" not in prompt
        assert "michael jackson" not in prompt.lower()
        assert "pop-funk" in prompt
        assert "funk" in prompt

    def test_artist_only_reference_appends_no_style(self) -> None:
        """artist-only reference still does not emit 'Inspirada en el estilo de'."""
        prompt = build_prompt(
            "male", "cumbia", "festiva",
            reference_song="Los Palmeras",
        )
        assert "Inspirada en el estilo de" not in prompt
        assert "masculino" in prompt.lower() or "cantante masculino" in prompt.lower()

    def test_reference_style_param_is_appended(self) -> None:
        """A pre-translated reference_style is appended verbatim (LLM path)."""
        prompt = build_prompt(
            "male", "pop", "energética",
            reference_song="Alguna referencia",
            reference_style="synthpop ochentero con bajo funky y coros pegadizos",
        )
        assert "synthpop ochentero" in prompt

    def test_without_reference_song_is_unchanged(self) -> None:
        """build_prompt without reference_song should not include style text."""
        prompt_with = build_prompt(
            "female", "bachata", "romántica",
            reference_song="Despacito",
        )
        prompt_without = build_prompt("female", "bachata", "romántica")
        assert "Inspirada en el estilo de" in prompt_with
        assert "Inspirada en el estilo de" not in prompt_without


class TestGetAvailableVoices:
    """Tests for get_available_voices()."""

    def test_returns_list(self) -> None:
        """get_available_voices() should return a list."""
        voices = get_available_voices()
        assert isinstance(voices, list)

    def test_contains_voice_config_objects(self) -> None:
        """Each item should be a VoiceConfig."""
        voices = get_available_voices()
        for voice in voices:
            assert isinstance(voice, VoiceConfig)

    def test_returns_all_registered_voices(self) -> None:
        """Should return both female and male voices."""
        voices = get_available_voices()
        ids = {v.id for v in voices}
        assert "female" in ids
        assert "male" in ids

    def test_returns_independent_copy(self) -> None:
        """Modifying the returned list should not affect the registry."""
        voices = get_available_voices()
        original_count = len(voices)
        voices.clear()
        assert len(get_available_voices()) == original_count
