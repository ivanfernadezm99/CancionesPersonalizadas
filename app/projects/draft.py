"""Draft lyrics normalization for the lyrics-draft endpoint (RQ-DRAFT-03).

Normalizes a generated :class:`LyricsResult` so the returned draft conforms to
the output schema: non-empty Spanish lines, ``language="es"``, and a minimum of
10 total lines. If the draft is too short, raises
:class:`LyricsGenerationError` which the route maps to a 503.
"""

from __future__ import annotations

from app.lyrics.providers import LyricsGenerationError
from app.models import Bridge, Chorus, LyricsResult, Verse


def _strip_lines(lines: list[str]) -> list[str]:
    """Return non-empty, stripped lines."""
    return [line.strip() for line in lines if line.strip()]


def normalize_draft(result: LyricsResult) -> LyricsResult:
    """Normalize a generated draft for the lyrics-draft endpoint.

    - Strips each line and removes empty lines
    - Pins ``language`` to ``"es"`` (RQ-DRAFT-03)
    - Raises ``LyricsGenerationError`` if the total line count is below 10

    Args:
        result: The raw result from ``lyrics_generate``.

    Returns:
        A normalized ``LyricsResult`` conforming to the output schema.

    Raises:
        LyricsGenerationError: If total lines after stripping are < 10.
    """
    # Filter out sections whose lines are all empty after stripping. A verse or
    # bridge that strips to zero lines would violate the output schema's
    # min_length=1 and leak a pydantic ValidationError -> 422, which violates
    # the documented invalid-draft -> 503 contract. Chorus is structurally
    # required, so an empty chorus is a degenerate draft -> LyricsGenerationError.
    verses = [
        Verse(number=v.number, lines=lines)
        for v in result.verses
        if (lines := _strip_lines(v.lines))
    ]

    chorus_lines = _strip_lines(result.chorus.lines)
    if not chorus_lines:
        raise LyricsGenerationError("Generated draft has an empty chorus")

    bridge_lines = _strip_lines(result.bridge.lines) if result.bridge is not None else []
    bridge = Bridge(lines=bridge_lines) if bridge_lines else None

    if not verses:
        raise LyricsGenerationError("Generated draft has no non-empty verses")

    total = sum(len(v.lines) for v in verses) + len(chorus_lines)
    if bridge is not None:
        total += len(bridge_lines)

    if total < 10:
        raise LyricsGenerationError(f"Generated draft is too short ({total} lines, minimum 10)")

    return LyricsResult(
        verses=verses,
        chorus=Chorus(lines=chorus_lines),
        bridge=bridge,
        language="es",
        title_suggestion=result.title_suggestion,
        provider=result.provider,
    )
