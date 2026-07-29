"""Reference audio file management for Suno Cover mode.

Stores, serves, and cleans up reference audio files uploaded for Suno
Cover mode music generation.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

REF_AUDIO_SUBDIR = "ref-audio"


def store_reference_audio(project_id: str, source_path: Path) -> Path:
    """Store a reference audio file for a project.

    Copies the file to {OUTPUT_DIR}/ref-audio/{project_id}/reference.mp3.

    Args:
        project_id: The project UUID.
        source_path: Path to the source MP3 file.

    Returns:
        Path to the stored reference audio file.
    """
    ref_dir = Path(settings.OUTPUT_DIR) / REF_AUDIO_SUBDIR / project_id
    ref_dir.mkdir(parents=True, exist_ok=True)
    dest_path = ref_dir / "reference.mp3"

    shutil.copy2(source_path, dest_path)
    logger.info("Reference audio stored at %s", dest_path)
    return dest_path


def get_reference_audio_path(project_id: str) -> Path | None:
    """Get the path to a stored reference audio file.

    Args:
        project_id: The project UUID.

    Returns:
        Path to the reference audio MP3, or None if not found.
    """
    ref_path = Path(settings.OUTPUT_DIR) / REF_AUDIO_SUBDIR / project_id / "reference.mp3"
    if ref_path.exists():
        return ref_path
    return None


def get_reference_audio_url(project_id: str) -> str | None:
    """Build the public URL for a stored reference audio file.

    Uses PUBLIC_BASE_URL setting if available, otherwise returns None
    (the caller should infer from the Host header).

    Args:
        project_id: The project UUID.

    Returns:
        Public URL string, or None if PUBLIC_BASE_URL is not configured.
    """
    if not settings.PUBLIC_BASE_URL:
        return None
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/api/ref-audio/{project_id}"


def cleanup_reference_audio(project_id: str) -> None:
    """Remove stored reference audio for a project.

    Args:
        project_id: The project UUID.
    """
    ref_dir = Path(settings.OUTPUT_DIR) / REF_AUDIO_SUBDIR / project_id
    if ref_dir.exists():
        shutil.rmtree(ref_dir)
        logger.info("Reference audio cleaned up for project %s", project_id)


def has_reference_audio(project_id: str) -> bool:
    """Check if reference audio exists for a project.

    Args:
        project_id: The project UUID.

    Returns:
        True if the reference audio file exists.
    """
    ref_path = Path(settings.OUTPUT_DIR) / REF_AUDIO_SUBDIR / project_id / "reference.mp3"
    return ref_path.exists()
