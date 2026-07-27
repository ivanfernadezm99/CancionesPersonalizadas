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
from app.voice.registry import VOICE_REGISTRY, get_voice


def get_available_voices() -> list[VoiceConfig]:
    """Return all registered voice configurations."""
    return list(VOICE_REGISTRY.values())


def build_prompt(voice_id: str, genre: str, mood: str) -> str:
    """Build a Lyria 3 prompt combining voice descriptor, genre, and mood.

    Args:
        voice_id: Voice identifier (e.g. "female", "male").
        genre: Musical genre (e.g. "bachata", "balada", "reggaeton").
        mood: Emotional tone (e.g. "romántica", "festiva").

    Returns:
        A Spanish prompt string suitable for Lyria 3 music generation.

    Raises:
        ValueError: If voice_id is not found in the registry.
    """
    voice = get_voice(voice_id)
    if voice is None:
        valid = ", ".join(VOICE_REGISTRY.keys())
        raise ValueError(f"Unknown voice '{voice_id}'. Valid options: {valid}")

    return f"Una canción {mood} de {genre}. {voice.prompt_es}. Estilo musical {genre}."
