"""Clip chaining: split lyrics -> parallel generation -> stitch with crossfade.

Provides ClipSection, ENERGY_MAP, split_lyrics(), generate_clips_parallel(),
stitch_clips(), and generate_stitched() for producing full-length songs
from multiple 30s Lyria 3 clips.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from app.config import settings
from app.music.openclaw import OpenClawClient

logger = logging.getLogger(__name__)


# ── Data Structures ───────────────────────────────────────────────────────────────


class ClipSection(NamedTuple):
    """A single clip section for parallel generation."""

    section_name: str  # "Verse 1", "Chorus", etc.
    lyrics_text: str  # Full lyrics for this section
    order: int  # 0-based position


ENERGY_MAP: dict[str, str] = {
    "verse": "suave, estableciendo la historia",
    "chorus": "enérgico, poderoso, estallido emocional",
    "bridge": "clímax, intenso, momento culminante",
    "outro": "gentil, resolución, calmado descendiendo",
}

SECTION_NAMES: frozenset[str] = frozenset({"verse", "chorus", "bridge", "outro"})

# Regex matching [Verse N], [Chorus], [Bridge], [Outro] at line start
SECTION_RE: re.Pattern[str] = re.compile(
    r"^\[((?:Verse\s+\d+)|Chorus|Bridge|Outro)\]\s*\n?",
    re.MULTILINE | re.IGNORECASE,
)


# ── Errors ────────────────────────────────────────────────────────────────────────


class ClipChainError(Exception):
    """Base error for clip chaining failures."""


class AllProvidersUnavailableError(ClipChainError):
    """Raised when every clip generation attempt fails."""


class PydubUnavailableError(ClipChainError):
    """Raised when pydub is not installed for stitching."""


# ── Helpers ───────────────────────────────────────────────────────────────────────


def _get_energy_descriptor(section_name: str) -> str:
    """Return the energy descriptor for a section name.

    Normalises section name (lowercase, strip numbers), looks up in
    ENERGY_MAP. Returns 'neutro' for unknown sections.
    """
    key = section_name.lower().split()[0] if section_name.lower().split() else ""
    return ENERGY_MAP.get(key, "neutro")


def _get_audio_segment() -> Any:
    """Lazy import for pydub to allow graceful fallback."""
    try:
        from pydub import AudioSegment  # noqa: F811

        return AudioSegment
    except ImportError:
        return None


# ── Task 4: split_lyrics ──────────────────────────────────────────────────────────


def split_lyrics(text: str, max_clips: int | None = None) -> list[ClipSection]:
    """Split lyrics at section markers into N clips.

    Splits at [Verse N], [Chorus], [Bridge], [Outro] markers.
    Each section becomes a ClipSection with its lyrics and a position-based
    energy descriptor. Bounded by max_clips. Falls back to a single section
    containing the whole text if no markers are found.

    Args:
        text: Full lyrics with section markers.
        max_clips: Maximum number of clips (default from settings.MAX_CLIPS).

    Returns:
        List of ClipSection named tuples.
    """
    if max_clips is None:
        max_clips = settings.MAX_CLIPS

    matches = list(SECTION_RE.finditer(text))
    sections: list[ClipSection] = []

    for i, match in enumerate(matches):
        if len(sections) >= max_clips:
            break

        section_name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        lyrics = text[start:end].strip()

        if lyrics:
            sections.append(
                ClipSection(
                    section_name=section_name,
                    lyrics_text=lyrics,
                    order=i,
                )
            )

    # If no markers found, treat the whole text as a single [Verse 1] clip
    if not sections:
        sections.append(
            ClipSection(
                section_name="Verse 1",
                lyrics_text=text.strip(),
                order=0,
            )
        )

    return sections


# ── Task 5: generate_clips_parallel ──────────────────────────────────────────────


async def _generate_one_clip(
    client: OpenClawClient,
    section: ClipSection,
    voice_prompt: str,
    reference_description: str | None,
    model: str,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    retry_attempts: int,
) -> Path | None:
    """Generate a single clip for one section.

    Runs inside the semaphore to cap concurrency. Builds the per-clip prompt
    by appending the section's energy descriptor. Retries on failure with
    10s backoff.

    Returns:
        Path to the saved MP3, or None if all retries fail.
    """
    async with semaphore:
        energy = _get_energy_descriptor(section.section_name)
        prompt = voice_prompt
        if reference_description:
            prompt = f"{prompt}. Estilo: {reference_description}"
        prompt = f"{prompt}. Esta sección debe sonar: {energy}"

        clip_filename = (
            f"clip_{section.order:02d}_{section.section_name.lower().replace(' ', '_')}.mp3"
        )
        clip_path = output_dir / clip_filename

        for attempt in range(retry_attempts + 1):
            try:
                task_id = await client.invoke(
                    lyrics=section.lyrics_text,
                    prompt=prompt,
                    model=model,
                )
                download_url = await client.poll(task_id, timeout=300)
                mp3_bytes = await client.download(download_url)
                clip_path.write_bytes(mp3_bytes)
                logger.info(
                    "Clip %d (%s) generated: %d bytes (attempt %d/%d)",
                    section.order,
                    section.section_name,
                    len(mp3_bytes),
                    attempt + 1,
                    retry_attempts + 1,
                )
                return clip_path
            except Exception as exc:
                logger.warning(
                    "Clip %d (%s) attempt %d/%d failed: %s",
                    section.order,
                    section.section_name,
                    attempt + 1,
                    retry_attempts + 1,
                    exc,
                )
                if attempt < retry_attempts - 1:
                    await asyncio.sleep(10)

        logger.error(
            "Clip %d (%s) failed after %d attempts",
            section.order,
            section.section_name,
            retry_attempts + 1,
        )
        return None


async def generate_clips_parallel(
    sections: list[ClipSection],
    voice_prompt: str,
    model: str = "google/lyria-3-clip-preview",
    reference_description: str | None = None,
    max_concurrency: int | None = None,
    retry_attempts: int | None = None,
    job_id: str | None = None,
) -> list[Path | None]:
    """Generate clips for all sections in parallel.

    Uses asyncio.Semaphore to limit concurrency (default MAX_PARALLEL=3).
    Each clip is invoked, polled, and downloaded independently — they do NOT
    wait for each other. Failed clips return None in the result list.

    Args:
        sections: List of clip sections to generate.
        voice_prompt: Base voice/style prompt for Lyria 3.
        model: OpenClaw model name (default: lyria-3-clip-preview).
        reference_description: Optional style description from reference audio.
        max_concurrency: Max parallel invocations (default settings.MAX_PARALLEL).
        retry_attempts: Retry count per clip (default settings.CLIP_RETRY_ATTEMPTS).
        job_id: Optional job ID for the output subdirectory.

    Returns:
        List of Path (for successful clips) or None (for failed clips), in
        the same order as the input sections.
    """
    if max_concurrency is None:
        max_concurrency = settings.MAX_PARALLEL
    if retry_attempts is None:
        retry_attempts = settings.CLIP_RETRY_ATTEMPTS

    if job_id is None:
        job_id = str(uuid.uuid4())
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenClawClient(
        base_url=settings.OPENCLAW_BASE_URL,
        token=settings.OPENCLAW_TOKEN,
    )

    semaphore = asyncio.Semaphore(max_concurrency)

    tasks = [
        _generate_one_clip(
            client=client,
            section=section,
            voice_prompt=voice_prompt,
            reference_description=reference_description,
            model=model,
            output_dir=output_dir,
            semaphore=semaphore,
            retry_attempts=retry_attempts,
        )
        for section in sections
    ]

    results: list[Path | None] = await asyncio.gather(*tasks)
    return results


# ── Task 6: stitch_clips ──────────────────────────────────────────────────────────


def stitch_clips(
    clip_paths: list[Path | None],
    crossfade_ms: int | None = None,
    target_seconds: float = 150.0,
    output_path: Path | None = None,
) -> Path:
    """Stitch clip MP3s into a single track with crossfade.

    Loads successful clips via pydub, appends them sequentially with
    crossfade, applies a 3s final fade-out, and exports as 192k MP3.
    If the stitched result is too short (<120s), falls back to
    extend_duration(). If it exceeds 180s, trims to target_seconds.

    Args:
        clip_paths: Ordered list of Paths (successful) and Nones (failed).
        crossfade_ms: Crossfade duration in ms (default CLIP_CROSSFADE_MS).
        target_seconds: Target output duration in seconds.
        output_path: Explicit output path (auto-derived if None).

    Returns:
        Path to the final stitched MP3.

    Raises:
        AllProvidersUnavailableError: If no clips succeeded or none loaded.
        PydubUnavailableError: If pydub is not available.
    """
    if crossfade_ms is None:
        crossfade_ms = settings.CLIP_CROSSFADE_MS

    audio_segment = _get_audio_segment()
    if audio_segment is None:
        raise PydubUnavailableError("pydub is required for clip stitching")

    valid_clips = [p for p in clip_paths if p is not None]
    if not valid_clips:
        raise AllProvidersUnavailableError("All clip generation attempts failed")

    # Load all successful clips
    segments: list[Any] = []
    for path in valid_clips:
        try:
            seg = audio_segment.from_mp3(str(path))
            segments.append(seg)
        except Exception as exc:
            logger.warning("Failed to load clip %s: %s", path, exc)

    if not segments:
        raise AllProvidersUnavailableError("No clips could be loaded for stitching")

    # Stitch with crossfade
    result = segments[0]
    for seg in segments[1:]:
        result = result.append(seg, crossfade=crossfade_ms)

    # Apply 3s final fade-out
    fade_ms = min(3000, len(result))
    result = result.fade_out(fade_ms)

    total_seconds = len(result) / 1000.0

    # If too short, fallback to extend_duration
    if total_seconds < 120.0:
        logger.info(
            "Stitched duration %.1fs < 120s — applying extend_duration fallback",
            total_seconds,
        )
        if output_path is None:
            parent = valid_clips[0].parent
            output_path = parent / "stitched.mp3"
        result.export(str(output_path), format="mp3", bitrate="192k")
        from app.music.durext import extend_duration

        ext_result = extend_duration(output_path, target_seconds=int(target_seconds))
        return ext_result.path

    # Trim if exceeding 180s cap
    max_allowed_ms = 180_000  # 180s hard cap
    if len(result) > max_allowed_ms:
        logger.info(
            "Stitched duration %.1fs > 180s — trimming to %ds",
            total_seconds,
            target_seconds,
        )
        result = result[: int(target_seconds * 1000)]

    # Export as 192k MP3
    if output_path is None:
        parent = valid_clips[0].parent
        output_path = parent / "final.mp3"
    result.export(str(output_path), format="mp3", bitrate="192k")
    logger.info(
        "Stitched clip exported: %s (%.1fs, crossfade=%dms)",
        output_path,
        len(result) / 1000,
        crossfade_ms,
    )
    return output_path


# ── Task 7: generate_stitched ─────────────────────────────────────────────────────


async def generate_stitched(
    lyrics: str,
    voice_prompt: str,
    model: str = "google/lyria-3-clip-preview",
    reference_description: str | None = None,
    job_id: str | None = None,
) -> Path:
    """Generate a full song via clip chaining: split -> parallel gen -> stitch.

    Orchestrates the full pipeline:
      1. split_lyrics() — split lyrics at section markers
      2. generate_clips_parallel() — invoke OpenClaw for each section
      3. stitch_clips() — crossfade all clips into one MP3

    Args:
        lyrics: Full lyrics with [Verse N]/[Chorus]/[Bridge]/[Outro] markers.
        voice_prompt: Base voice/style prompt for Lyria 3.
        model: OpenClaw model name.
        reference_description: Optional style description from reference audio.
        job_id: Optional job ID for output subdirectory.

    Returns:
        Path to the final stitched MP3 file.

    Raises:
        AllProvidersUnavailableError: If every clip generation fails.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Split lyrics into sections
    sections = split_lyrics(lyrics)
    logger.info("Split lyrics into %d sections for job %s", len(sections), job_id)

    # 2. Generate clips in parallel
    clip_paths = await generate_clips_parallel(
        sections=sections,
        voice_prompt=voice_prompt,
        model=model,
        reference_description=reference_description,
        job_id=job_id,
    )

    successful = sum(1 for p in clip_paths if p is not None)
    logger.info(
        "Clip generation complete: %d/%d successful for job %s",
        successful,
        len(clip_paths),
        job_id,
    )

    # 3. Stitch clips into final MP3
    final_path = output_dir / "final.mp3"
    result_path = stitch_clips(
        clip_paths=clip_paths,
        output_path=final_path,
    )

    return result_path
