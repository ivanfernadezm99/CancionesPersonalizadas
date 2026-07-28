"""Tests for app/lyrics/__init__.py — generate() orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.lyrics import generate
from app.lyrics.prompts import build_user_prompt
from app.lyrics.providers import LyricsGenerationError
from app.models import LyricsResult


class TestBuildUserPromptReferenceSong:
    """Tests for build_user_prompt with reference_song param."""

    def test_with_reference_song_includes_style_guidance(self) -> None:
        """build_user_prompt with reference_song should include style hint."""
        prompt = build_user_prompt(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
            reference_song="Bachata Rosa - Juan Luis Guerra",
        )
        assert "Bachata Rosa" in prompt
        assert "Juan Luis Guerra" in prompt
        assert "Inspírate" in prompt or "referencia" in prompt.lower()

    def test_without_reference_song_is_unchanged(self) -> None:
        """build_user_prompt without reference_song should not include style hint."""
        prompt_with = build_user_prompt(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
            reference_song="Bachata Rosa",
        )
        prompt_without = build_user_prompt(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
        )
        assert "Bachata Rosa" in prompt_with
        assert "Bachata Rosa" not in prompt_without
        assert prompt_with != prompt_without


@pytest.fixture
def sample_result() -> LyricsResult:
    return LyricsResult(
        verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
        chorus={"lines": ["a", "b", "c", "d"]},
        title_suggestion="Test Canción",
        provider="openai",
    )


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.name = "openai"
    return provider


@pytest.mark.asyncio
async def test_generate_returns_lyrics_result(
    sample_result: LyricsResult, mock_provider: MagicMock,
) -> None:
    """generate() should return LyricsResult on success."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.return_value = sample_result

        got = await generate(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
        )
        assert got is not None
        assert got.provider == "openai"
        assert got.title_suggestion == "Test Canción"


@pytest.mark.asyncio
async def test_generate_calls_cascade_with_proper_prompt(
    sample_result: LyricsResult, mock_provider: MagicMock,
) -> None:
    """generate() should call cascade with a prompt built from inputs."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.return_value = sample_result

        await generate(
            recipient="Carlos",
            relationship="amigo",
            occasion="cumpleaños",
            genre="salsa",
            mood="festiva",
        )

        mock_cascade.assert_called_once()
        prompt_arg = mock_cascade.call_args[0][1]
        assert "Carlos" in prompt_arg
        assert "amigo" in prompt_arg
        assert "cumpleaños" in prompt_arg


@pytest.mark.asyncio
async def test_generate_includes_story(
    sample_result: LyricsResult, mock_provider: MagicMock,
) -> None:
    """generate() should include the story in the prompt when provided."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.return_value = sample_result

        await generate(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
            story="Nuestro primer viaje a la playa",
        )

        mock_cascade.assert_called_once()
        prompt_arg = mock_cascade.call_args[0][1]
        assert "primer viaje" in prompt_arg
        assert "playa" in prompt_arg


@pytest.mark.asyncio
async def test_generate_raises_error_on_all_failures(
    mock_provider: MagicMock,
) -> None:
    """generate() should raise LyricsGenerationError if cascade fails."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.side_effect = LyricsGenerationError("All LLM providers failed to generate")

        with pytest.raises(LyricsGenerationError, match="All LLM providers failed"):
            await generate(
                recipient="María",
                relationship="pareja",
                occasion="aniversario",
                genre="bachata",
                mood="romántica",
            )


@pytest.mark.asyncio
async def test_generate_no_providers_raises_error() -> None:
    """generate() should raise error if no providers configured."""
    with patch("app.lyrics._build_providers", return_value=[]), \
         pytest.raises(LyricsGenerationError, match="No LLM providers configured"):
            await generate(
                recipient="María",
                relationship="pareja",
                occasion="aniversario",
                genre="bachata",
                mood="romántica",
            )


@pytest.mark.asyncio
async def test_generate_without_story(
    sample_result: LyricsResult, mock_provider: MagicMock,
) -> None:
    """generate() should work without optional story field."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.return_value = sample_result

        got = await generate(
            recipient="Ana",
            relationship="hermana",
            occasion="cumpleaños",
            genre="pop",
            mood="alegre",
        )
        assert got is not None
        assert got.provider == "openai"


@pytest.mark.asyncio
async def test_generate_with_reference_song_passes_through(
    sample_result: LyricsResult, mock_provider: MagicMock,
) -> None:
    """generate() with reference_song should pass it to build_user_prompt."""
    with patch("app.lyrics.cascade_providers", new_callable=AsyncMock) as mock_cascade, \
         patch("app.lyrics._build_providers", return_value=[mock_provider]):
        mock_cascade.return_value = sample_result

        got = await generate(
            recipient="María",
            relationship="pareja",
            occasion="aniversario",
            genre="bachata",
            mood="romántica",
            reference_song="Bachata Rosa - Juan Luis Guerra",
        )
        assert got is not None

        prompt_arg = mock_cascade.call_args[0][1]
        # Cascade receives the full prompt which includes the reference song
        assert "Bachata Rosa" in prompt_arg
        assert "Juan Luis Guerra" in prompt_arg
