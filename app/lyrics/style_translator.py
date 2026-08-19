"""Translate a user's reference (song/artist) into a Suno-safe style descriptor.

Suno rejects specific artist names in style tags. When a user asks for a
reference like "Michael Jackson - Bad", naming the artist would fail. This
module translates the reference into a written musical descriptor WITHOUT
naming any artist, so the generation stays close to the requested vibe while
remaining Suno-safe.

Strategy (fast → best-effort):
  1. Offline curated map (``ARTIST_STYLE_DESCRIPTORS``) for known artists.
  2. LLM translation of any other reference into a 1-2 sentence descriptor.
  3. ``None`` on any failure — callers fall back to their existing behavior.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.tag_sanitizer import artist_style_for

logger = logging.getLogger(__name__)

_STYLE_SYSTEM = (
    "Sos un experto en producción musical generativa. Convertí la referencia "
    "(la canción o el artista que el usuario menciona) en un descriptor de "
    "estilo musical en español de una o dos frases, listo para usarse como tag "
    "de Suno. NO nombres artistas, ni grupos, ni canciones concretas, ni "
    "nombres propios: describí solo el género, el tempo, los instrumentos, la "
    "vibra y la producción. Respondé únicamente con el descriptor, sin "
    "comillas ni etiquetas."
)


async def translate_style(
    reference_song: str | None,
    genre: str,
    mood: str,
) -> str | None:
    """Return a Suno-safe style descriptor for ``reference_song``, or ``None``.

    Uses the offline map when a known artist is detected; otherwise asks an
    LLM to translate the reference. Never raises — returns ``None`` so callers
    fall back to existing prompt behavior.
    """
    if not reference_song:
        return None

    offline = artist_style_for(reference_song)
    if offline:
        logger.info("Style reference resolved from offline map: %r", reference_song)
        return offline

    try:
        return await _llm_translate(reference_song, genre, mood)
    except Exception as exc:  # noqa: BLE001 - translator is best-effort
        logger.warning("Style translation failed, using fallback: %s", exc)
        return None


async def _llm_translate(reference_song: str, genre: str, mood: str) -> str | None:
    """Ask an OpenAI-compatible provider for a Suno-safe descriptor."""
    base_url, api_key, model = _pick_provider()
    if not base_url or not api_key or not model:
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _STYLE_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f'Referencia: "{reference_song}". '
                            f"Género pedido: {genre}. Ánimo pedido: {mood}."
                        ),
                    },
                ],
                "temperature": 0.7,
                "max_tokens": 120,
            },
        )
        resp.raise_for_status()
        text = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        text = (text or "").strip()
        return text[:400] if text else None


def _pick_provider() -> tuple[str | None, str | None, str | None]:
    """Return ``(base_url, api_key, model)`` for the first configured provider."""
    api_key: str | None = getattr(settings, "OPENAI_API_KEY", None)
    if api_key:
        base = getattr(settings, "OPENAI_BASE_URL", None) or "https://api.openai.com/v1"
        return base, api_key, "gpt-4o-mini"

    zen_key: str | None = getattr(settings, "ZEN_API_KEY", None)
    if zen_key:
        model = getattr(settings, "ZEN_MODEL", None) or "deepseek-v3"
        return "https://opencode.ai/zen/v1", zen_key, model

    for key in ("GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        k = getattr(settings, key, None)
        if k:
            # Fall back to OpenAI-compatible shapes where available.
            if key == "OPENROUTER_API_KEY":
                return "https://openrouter.ai/api/v1", k, "openai/gpt-4o-mini"
            return None, k, None
    return None, None, None
