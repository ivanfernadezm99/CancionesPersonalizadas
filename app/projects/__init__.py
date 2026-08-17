"""Song project management — iterative song creation with accumulating stories.

Provides orchestration for creating projects, generating previews and final
songs, and a project worker that runs the lyrics→music→processing pipeline
with project-specific overrides (model, reference_song, duration).
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import settings
from app.jobs import create_job as create_job_record
from app.jobs import get_job, update_status
from app.jobs.worker import _format_lyrics_for_music
from app.lyrics import generate as lyrics_generate
from app.models import GenerateRequest, JobCreateResponse, SongProjectCreate
from app.music import extend_duration
from app.music import generate as music_generate
from app.music.clipchain import generate_stitched
from app.projects import ref_audio, store
from app.tag_sanitizer import sanitize_reference_song
from app.voice import build_prompt

logger = logging.getLogger(__name__)

PREVIEW_MODEL = "google/lyria-3-clip-preview"
FINAL_MODEL = "google/lyria-3-pro-preview"

# Legacy voice values stored before the 7-voice registry (RQ-VOI-01).
# These are normalized at read time so rebuilding a GenerateRequest from an
# old project row never raises ValidationError->500 (T7/T8).
_LEGACY_VOICE_MAP: dict[str, str] = {
    "duo": "female",
    "children": "es-espana-child",
}


def _normalize_voice(voice: str | None) -> str:
    """Map a stored (possibly legacy) voice to a valid registry voice."""
    if voice is None:
        return "female"
    return _LEGACY_VOICE_MAP.get(voice, voice)


async def create_project(data: SongProjectCreate, *, user_id: str = "") -> str:
    """Create a new song project and return its ID.

    Args:
        data: Project creation parameters.
        user_id: Owning user ID (from the JWT nameidentifier claim).

    Returns:
        The new project's UUID string.
    """
    return await store.create_project(data, user_id=user_id, db_path=settings.DB_PATH)


async def create_preview_job(project_id: str) -> JobCreateResponse:
    """Create a preview job for a project.

    Validates that the project has at least one story fragment, creates a job
    record with preview metadata, links it to the project, and launches a
    background project_worker.

    Args:
        project_id: The project UUID.

    Returns:
        JobCreateResponse with job tracking endpoints.

    Raises:
        ValueError: If project not found or has no story fragments.
    """
    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    if not project.get("fragments"):
        raise ValueError("no_story_fragments")

    story = await store.get_accumulated_story(project_id, db_path=settings.DB_PATH)

    gen_request = GenerateRequest(
        recipient=project["recipient"],
        relationship=project["relationship"],
        occasion="personalizada",
        genre=project["genre"],
        mood=project["mood"],
        story=story[:2000] if story else None,
        voice=_normalize_voice(project["voice"]),
        idea=project.get("idea"),
    )

    metadata = {
        "project_id": project_id,
        "model": PREVIEW_MODEL,
        "duration_target": settings.PREVIEW_TARGET_SECONDS,
        "reference_song": project.get("reference_song"),
        "reference_description": project.get("reference_description"),
        "idea": project.get("idea"),
        "job_type": "preview",
    }

    job_id = await create_job_record(
        gen_request,
        db_path=settings.DB_PATH,
        initial_metadata=json.dumps(metadata),
    )

    await store.link_project_job(
        project_id, job_id, "preview", db_path=settings.DB_PATH,
    )

    asyncio.create_task(project_worker(job_id))

    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        estimated_total_seconds=120,
        endpoints={
            "status": f"/api/status/{job_id}",
            "stream": f"/api/stream/{job_id}",
        },
    )


async def create_final_job(project_id: str) -> JobCreateResponse:
    """Create a final song job for a project.

    Same flow as create_preview_job but uses the final model
    (lyria-3-pro-preview) and targets FINAL_TARGET_SECONDS duration.

    Args:
        project_id: The project UUID.

    Returns:
        JobCreateResponse with job tracking endpoints.

    Raises:
        ValueError: If project not found or has no story fragments.
    """
    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    if not project.get("fragments"):
        raise ValueError("no_story_fragments")

    story = await store.get_accumulated_story(project_id, db_path=settings.DB_PATH)

    gen_request = GenerateRequest(
        recipient=project["recipient"],
        relationship=project["relationship"],
        occasion="personalizada",
        genre=project["genre"],
        mood=project["mood"],
        story=story[:2000] if story else None,
        voice=_normalize_voice(project["voice"]),
        idea=project.get("idea"),
    )

    chaining_enabled = bool(project.get("chaining_enabled", False))

    metadata = {
        "project_id": project_id,
        "model": FINAL_MODEL,
        "duration_target": settings.FINAL_TARGET_SECONDS,
        "reference_song": project.get("reference_song"),
        "reference_description": project.get("reference_description"),
        "idea": project.get("idea"),
        "job_type": "final",
        "chaining_enabled": chaining_enabled,
        "num_clips": settings.MAX_CLIPS if chaining_enabled else None,
    }

    job_id = await create_job_record(
        gen_request,
        db_path=settings.DB_PATH,
        initial_metadata=json.dumps(metadata),
    )

    await store.link_project_job(
        project_id, job_id, "final", db_path=settings.DB_PATH,
    )

    asyncio.create_task(project_worker(job_id))

    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        estimated_total_seconds=180,
        endpoints={
            "status": f"/api/status/{job_id}",
            "stream": f"/api/stream/{job_id}",
        },
    )


async def project_worker(job_id: str) -> None:
    """Execute the project pipeline: lyrics → music → processing.

    Runs as a background asyncio task. Reads job metadata to determine
    model, duration target, and reference_song overrides. Skips
    extend_duration for preview jobs.

    Args:
        job_id: The UUID job ID to process.
    """
    try:
        job = await get_job(job_id, db_path=settings.DB_PATH)
        if job is None:
            logger.error("Project worker: job %s not found", job_id)
            return

        metadata = json.loads(job.get("metadata") or "{}")
        model = metadata.get("model", PREVIEW_MODEL)
        duration_target = metadata.get("duration_target")
        reference_song = metadata.get("reference_song")
        reference_description = metadata.get("reference_description")
        job_type = metadata.get("job_type", "preview")
        # RQ-RS-06: sanitize the stored song token before it reaches
        # lyrics/prompt (covers legacy projects stored before input
        # validation). Completion metadata persists the ORIGINAL value.
        sanitized_song = sanitize_reference_song(reference_song)

        params_dict = json.loads(job["params"])
        params = GenerateRequest(**params_dict)

        # 1. Lyrics generation
        await update_status(
            job_id, "lyrics_generating", progress=0.2, db_path=settings.DB_PATH,
        )
        logger.info("Project worker: generating lyrics for job %s", job_id)

        lyrics_result = await lyrics_generate(
            recipient=params.recipient,
            relationship=params.relationship,
            occasion=params.occasion,
            genre=params.genre,
            mood=params.mood,
            story=params.story,
            idea=getattr(params, "idea", None),
            reference_song=sanitized_song,
            reference_description=reference_description,
        )

        lyrics_text = _format_lyrics_for_music(lyrics_result)

        voice_prompt = build_prompt(
            voice_id=params.voice,
            genre=params.genre,
            mood=params.mood,
            reference_song=sanitized_song,
            reference_description=reference_description,
        )

        # Suno chaining guard: if MUSIC_PROVIDER=suno, chaining is irrelevant
        music_provider = getattr(settings, "MUSIC_PROVIDER", None)
        is_suno = isinstance(music_provider, str) and music_provider == "suno"
        chaining_enabled = metadata.get("chaining_enabled", False)

        if is_suno and chaining_enabled:
            logger.warning(
                "Chaining disabled for Suno provider (project_worker job_id=%s)",
                job_id,
            )
            chaining_enabled = False

        # Build reference audio URL for Suno Cover mode
        reference_audio_url: str | None = None
        if is_suno and ref_audio.has_reference_audio(metadata.get("project_id", "")):
            reference_audio_url = ref_audio.get_reference_audio_url(metadata.get("project_id", ""))

        if chaining_enabled:
            # 2a. Clip-chaining path: split lyrics, generate clips in parallel, stitch
            await update_status(
                job_id, "music_generating", progress=0.5, db_path=settings.DB_PATH,
            )
            logger.info(
                "Project worker: generating stitched clips for job %s (chaining_enabled)",
                job_id,
            )

            final_path = await generate_stitched(
                lyrics=lyrics_text,
                voice_prompt=voice_prompt,
                model="google/lyria-3-clip-preview",
                reference_description=reference_description,
                job_id=job_id,
            )

            # 3a. Processing step (required by state machine before complete)
            await update_status(
                job_id, "processing", progress=0.8, db_path=settings.DB_PATH,
            )

            stitching_used = True
            extended = False
        else:
            # 2b. Standard music generation
            await update_status(
                job_id, "music_generating", progress=0.5, db_path=settings.DB_PATH,
            )
            logger.info("Project worker: generating music for job %s", job_id)

            generated_path = await music_generate(
                lyrics=lyrics_text,
                voice_prompt=voice_prompt,
                model=model,
                job_id=job_id,
                reference_audio=reference_audio_url,
            )

            # 3. Processing — the status transition is required by the state
            # machine before complete; duration extension only for final songs.
            await update_status(
                job_id, "processing", progress=0.8, db_path=settings.DB_PATH,
            )
            if job_type != "preview" and duration_target:
                logger.info(
                    "Project worker: extending duration for job %s (target=%ss)",
                    job_id, duration_target,
                )
                ext_result = extend_duration(generated_path, target_seconds=duration_target)
                final_path = ext_result.path
                extended = ext_result.extended
            else:
                final_path = generated_path
                extended = False
            stitching_used = False

        # 4. Complete
        completion_meta = {
            **metadata,
            "duration_extended": extended,
            "stitching_used": stitching_used,
            "lyrics_provider": lyrics_result.provider,
            "title_suggestion": lyrics_result.title_suggestion,
        }
        await update_status(
            job_id,
            "complete",
            progress=1.0,
            metadata=json.dumps(completion_meta),
            db_path=settings.DB_PATH,
        )
        logger.info(
            "Project worker: job %s complete — final file at %s (extended=%s)",
            job_id, final_path, extended,
        )

    except Exception as exc:
        logger.exception("Project worker: job %s failed: %s", job_id, exc)
        try:
            await update_status(
                job_id, "failed", error=str(exc), db_path=settings.DB_PATH,
            )
        except Exception:
            logger.exception(
                "Project worker: failed to update job %s status to failed", job_id,
            )
