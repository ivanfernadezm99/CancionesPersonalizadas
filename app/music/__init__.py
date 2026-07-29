"""Music generation public API.

Provides generate() to invoke music generation through the configured
provider (OpenClaw or Suno), extend_duration() to post-process audio to
target length, and generate_stitched() for clip-chaining full songs.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.config import settings
from app.music.clipchain import generate_stitched
from app.music.durext import ExtendResult, extend_duration
from app.music.openclaw import OpenClawClient, OpenClawError
from app.music.providers import (
    BaseMusicProvider,
    MusicGenerationError,
    OpenClawProvider,
    SunoError,
    SunoProvider,
)

__all__ = [
    "BaseMusicProvider",
    "ExtendResult",
    "MusicGenerationError",
    "OpenClawClient",
    "OpenClawError",
    "OpenClawProvider",
    "SunoError",
    "SunoProvider",
    "extend_duration",
    "generate",
    "generate_stitched",
]

logger = logging.getLogger(__name__)


def _select_music_provider() -> BaseMusicProvider:
    """Select the music generation provider based on config.

    Returns:
        An OpenClawProvider if MUSIC_PROVIDER=openclaw (default),
        a SunoProvider if MUSIC_PROVIDER=suno.

    Raises:
        MusicGenerationError: If Suno is selected but not configured.
    """
    if settings.MUSIC_PROVIDER == "suno":
        if not settings.SUNO_API_KEY:
            raise MusicGenerationError(
                "SUNO_API_KEY required when MUSIC_PROVIDER=suno",
            )
        if not settings.SUNO_BASE_URL:
            raise MusicGenerationError(
                "SUNO_BASE_URL required when MUSIC_PROVIDER=suno",
            )
        return SunoProvider(
            api_key=settings.SUNO_API_KEY,
            base_url=settings.SUNO_BASE_URL,
        )

    return OpenClawProvider(
        token=settings.OPENCLAW_TOKEN,
        base_url=settings.OPENCLAW_BASE_URL,
    )


async def generate(
    lyrics: str,
    voice_prompt: str,
    model: str = "google/lyria-3-clip-preview",
    job_id: str | None = None,
    reference_audio: str | None = None,
) -> Path:
    """Generate music from lyrics and voice prompt via configured provider.

    Delegates to the provider selected by MUSIC_PROVIDER setting.
    When MUSIC_PROVIDER=openclaw (default), behaves identically to
    pre-abstraction code path.

    Args:
        lyrics: Full lyrics text.
        voice_prompt: Style/genre voice prompt.
        model: Model name (used by OpenClaw; Suno uses SUNO_DEFAULT_MODEL).
        job_id: Optional job ID for output subdirectory. Uses random UUID if None.
        reference_audio: Optional URL to reference audio (Suno Cover mode).
            Ignored by OpenClaw.

    Returns:
        Path to the saved MP3 file.

    Raises:
        MusicGenerationError: If music generation fails at any stage.
        OpenClawError: If using OpenClaw and it fails.
        SunoError: If using Suno and it fails.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())

    # For Suno provider, use the provider delegation path.
    # Use isinstance guard for backward compatibility: existing tests mock
    # app.music.settings as MagicMock, which makes .MUSIC_PROVIDER a Mock.
    provider_name = getattr(settings, "MUSIC_PROVIDER", None)
    if isinstance(provider_name, str) and provider_name == "suno":

        provider = _select_music_provider()
        logger.info(
            "Music generation: using provider=%s (job_id=%s)", provider.name, job_id,
        )
        return await provider.generate(
            lyrics=lyrics,
            voice_prompt=voice_prompt,
            model=model,
            reference_audio=reference_audio,
            job_id=job_id,
        )

    # Pre-abstraction code path for MUSIC_PROVIDER=openclaw (default).
    # Kept to preserve backward compatibility exactly — existing tests
    # patch app.music.OpenClawClient and app.music.settings.
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "generated.mp3"

    client = OpenClawClient(
        base_url=settings.OPENCLAW_BASE_URL,
        token=settings.OPENCLAW_TOKEN,
    )

    logger.info("Music generation: invoking OpenClaw (job_id=%s)", job_id)
    task_id = await client.invoke(lyrics=lyrics, prompt=voice_prompt, model=model)

    logger.info("Music generation: polling task %s", task_id)
    download_url = await client.poll(task_id, timeout=300)

    logger.info("Music generation: downloading MP3 from %s", download_url)
    mp3_bytes = await client.download(download_url)

    output_path.write_bytes(mp3_bytes)
    logger.info(
        "Music generation complete: %d bytes saved to %s",
        len(mp3_bytes), output_path,
    )

    return output_path
