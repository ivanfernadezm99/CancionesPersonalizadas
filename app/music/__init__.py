"""Music generation public API.

Provides generate() to invoke OpenClaw music generation and
extend_duration() to post-process audio to target length.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.config import settings
from app.music.durext import ExtendResult, extend_duration
from app.music.openclaw import OpenClawClient, OpenClawError

__all__ = [
    "ExtendResult",
    "OpenClawClient",
    "OpenClawError",
    "extend_duration",
    "generate",
]

logger = logging.getLogger(__name__)


async def generate(
    lyrics: str,
    voice_prompt: str,
    model: str = "google/lyria-3-clip-preview",
    job_id: str | None = None,
) -> Path:
    """Generate music from lyrics and voice prompt via OpenClaw.

    Invokes OpenClaw, polls for completion, downloads the MP3,
    and saves it to {OUTPUT_DIR}/{job_id}/generated.mp3.

    Args:
        lyrics: Full lyrics text.
        voice_prompt: Style/genre voice prompt for Lyria 3.
        model: OpenClaw model name (default: google/lyria-3-clip-preview).
        job_id: Optional job ID for output subdirectory. Uses random UUID if None.

    Returns:
        Path to the saved MP3 file.

    Raises:
        OpenClawError: If music generation fails at any stage.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())
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
