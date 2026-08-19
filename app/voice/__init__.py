"""Voice selection and prompt building for music generation.

Provides a voice selection abstraction layer for Lyria 3 music generation.
Supports male and female Spanish voices in v0 with a documented extension
point for future voice types (v1+).

## Extension Guide (v1+)

To add a new voice type:

1. Add a new entry to `app/voice/registry.py:VOICE_REGISTRY`:
   ```python
   VOICE_REGISTRY["celebrity_x"] = VoiceConfig(
       id="celebrity_x",
       label="Voz de Artista X",
       gender="male",  # or "female"
       prompt_es="cantante masculino con voz ronca española",
   )
   ```
2. Validation at startup will pick it up automatically.
3. No other code changes are needed — the new voice will be available
   in the API and prompt builder.
"""

from __future__ import annotations

from app.models import VoiceConfig
from app.tag_sanitizer import (
    artist_style_for,
    sanitize_reference_song,
)
from app.voice.registry import VOICE_REGISTRY, get_voice


def get_available_voices() -> list[VoiceConfig]:
    """Return all registered voice configurations."""
    return list(VOICE_REGISTRY.values())


def build_prompt(
    voice_id: str,
    genre: str,
    mood: str,
    reference_song: str | None = None,
    reference_description: str | None = None,
    reference_style: str | None = None,
) -> str:
    """Build a Lyria 3 prompt combining voice descriptor, genre, and mood.

    Args:
        voice_id: Voice identifier (e.g. "female", "male").
        genre: Musical genre (e.g. "bachata", "balada", "reggaeton").
        mood: Emotional tone (e.g. "romántica", "festiva").
        reference_song: Optional reference song name for style inspiration.
        reference_description: Optional detailed style description from audio analysis.
        reference_style: Optional pre-translated, Suno-safe style descriptor
            (from the offline artist map or the LLM translator). Appended
            verbatim; must NOT name specific artists.

    Returns:
        A Spanish prompt string suitable for Lyria 3 music generation.

    Raises:
        ValueError: If voice_id is not found in the registry.
    """
    voice = get_voice(voice_id)
    if voice is None:
        valid = ", ".join(VOICE_REGISTRY.keys())
        raise ValueError(f"Unknown voice '{voice_id}'. Valid options: {valid}")

    # Rich musical prompt with structural guidance for Lyria 3
    prompt = (
        f"Una canción {mood} de {genre}. {voice.prompt_es}. "
        f"Melodía con estructura completa: introducción suave, desarrollo emotivo, "
        f"clímax apasionado alrededor del minuto 1:20, y cierre con fade-out delicado. "
        f"Ritmo de {genre} auténtico, con dinámica variada — "
        f"empieza suave e íntimo, crece en intensidad. "
        f"Calidad de producción profesional, sonido cálido con instrumentos reales. "
        f"Duración mínima 2:30."
    )
    if reference_description:
        prompt += f" {reference_description}"
    elif reference_style:
        # Pre-translated Suno-safe descriptor (LLM or offline artist map).
        prompt += f" {reference_style}."
    elif reference_song:
        # Known artist → its curated Suno-safe descriptor (RQ-TAG-05).
        artist_style = artist_style_for(reference_song)
        if artist_style:
            prompt += f" {artist_style}."
        else:
            # Generation-time guard (RQ-VOI-05, RQ-TAG-04): sanitize before
            # injecting so legacy stored values ("Song - Artist") never reach
            # the Lyria/Suno prompt; a "no usable reference" appends nothing.
            song = sanitize_reference_song(reference_song)
            if song:
                prompt += f" Inspirada en el estilo de {song}."
    return prompt
