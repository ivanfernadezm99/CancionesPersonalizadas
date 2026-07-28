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
from app.projects import store
from app.voice import build_prompt

logger = logging.getLogger(__name__)

PREVIEW_MODEL = "google/lyria-3-clip-preview"
FINAL_MODEL = "google/lyria-3-pro-preview"


async def create_project(data: SongProjectCreate) -> str:
    """Create a new song project and return its ID.

    Args:
        data: Project creation parameters.

    Returns:
        The new project's UUID string.
    """
    return await store.create_project(data, db_path=settings.DB_PATH)


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
        voice=project["voice"],
    )

    metadata = {
        "project_id": project_id,
        "model": PREVIEW_MODEL,
        "duration_target": settings.PREVIEW_TARGET_SECONDS,
        "reference_song": project.get("reference_song"),
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
        voice=project["voice"],
    )

    metadata = {
        "project_id": project_id,
        "model": FINAL_MODEL,
        "duration_target": settings.FINAL_TARGET_SECONDS,
        "reference_song": project.get("reference_song"),
        "job_type": "final",
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
        job_type = metadata.get("job_type", "preview")

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
            reference_song=reference_song,
        )

        lyrics_text = _format_lyrics_for_music(lyrics_result)

        # 2. Music generation
        await update_status(
            job_id, "music_generating", progress=0.5, db_path=settings.DB_PATH,
        )
        logger.info("Project worker: generating music for job %s", job_id)

        voice_prompt = build_prompt(
            voice_id=params.voice,
            genre=params.genre,
            mood=params.mood,
            reference_song=reference_song,
        )

        generated_path = await music_generate(
            lyrics=lyrics_text,
            voice_prompt=voice_prompt,
            model=model,
            job_id=job_id,
        )

        # 3. Processing (duration extension — skip for previews)
        if job_type != "preview" and duration_target:
            await update_status(
                job_id, "processing", progress=0.8, db_path=settings.DB_PATH,
            )
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

        # 4. Complete
        completion_meta = {
            **metadata,
            "duration_extended": extended,
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
