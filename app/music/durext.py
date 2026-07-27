"""Duration extension for generated audio via pydub.

Provides smart crossfade looping, simple looping, and a top-level
extend_duration() function that gracefully handles missing ffmpeg.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class ExtendResult(NamedTuple):
    """Result of a duration extension operation."""

    path: Path
    extended: bool


def _get_audio_segment() -> Any:
    """Lazy import for pydub to allow graceful fallback.

    Returns the AudioSegment class, or None if pydub/ffmpeg unavailable.
    """
    try:
        from pydub import AudioSegment

        return AudioSegment
    except ImportError:
        return None


def smart_crossfade_loop(audio: Any, target_ms: int) -> Any:
    """Extend audio by crossfade-looping for natural-sounding extension.

    Takes the last 10% as crossfade intro and first 10% as crossfade outro,
    loops the full segment N times with 2s crossfade between each join.

    Args:
        audio: pydub AudioSegment to extend.
        target_ms: Target duration in milliseconds.

    Returns:
        Extended AudioSegment at or above target_ms.
    """
    audio_ms = len(audio)
    if audio_ms >= target_ms:
        return audio

    crossfade_ms = min(2000, audio_ms // 4)  # 2s crossfade, capped at 25% of audio
    crossfade_ms = max(crossfade_ms, 100)  # at least 100ms

    # How many loops needed
    loops_needed = max(1, target_ms // (audio_ms - crossfade_ms))
    segments: list[Any] = []

    for _ in range(loops_needed):
        segments.append(audio)

    # Crossfade append all segments with 2s crossfade
    result = segments[0]
    for seg in segments[1:]:
        result = result.append(seg, crossfade=crossfade_ms)

    # Fade out last 2s
    result = result.fade_out(min(2000, len(result)))

    # If still too short, append another loop
    while len(result) < target_ms:
        result = result.append(audio, crossfade=crossfade_ms)

    return result[:target_ms]


def simple_loop(audio: Any, target_ms: int) -> Any:
    """Simple fallback extension by naive repeat with fade-out.

    Args:
        audio: pydub AudioSegment to extend.
        target_ms: Target duration in milliseconds.

    Returns:
        Extended AudioSegment at or above target_ms.
    """
    audio_ms = len(audio)
    if audio_ms >= target_ms:
        return audio

    loops_needed = target_ms // audio_ms + 1
    result = audio
    for _ in range(loops_needed - 1):
        result = result + audio  # simple concatenation

    # Apply fade-out to last 3s
    fade_ms = min(3000, len(result))
    result = result[:target_ms].fade_out(fade_ms)
    return result


def extend_duration(
    path: Path,
    target_seconds: int = 150,
) -> ExtendResult:
    """Extend an MP3 file to the target duration.

    Uses smart_crossfade_loop as primary strategy, falls back to
    simple_loop if crossfade fails, and gracefully handles missing
    ffmpeg/pydub by returning the original file unmodified.

    Args:
        path: Path to the MP3 file.
        target_seconds: Target duration in seconds (default 150 = 2:30).

    Returns:
        ExtendResult with the output path and whether extension was applied.
    """
    audio_segment_cls = _get_audio_segment()
    if audio_segment_cls is None:
        logger.warning("pydub not available — skipping duration extension")
        return ExtendResult(path=path, extended=False)

    try:
        audio = audio_segment_cls.from_mp3(str(path))
    except Exception as exc:
        logger.warning("Failed to load MP3 for extension: %s", exc)
        return ExtendResult(path=path, extended=False)

    target_ms = target_seconds * 1000
    audio_ms = len(audio)

    if audio_ms >= target_ms:
        logger.info(
            "Audio already %dms >= target %dms — no extension needed",
            audio_ms, target_ms,
        )
        return ExtendResult(path=path, extended=False)

    try:
        extended = smart_crossfade_loop(audio, target_ms)
        out = path.parent / "final.mp3"
        extended.export(str(out), format="mp3", bitrate="192k")
        logger.info(
            "Duration extended: %dms → %dms (target: %dms)",
            audio_ms, len(extended), target_ms,
        )
        return ExtendResult(path=out, extended=True)
    except Exception as exc:
        logger.warning("Smart crossfade loop failed: %s", exc)
        try:
            extended = simple_loop(audio, target_ms)
            out = path.parent / "final.mp3"
            extended.export(str(out), format="mp3", bitrate="192k")
            return ExtendResult(path=out, extended=True)
        except Exception as exc2:
            logger.warning("Simple loop also failed: %s", exc2)
            return ExtendResult(path=path, extended=False)
