"""VoiceConfig dictionary registry with startup validation."""

from __future__ import annotations

import logging

from app.models import VoiceConfig

logger = logging.getLogger(__name__)

# ── Voice Registry ───────────────────────────────────────────────────────────
# Add new voices here following the same VoiceConfig structure.
# Each key must match the voice ID and be lowercase.

VOICE_REGISTRY: dict[str, VoiceConfig] = {
    "female": VoiceConfig(
        id="female",
        label="Voz Femenina",
        gender="female",
        prompt_es="cantante femenina española, voz dulce y melódica",
    ),
    "male": VoiceConfig(
        id="male",
        label="Voz Masculina",
        gender="male",
        prompt_es="cantante masculino español, voz cálida y romántica",
    ),
    "es-latino-male": VoiceConfig(
        id="es-latino-male",
        label="Español hombre latino",
        gender="male",
        prompt_es="voz masculina latina, cantante hombre latinoamericano, cálida y expresiva",
    ),
    "es-espana-male": VoiceConfig(
        id="es-espana-male",
        label="Español hombre España",
        gender="male",
        prompt_es="voz masculina española, cantante masculino español, cálida y romántica",
    ),
    "es-espana-female": VoiceConfig(
        id="es-espana-female",
        label="Mujer española",
        gender="female",
        prompt_es="voz femenina española, cantante femenina española, dulce y melódica",
    ),
    "es-latina-female": VoiceConfig(
        id="es-latina-female",
        label="Mujer latina",
        gender="female",
        prompt_es="voz femenina latina, cantante mujer latina, dulce y apasionada",
    ),
    "es-espana-child": VoiceConfig(
        id="es-espana-child",
        label="Voz infantil española",
        gender="child",
        prompt_es="voz infantil española, niño cantando, inocente y tierno",
    ),
}


def get_voice(voice_id: str) -> VoiceConfig | None:
    """Look up a voice configuration by ID.

    Returns the VoiceConfig if found, or None for unknown IDs.
    Lookup is case-sensitive — IDs must be lowercase.
    """
    return VOICE_REGISTRY.get(voice_id)


def validate_registry() -> None:
    """Validate the voice registry at startup.

    Raises:
        ValueError: If the registry is empty or contains invalid entries.
    """
    if not VOICE_REGISTRY:
        raise ValueError("Voice registry is empty — at least one voice must be defined")

    for voice_id, entry in VOICE_REGISTRY.items():
        if not isinstance(entry, VoiceConfig):
            raise ValueError(
                f"Invalid entry '{voice_id}' in voice registry: "
                f"expected VoiceConfig, got {type(entry).__name__}"
            )
        if entry.id != voice_id:
            logger.warning(
                "Voice registry key '%s' does not match entry.id '%s'",
                voice_id,
                entry.id,
            )

    logger.info("Voice registry validated: %d voices available", len(VOICE_REGISTRY))
    for voice_id, entry in VOICE_REGISTRY.items():
        logger.debug("  - %s: %s", voice_id, entry.label)
