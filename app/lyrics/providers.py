"""Multi-provider LLM clients for lyrics generation.

Provides OpenAI, Google Gemini, OpenRouter, and OpenCode Zen providers with a
cascade fallback mechanism. Each provider implements async generate() and the
cascade tries providers in order until one returns a valid result.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx

from app.models import Bridge, Chorus, LyricsResult, Verse

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Custom Exceptions ────────────────────────────────────────────────────────


class LyricsGenerationError(Exception):
    """Raised when all LLM providers fail to generate lyrics."""

    def __init__(self, message: str = "All LLM providers failed to generate lyrics") -> None:
        self.message = message
        super().__init__(message)


# ── JSON Parsing Utility ─────────────────────────────────────────────────────


def _parse_lyrics_json(text: str) -> LyricsResult | None:
    """Parse a JSON string into a LyricsResult, handling markdown fences."""
    try:
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            # Find the first and last ```
            lines = text.split("\n")
            start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith("```"):
                    start = i + 1
                    break
            end = len(lines)
            for i in range(len(lines) - 1, start - 1, -1):
                if lines[i].strip().startswith("```"):
                    end = i
                    break
            text = "\n".join(lines[start:end]).strip()

        data = json.loads(text)

        verses = []
        for v in data.get("verses", []):
            verses.append(Verse(number=v["number"], lines=v["lines"]))

        chorus_data = data.get("chorus", {})
        chorus = Chorus(lines=chorus_data.get("lines", []))

        bridge_data = data.get("bridge")
        bridge = (
            Bridge(lines=bridge_data["lines"])
            if bridge_data and bridge_data.get("lines")
            else None
        )

        return LyricsResult(
            verses=verses,
            chorus=chorus,
            bridge=bridge,
            title_suggestion=data.get("title_suggestion", "Canción Romántica"),
            provider="",  # Will be set by the specific provider
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse LLM response: %s", exc)
        return None


# ── Abstract Base Provider ───────────────────────────────────────────────────


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str, name: str) -> None:
        if not api_key:
            raise ValueError(f"{name.upper()}_API_KEY is not configured")
        self.api_key = api_key
        self.name = name

    @abstractmethod
    async def generate(self, prompt: str) -> LyricsResult | None:
        """Send prompt to the LLM and parse the response into LyricsResult.

        Returns LyricsResult on success, None on any error.
        """


# ── OpenAI Provider ──────────────────────────────────────────────────────────


class OpenAIProvider(BaseProvider):
    """Lyrics generation via OpenAI GPT-4o."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "openai")
        import openai

        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o"

    async def generate(self, prompt: str) -> LyricsResult | None:
        logger.info("Generating lyrics with OpenAI (%s)...", self.model)
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": (
                        "Eres un compositor de canciones románticas en español. "
                        "Genera letras de canciones con estructura poética. "
                        "Devuelve SOLO un objeto JSON válido."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=1500,
            )

            if not response.choices:
                logger.warning("OpenAI returned no choices")
                return None

            content = response.choices[0].message.content
            if not content:
                logger.warning("OpenAI returned empty content")
                return None

            result = _parse_lyrics_json(content)
            if result is not None:
                result.provider = self.name
            return result

        except Exception as exc:
            logger.warning("OpenAI generation failed: %s", exc)
            return None


# ── Gemini Provider ──────────────────────────────────────────────────────────


class GeminiProvider(BaseProvider):
    """Lyrics generation via Google Gemini REST API."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "gemini")
        self._client = httpx.AsyncClient(timeout=60.0)
        self._model = "gemini-flash-latest"

    async def generate(self, prompt: str) -> LyricsResult | None:
        logger.info("Generating lyrics with Gemini (%s)...", self._model)
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self._model}:generateContent?key={self.api_key}"
            )
            response = await self._client.post(
                url,
                json={
                    "contents": [{
                        "parts": [{
                            "text": (
                                "Eres un compositor de canciones románticas en español.\n"
                                f"{prompt}\n\n"
                                "Devuelve SOLO un objeto JSON válido."
                            )
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 1500,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                logger.warning("Gemini returned no candidates")
                return None

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                logger.warning("Gemini returned empty text")
                return None

            result = _parse_lyrics_json(text)
            if result is not None:
                result.provider = self.name
            return result

        except Exception as exc:
            logger.warning("Gemini generation failed: %s", exc)
            return None


# ── OpenAI-Compatible Providers (OpenRouter, Zen) ───────────────────────────


class OpenAICompatProvider(BaseProvider):
    """Base for OpenAI-compatible ``/chat/completions`` providers.

    Parametrized by name, api_key, model, base_url, and request headers.
    Reads the JSON answer from ``choices[0]["message"]["content"]`` and ignores
    reasoning fields (``reasoning_content``/``reasoning_details``) that
    reasoning models may return alongside ``content``.
    """

    def __init__(
        self,
        name: str,
        api_key: str,
        model: str,
        base_url: str,
        headers: dict[str, str],
    ) -> None:
        super().__init__(api_key, name)
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=60.0,
        )

    async def generate(self, prompt: str) -> LyricsResult | None:
        logger.info("Generating lyrics with %s (%s)...", self.name, self.model)
        try:
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": (
                            "Eres un compositor de canciones románticas en español. "
                            "Devuelve SOLO un objeto JSON válido."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            if not choices:
                logger.warning("%s returned no choices", self.name)
                return None

            content = choices[0].get("message", {}).get("content")
            if not content:
                logger.warning("%s returned empty content", self.name)
                return None

            result = _parse_lyrics_json(content)
            if result is not None:
                result.provider = self.name
            return result

        except Exception as exc:
            logger.warning("%s generation failed: %s", self.name, exc)
            return None


class OpenRouterProvider(OpenAICompatProvider):
    """Lyrics generation via OpenRouter API."""

    def __init__(self, api_key: str) -> None:
        super().__init__(
            name="openrouter",
            api_key=api_key,
            model="openai/gpt-4o-mini",
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://canciones-personalizadas.app",
            },
        )


# Zen model → cascade entry name mapping (keeps result.provider transparent).
_ZEN_MODEL_ENTRY_NAMES: dict[str, str] = {
    "big-pickle": "zen-big-pickle",
    "nemotron-3-ultra-free": "zen-nemotron",
}


class ZenProvider(OpenAICompatProvider):
    """Lyrics generation via OpenCode Zen (free, OpenAI-compatible endpoint).

    Zen reasoning models (Big Pickle, Nemotron) return the JSON answer in
    ``message.content`` — this provider reads ``content`` only and ignores
    ``reasoning_content``/``reasoning_details``. Empty content yields None so
    the cascade falls through to the next provider.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("ZEN_API_KEY is not configured")
        super().__init__(
            name=_ZEN_MODEL_ENTRY_NAMES.get(model, f"zen-{model}"),
            api_key=api_key,
            model=model,
            base_url="https://opencode.ai/zen/v1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )


# ── Cascade Logic ────────────────────────────────────────────────────────────


async def cascade_providers(
    providers: list[BaseProvider],
    prompt: str,
) -> LyricsResult:
    """Try each provider in order until one returns a valid result.

    Args:
        providers: Ordered list of provider instances to try.
        prompt: The prompt string to send to each provider.

    Returns:
        The first valid LyricsResult.

    Raises:
        LyricsGenerationError: If all providers fail.
    """
    if not providers:
        raise LyricsGenerationError("No LLM providers configured")

    errors: list[str] = []
    for provider in providers:
        try:
            result = await provider.generate(prompt)
            if result is not None:
                logger.info("Lyrics generated successfully by %s", provider.name)
                return result
            errors.append(f"{provider.name}: returned no result")
        except Exception as exc:
            errors.append(f"{provider.name}: {exc}")
            logger.warning("Provider %s failed: %s", provider.name, exc)

    raise LyricsGenerationError(
        f"All LLM providers failed to generate lyrics ({'; '.join(errors)})"
    )
