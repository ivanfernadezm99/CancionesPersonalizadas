"""Shared reference-song sanitizer for Suno tag validation.

Pure, dependency-free module: no I/O, no app imports — zero circular-import
risk. Applied at three layers (RQ-TAG-04): input validation (Pydantic 422),
generation time (``build_prompt`` + lyrics builder, covering legacy projects
and both worker paths), and the Suno error translator as a safety net.
Mirrored client-side in the frontend (strip-only heuristic).
"""

from __future__ import annotations

import re

# Shared friendly Spanish message (design decision 6): one constant reused by
# the Pydantic validator (422 response) and by SunoProvider._translate_suno_error
# (persisted job error) so the two never drift apart.
ARTIST_REJECTION_MESSAGE = (
    "El nombre de la canción de referencia contiene un artista. "
    "Por favor quitá el nombre del artista y probá de nuevo."
)

# Curated blocklist of known-rejected artist names (RQ-TAG-02). Stored
# lowercase and matched as a case-insensitive substring (design decision 5).
# Seed set per RQ-TAG-02/03; extensible.
ARTIST_BLOCKLIST: frozenset[str] = frozenset(
    {"los palmeras", "la mona jiménez", "juan luis guerra"}
)

# Separator patterns (RQ-TAG-01). Applied in order (parenthesized artists
# are trailing, so parens first avoids mis-splitting "Mi Viejo (En Vivo)"):
#   "Bachata Rosa - Juan Luis Guerra"  →  "Bachata Rosa"
#   "Bailando de Enrique Iglesias"     →  "Bailando"
#   "La Bamba (Los Lobos)"             →  "La Bamba"
_TRAILING_PARENS = re.compile(r"\s*\([^)]*\)\s*$")
_DASH_SEPARATOR = re.compile(r"\s+-\s+")
_DE_SEPARATOR = re.compile(r"\s+de\s+", re.IGNORECASE)


def _is_blocked(token: str) -> bool:
    """True when the token contains any blocklist entry (case-insensitive)."""
    lowered = token.lower()
    return any(artist in lowered for artist in ARTIST_BLOCKLIST)


def _pick_song_side(text: str, separator: re.Pattern[str], *, tie: str) -> str:
    """Split once on ``separator`` and keep the song side, blocklist-aware.

    - If exactly one side contains a blocklist artist, that side is dropped
      and the other side is the song (design decision 4: "Los Palmeras - Mi
      Amor" must strip to the usable song "Mi Amor", not be rejected; and
      RQ-TAG-01: "Bachata Rosa - Juan Luis Guerra" → "Bachata Rosa").
    - If both sides are blocklisted, no usable reference remains.
    - If neither side is blocklisted, the format decides the song side:
      ``tie="right"`` for the dash pattern ("Artist - Song" input such as
      "Coldplay - Yellow" → "Yellow", tasks 6.3) and ``tie="left"`` for the
      "Song de Artist" pattern ("Bailando de Enrique Iglesias" → "Bailando").

    Returns ``text`` unchanged when the separator is absent.
    """
    parts = separator.split(text, maxsplit=1)
    if len(parts) < 2:
        return text
    left, right = parts[0].strip(), parts[1].strip()
    left_blocked = _is_blocked(left)
    right_blocked = _is_blocked(right)
    if left_blocked and right_blocked:
        return ""
    if left_blocked:
        return right
    if right_blocked:
        return left
    return left if tie == "left" else right


def sanitize_reference_song(value: str | None) -> str | None:
    """Return the song token from ``value``, or ``None`` when unusable.

    Strips artist tokens for the safe patterns ``"Song - Artist"``,
    ``"Song de Artist"``, and ``"Song (Artist)"`` (case-insensitive,
    whitespace-trimmed), then substring-matches the result against
    ``ARTIST_BLOCKLIST`` (case-insensitive). Returns ``None`` when no usable
    reference remains: artist-only input, blocklist hit, empty string, or
    ``None`` (RQ-TAG-03).

    Idempotent: ``sanitize_reference_song(sanitize_reference_song(x))`` equals
    ``sanitize_reference_song(x)`` — safe for the layered, defense-in-depth
    application at both prompt builders and both workers.
    """
    if value is None:
        return None
    song = value.strip()
    if not song:
        return None

    song = _TRAILING_PARENS.sub("", song).strip()
    song = _pick_song_side(song, _DASH_SEPARATOR, tie="right").strip()
    song = _pick_song_side(song, _DE_SEPARATOR, tie="left").strip()

    if not song:
        return None

    # Final guard: covers no-separator inputs (e.g. "Grupo Los Palmeras").
    if _is_blocked(song):
        return None

    return song
