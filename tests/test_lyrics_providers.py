"""Tests for app/lyrics/providers.py — Multi-provider LLM clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.lyrics.providers import (
    GeminiProvider,
    LyricsGenerationError,
    OpenAIProvider,
    OpenRouterProvider,
    cascade_providers,
)
from app.models import LyricsResult

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_prompt() -> str:
    return "Escribe una canción romántica para María"


@pytest.fixture
def valid_lyrics_json() -> str:
    return (
        '{\n'
        '  "verses": [\n'
        '    {"number": 1, "lines": ["Línea uno del verso", "Línea dos del verso", '
        '"Línea tres del verso", "Línea cuatro del verso"]},\n'
        '    {"number": 2, "lines": ["Otra línea uno", "Otra línea dos", '
        '"Otra línea tres", "Otra línea cuatro"]}\n'
        '  ],\n'
        '  "chorus": {"lines": ["Coro línea uno", "Coro línea dos", '
        '"Coro línea tres", "Coro línea cuatro"]},\n'
        '  "bridge": {"lines": ["Puente línea uno", "Puente línea dos"]},\n'
        '  "title_suggestion": "María, Mi Amor"\n'
        "}"
    )


# ── OpenAI Provider Tests ────────────────────────────────────────────────────


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_init_with_no_key_raises_error(self) -> None:
        """OpenAIProvider should raise ValueError if no API key."""
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            OpenAIProvider(api_key="")

    def test_init_with_key_succeeds(self) -> None:
        """OpenAIProvider should initialize with a valid key."""
        provider = OpenAIProvider(api_key="sk-test123")
        assert provider.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_generate_returns_lyrics_result(
        self, sample_prompt: str, valid_lyrics_json: str,
    ) -> None:
        """generate() should return LyricsResult on successful API call."""
        provider = OpenAIProvider(api_key="sk-test123")
        target = provider.client.chat.completions

        with patch.object(target, "create", new_callable=AsyncMock) as mock_create:
            mock_response = AsyncMock()
            mock_response.choices = [
                AsyncMock(message=AsyncMock(content=valid_lyrics_json))
            ]
            mock_create.return_value = mock_response

            result = await provider.generate(sample_prompt)
            assert result is not None
            assert isinstance(result, LyricsResult)
            assert result.provider == "openai"
            assert result.title_suggestion == "María, Mi Amor"
            assert len(result.verses) == 2
            assert len(result.chorus.lines) == 4

    @pytest.mark.asyncio
    async def test_generate_returns_none_on_api_error(
        self, sample_prompt: str,
    ) -> None:
        """generate() should return None on API errors."""
        provider = OpenAIProvider(api_key="sk-test123")
        target = provider.client.chat.completions

        with patch.object(target, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=httpx.Request(
                    "POST", "https://api.openai.com/v1/chat/completions",
                ),
                response=httpx.Response(401),
            )

            result = await provider.generate(sample_prompt)
            assert result is None

    @pytest.mark.asyncio
    async def test_generate_returns_none_on_parse_failure(
        self, sample_prompt: str,
    ) -> None:
        """generate() should return None if JSON parsing fails."""
        provider = OpenAIProvider(api_key="sk-test123")
        target = provider.client.chat.completions

        with patch.object(target, "create", new_callable=AsyncMock) as mock_create:
            mock_response = AsyncMock()
            mock_response.choices = [
                AsyncMock(message=AsyncMock(content="not valid json"))
            ]
            mock_create.return_value = mock_response

            result = await provider.generate(sample_prompt)
            assert result is None

    @pytest.mark.asyncio
    async def test_generate_returns_none_on_timeout(
        self, sample_prompt: str,
    ) -> None:
        """generate() should return None on timeout."""
        provider = OpenAIProvider(api_key="sk-test123")
        target = provider.client.chat.completions

        with patch.object(target, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = httpx.TimeoutException("timeout")

            result = await provider.generate(sample_prompt)
            assert result is None


# ── Gemini Provider Tests ────────────────────────────────────────────────────


class TestGeminiProvider:
    """Tests for GeminiProvider."""

    def test_init_with_no_key_raises_error(self) -> None:
        """GeminiProvider should raise ValueError if no API key."""
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiProvider(api_key="")

    @pytest.mark.asyncio
    async def test_generate_returns_lyrics_result(
        self, sample_prompt: str, valid_lyrics_json: str,
    ) -> None:
        """generate() should return LyricsResult on success."""
        provider = GeminiProvider(api_key="test-key")

        mock_model = AsyncMock()
        mock_response = AsyncMock()
        mock_response.text = f"```json\n{valid_lyrics_json}\n```"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.generate(sample_prompt)
            assert result is not None
            assert isinstance(result, LyricsResult)
            assert result.provider == "gemini"

    @pytest.mark.asyncio
    async def test_generate_returns_none_on_error(
        self, sample_prompt: str,
    ) -> None:
        """generate() should return None on API errors."""
        provider = GeminiProvider(api_key="test-key")

        mock_model = AsyncMock()
        mock_model.generate_content_async = AsyncMock(side_effect=Exception("API error"))

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.generate(sample_prompt)
            assert result is None


# ── OpenRouter Provider Tests ────────────────────────────────────────────────


class TestOpenRouterProvider:
    """Tests for OpenRouterProvider."""

    def test_init_with_no_key_raises_error(self) -> None:
        """OpenRouterProvider should raise ValueError if no API key."""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            OpenRouterProvider(api_key="")

    @pytest.mark.asyncio
    async def test_generate_returns_lyrics_result(
        self, sample_prompt: str, valid_lyrics_json: str,
    ) -> None:
        """generate() should return LyricsResult on success."""
        provider = OpenRouterProvider(api_key="or-test123")

        with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                "choices": [{"message": {"content": valid_lyrics_json}}],
            })
            mock_post.return_value = mock_response

            result = await provider.generate(sample_prompt)
            assert result is not None
            assert isinstance(result, LyricsResult)
            assert result.provider == "openrouter"

    @pytest.mark.asyncio
    async def test_generate_returns_none_on_error(
        self, sample_prompt: str,
    ) -> None:
        """generate() should return None on API errors."""
        provider = OpenRouterProvider(api_key="or-test123")

        with patch.object(provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "402 Payment Required",
                request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
                response=httpx.Response(402),
            )

            result = await provider.generate(sample_prompt)
            assert result is None


# ── Cascade Tests ────────────────────────────────────────────────────────────


class MockProvider:
    """Mock provider for testing cascade logic."""

    def __init__(
        self, name: str,
        result: LyricsResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._result = result
        self._error = error

    async def generate(self, _prompt: str) -> LyricsResult | None:
        if self._error:
            raise self._error
        return self._result


class TestCascadeProviders:
    """Tests for cascade_providers()."""

    def _make_result(self, provider: str) -> LyricsResult:
        return LyricsResult(
            verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
            chorus={"lines": ["a", "b", "c", "d"]},
            title_suggestion="Test",
            provider=provider,
        )

    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self, sample_prompt: str) -> None:
        """Should return result from the first provider if it succeeds."""
        providers = [
            MockProvider("first", result=self._make_result("first")),
            MockProvider("never_called"),
        ]

        result = await cascade_providers(providers, sample_prompt)  # type: ignore[arg-type]
        assert result is not None
        assert result.provider == "first"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, sample_prompt: str) -> None:
        """Should fall back to second provider if first fails."""
        providers = [
            MockProvider("first", result=None),
            MockProvider("second", result=self._make_result("second")),
        ]

        result = await cascade_providers(providers, sample_prompt)  # type: ignore[arg-type]
        assert result is not None
        assert result.provider == "second"

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_error(self, sample_prompt: str) -> None:
        """Should raise LyricsGenerationError if all providers fail."""
        providers = [
            MockProvider("a", result=None),
            MockProvider("b", result=None),
        ]

        with pytest.raises(LyricsGenerationError, match="All LLM providers failed"):
            await cascade_providers(providers, sample_prompt)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_empty_providers_list_raises_error(self, sample_prompt: str) -> None:
        """Should raise LyricsGenerationError with no providers."""
        with pytest.raises(LyricsGenerationError, match="No LLM providers"):
            await cascade_providers([], sample_prompt)
