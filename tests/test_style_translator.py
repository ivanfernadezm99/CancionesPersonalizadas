"""Tests for app/lyrics/style_translator.py — Suno-safe style translation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.lyrics.style_translator import translate_style


@pytest.mark.asyncio
async def test_known_artist_uses_offline_map_without_llm() -> None:
    """Michael Jackson resolves from the offline map; no LLM call."""
    with patch(
        "app.lyrics.style_translator._llm_translate", new_callable=AsyncMock,
    ) as mock_llm:
        descriptor = await translate_style("Michael Jackson - Bad", "pop", "energética")
    assert descriptor is not None
    assert "funk" in descriptor.lower()
    assert "michael" not in descriptor.lower()
    mock_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_reference_returns_none() -> None:
    assert await translate_style(None, "pop", "romántica") is None
    assert await translate_style("", "pop", "romántica") is None


@pytest.mark.asyncio
async def test_non_artist_reference_calls_llm_and_returns_result() -> None:
    """A non-map reference delegates to the LLM; its result is returned."""
    with patch(
        "app.lyrics.style_translator._llm_translate",
        new=AsyncMock(return_value="synthpop bailable con sintetizadores"),
    ) as mock_llm:
        result = await translate_style("Alguna canción inventada", "pop", "energética")
    assert result == "synthpop bailable con sintetizadores"
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_failure_returns_none() -> None:
    """A failing LLM degrades to None so callers keep working."""
    with patch(
        "app.lyrics.style_translator._llm_translate",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await translate_style("Alguna canción inventada", "pop", "romántica")
    assert result is None
