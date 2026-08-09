"""Job worker orchestrator for the lyrics→music→processing pipeline.

Runs as an asyncio background task. Updates job status through the
state machine at each stage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.jobs import get_job, update_status
from app.lyrics import generate as lyrics_generate
from app.models import GenerateRequest
from app.music import extend_duration
from app.music import generate as music_generate
from app.voice import build_prompt

logger = logging.getLogger(__name__)


async def job_worker(job_id: str) -> None:
    """Execute the full job pipeline: lyrics → music → processing → complete.

    Runs as a background asyncio task. Each stage updates the job status,
    and any error sets status to 'failed'.

    Args:
        job_id: The UUID job ID to process.
    """
    try:
        # 1. Get job parameters
        job = await get_job(job_id, db_path=settings.DB_PATH)
        if job is None:
            logger.error("Worker: job %s not found", job_id)
            return

        params_dict = json.loads(job["params"])
        params = GenerateRequest(**params_dict)

        ref_song = getattr(params, "reference_song", None)
        ref_desc = getattr(params, "reference_description", None)

        # 2. Lyrics generation
        await update_status(
            job_id, "lyrics_generating", progress=0.2, db_path=settings.DB_PATH,
        )
        logger.info("Worker: generating lyrics for job %s", job_id)

        lyrics_result = await lyrics_generate(
            recipient=params.recipient,
            relationship=params.relationship,
            occasion=params.occasion,
            genre=params.genre,
            mood=params.mood,
            story=params.story,
            reference_song=ref_desc or ref_song,
            reference_description=ref_desc,
        )

        # Format lyrics text with markers for music generation
        lyrics_text = _format_lyrics_for_music(lyrics_result)

        # 3. Music generation
        await update_status(
            job_id, "music_generating", progress=0.5, db_path=settings.DB_PATH,
        )
        logger.info("Worker: generating music for job %s", job_id)

        voice_prompt = build_prompt(
            voice_id=params.voice,
            genre=params.genre,
            mood=params.mood,
            reference_description=ref_desc,
            reference_song=ref_song,
        )

        generated_path = await music_generate(
            lyrics=lyrics_text,
            voice_prompt=voice_prompt,
        )

        # 4. Processing (duration extension)
        await update_status(
            job_id, "processing", progress=0.8, db_path=settings.DB_PATH,
        )
        logger.info("Worker: extending duration for job %s", job_id)

        ext_result = extend_duration(generated_path, target_seconds=150)
        final_path = ext_result.path
        extended = ext_result.extended

        # 5. Complete
        metadata: dict[str, Any] = {
            "recipient": params.recipient,
            "genre": params.genre,
            "mood": params.mood,
            "voice": params.voice,
            "duration_extended": extended,
            "lyrics_provider": lyrics_result.provider,
            "title_suggestion": lyrics_result.title_suggestion,
            "reference_song": ref_song,
            "reference_description": ref_desc,
        }

        await update_status(
            job_id,
            "complete",
            progress=1.0,
            metadata=json.dumps(metadata),
            db_path=settings.DB_PATH,
        )
        logger.info(
            "Worker: job %s complete — final file at %s (extended=%s)",
            job_id, final_path, extended,
        )

    except Exception as exc:
        logger.exception("Worker: job %s failed: %s", job_id, exc)
        try:
            await update_status(
                job_id, "failed", error=str(exc), db_path=settings.DB_PATH,
            )
        except Exception:
            logger.exception("Worker: failed to update job %s status to failed", job_id)


def _format_lyrics_for_music(lyrics_result: Any) -> str:
    """Format a LyricsResult into a text string with markers for music gen.

    Args:
        lyrics_result: LyricsResult object with verses, chorus, bridge.

    Returns:
        Formatted lyrics string with [Verse], [Chorus], [Bridge] markers.
    """
    parts: list[str] = []

    for verse in lyrics_result.verses:
        parts.append(f"[Verse {verse.number}]")
        parts.extend(verse.lines)

    parts.append("[Chorus]")
    parts.extend(lyrics_result.chorus.lines)

    if lyrics_result.bridge:
        parts.append("[Bridge]")
        parts.extend(lyrics_result.bridge.lines)

    return "\n".join(parts)
