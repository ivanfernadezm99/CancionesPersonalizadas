"""Spanish prompt templates for LLM-based lyrics generation.

Templates vary by genre to produce genre-appropriate vocabulary, rhyme
schemes, and rhythm in Spanish.
"""

from __future__ import annotations

from typing import Final

SYSTEM_PROMPT: Final[str] = (
    "Eres un compositor de canciones románticas en español. "
    "Genera letras de canciones con estructura poética y rima "
    "apropiada para el género musical solicitado. "
    "Las letras deben ser en español natural, romántico y emotivo. "
    "Cada verso debe tener 4 líneas. El coro debe tener 4 líneas. "
    "Incluye el nombre del destinatario en el coro y al menos una vez en los versos. "
    "Las líneas deben tener entre 10 y 100 caracteres cada una. "
    "Devuelve SOLO un objeto JSON válido con esta estructura exacta, sin texto adicional:\n"
    '{\n'
    '  "verses": [{"number": 1, "lines": ["línea1", "línea2", "línea3", "línea4"]}],\n'
    '  "chorus": {"lines": ["línea1", "línea2", "línea3", "línea4"]},\n'
    '  "bridge": {"lines": ["línea1", "línea2"]},\n'
    '  "title_suggestion": "Título sugerido"\n'
    "}"
)

# ── Genre-specific prompt additions ──────────────────────────────────────────

_GENRE_PROMPTS: dict[str, str] = {
    "bachata": (
        "Género: bachata romántica dominicana. "
        "Usa rima consonante. Letras nostálgicas y apasionadas. "
        "Estructura: verso - coro - verso - coro - puente - coro final. "
        "Vocabulario: amor, corazón, dolor, pasión, besos, guitarra."
    ),
    "balada": (
        "Género: balada romántica pop. "
        "Letras emotivas y melódicas. Estrofas de 4 líneas con rima asonante. "
        "Estructura: verso - coro - verso - coro - coro final. "
        "Vocabulario: amor, vida, sueños, corazón, siempre, estrella."
    ),
    "reggaeton": (
        "Género: reggaetón romántico. "
        "Letras con ritmo urbano, lenguaje informal y juvenil. "
        "Líneas más cortas y directas. Estribillo pegadizo y repetitivo. "
        "Estructura: intro - verso - coro - verso - coro - coro final. "
        "Vocabulario: baby, noche, bailar, fuego, pasión, dulce."
    ),
    "salsa": (
        "Género: salsa romántica. "
        "Letras apasionadas con ritmo bailable. Rima consonante. "
        "Estructura: intro - verso - coro - montuno - verso - coro - final. "
        "Vocabulario: amor, ritmo, calor, son, salsa, bailar, pasión."
    ),
    "pop": (
        "Género: pop romántico latino. "
        "Letras positivas y modernas. Estribillo pegadizo. "
        "Estructura: verso - coro - verso - coro - puente - coro final. "
        "Vocabulario: amor, luz, sonrisa, magia, corazón, destino."
    ),
    "cumbia": (
        "Género: cumbia romántica. "
        "Letras alegres y bailables con tono romántico. "
        "Estructura: intro - verso - coro - verso - coro - coro final. "
        "Vocabulario: amor, baile, alegría, ritmo, flor, sonrisa."
    ),
    "vallenato": (
        "Género: vallenato romántico. "
        "Letras nostálgicas y costumbristas. Rima consonante. "
        "Estructura: verso - coro - verso - coro - puente - coro final. "
        "Vocabulario: amor, recuerdo, acordeón, camino, tierra, sentimiento."
    ),
    "trap": (
        "Género: trap romántico latino. "
        "Letras urbanas con flow moderno. Líneas cortas y directas. "
        "Estructura: intro - verso - coro - verso - coro - outro. "
        "Vocabulario: baby, noche, hielo, dinero, amor, corazón, flow."
    ),
}


def build_user_prompt(
    recipient: str,
    relationship: str,
    occasion: str,
    genre: str,
    mood: str,
    story: str | None = None,
) -> str:
    """Build the full user prompt for the LLM based on input parameters.

    Args:
        recipient: Name of the song recipient.
        relationship: Relationship type (e.g. "pareja", "amigo").
        occasion: Occasion (e.g. "cumpleaños", "aniversario").
        genre: Musical genre.
        mood: Emotional tone.
        story: Optional personal story or anecdote (max 2000 chars).

    Returns:
        A complete Spanish prompt string for the LLM.
    """
    genre_instructions = _GENRE_PROMPTS.get(genre.lower(), _GENRE_PROMPTS["pop"])

    parts = [
        f"Escribe una canción romántica para {recipient}, mi {relationship}.",
        f"Ocasión: {occasion}.",
        f"Tono: {mood}.",
        genre_instructions,
    ]

    if story:
        story = story[:2000]
        parts.append(f"Anecdoticas personales para incluir: {story}")

    parts.append(
        f"Asegúrate de que el nombre '{recipient}' aparezca en el coro "
        f"y al menos una vez en los versos."
    )

    return "\n\n".join(parts)
