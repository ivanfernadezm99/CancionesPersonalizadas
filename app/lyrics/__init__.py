"""Lyrics generation orchestrator.

Builds genre-specific Spanish prompts and cascades through configured
LLM providers (Zen → OpenAI → Gemini → OpenRouter) until one returns valid
structured lyrics.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.lyrics.prompts import SYSTEM_PROMPT, build_user_prompt
from app.lyrics.providers import (
    BaseProvider,
    DeepSeekProvider,
    GeminiProvider,
    LyricsGenerationError,
    OpenAIProvider,
    OpenCodeGoProvider,
    OpenRouterProvider,
    ZenProvider,
    cascade_providers,
)
from app.models import LyricsResult

logger = logging.getLogger(__name__)


def _build_providers() -> list[BaseProvider]:
    """Build provider instances based on configured API keys."""
    providers: list[BaseProvider] = []

    if settings.ZEN_API_KEY:
        providers.append(
            ZenProvider(api_key=settings.ZEN_API_KEY, model=settings.ZEN_PRIMARY_MODEL)
        )
        providers.append(
            ZenProvider(api_key=settings.ZEN_API_KEY, model=settings.ZEN_SECONDARY_MODEL)
        )
    if settings.OPENCODE_GO_API_KEY:
        providers.append(
            OpenCodeGoProvider(
                api_key=settings.OPENCODE_GO_API_KEY,
                model=settings.OPENCODE_GO_MODEL,
            )
        )
    if settings.DEEPSEEK_API_KEY:
        providers.append(
            DeepSeekProvider(api_key=settings.DEEPSEEK_API_KEY, model=settings.DEEPSEEK_MODEL)
        )
    if settings.OPENAI_API_KEY:
        providers.append(OpenAIProvider(api_key=settings.OPENAI_API_KEY))
    if settings.GEMINI_API_KEY:
        providers.append(GeminiProvider(api_key=settings.GEMINI_API_KEY))
    if settings.OPENROUTER_API_KEY:
        providers.append(OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY))

    return providers


async def generate(
    recipient: str,
    relationship: str,
    occasion: str,
    genre: str,
    mood: str,
    story: str | None = None,
    reference_song: str | None = None,
    reference_description: str | None = None,
    idea: str | None = None,
) -> LyricsResult:
    """Generate lyrics using the multi-provider cascade.

    Args:
        recipient: Name of the song recipient.
        relationship: Relationship type (e.g. "pareja", "amigo").
        occasion: Occasion (e.g. "cumpleaños", "aniversario").
        genre: Musical genre.
        mood: Emotional tone.
        story: Optional personal story or anecdote.
        reference_song: Optional reference song for style inspiration.
        reference_description: Optional style description from audio analysis.
        idea: Optional free-text thematic seed for the lyrics (RQ-LYR-07).

    Returns:
        A structured LyricsResult containing verses, chorus, and metadata.

    Raises:
        LyricsGenerationError: If all configured providers fail to generate.
    """
    user_prompt = build_user_prompt(
        recipient=recipient,
        relationship=relationship,
        occasion=occasion,
        genre=genre,
        mood=mood,
        story=story,
        reference_song=reference_song,
        reference_description=reference_description,
        idea=idea,
    )

    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    providers = _build_providers()
    if not providers:
        raise LyricsGenerationError(
            "No LLM providers configured — set at least one API key "
            "(ZEN_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY)"
        )

    logger.info(
        "Generating lyrics for %s (%s, %s) with %d provider(s)...",
        recipient, genre, mood, len(providers),
    )

    return await cascade_providers(providers, full_prompt)
