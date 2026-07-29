"""FastAPI router for song project management.

Provides endpoints for creating, reading, updating projects,
uploading audio references, and generating preview/final songs.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.audio_analysis import analyze_audio
from app.models import (
    AudioReferenceResponse,
    JobCreateResponse,
    SongProjectCreate,
    SongProjectResponse,
    SongProjectUpdate,
    StoryFragmentResponse,
    ProjectPreview,
)
from app.projects import create_final_job, create_preview_job
from app.projects import create_project as orch_create_project
from app.projects import ref_audio, store

router = APIRouter(prefix="/api/projects")


def _project_to_response(project: dict) -> SongProjectResponse:
    """Convert a raw project dict from store to a SongProjectResponse."""
    fragments = [
        StoryFragmentResponse(
            id=f["id"],
            text=f["fragment"],
            sort_order=f["sort_order"],
            created_at=f["created_at"],
        )
        for f in project.get("fragments", [])
    ]
    previews = [
        ProjectPreview(
            job_id=p["job_id"],
            job_type=p["job_type"],
            status=p.get("status", "unknown"),
            created_at=p["created_at"],
        )
        for p in project.get("previews", [])
    ]
    return SongProjectResponse(
        id=project["id"],
        recipient=project["recipient"],
        relationship=project["relationship"],
        genre=project["genre"],
        mood=project["mood"],
        voice=project["voice"],
        reference_song=project.get("reference_song"),
        reference_description=project.get("reference_description"),
        status=project["status"],
        fragments=fragments,
        previews=previews,
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(data: SongProjectCreate) -> dict:
    """Create a new song project.

    Returns the project ID and status.
    """
    project_id = await orch_create_project(data)
    return {
        "id": project_id,
        "status": "draft",
        "endpoints": {"project": f"/api/projects/{project_id}"},
    }


@router.get("/{project_id}")
async def get_project(project_id: str) -> SongProjectResponse:
    """Get a project by ID with all fragments and previews."""
    from app.config import settings

    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )
    return _project_to_response(project)


@router.patch("/{project_id}")
async def update_project(
    project_id: str, data: SongProjectUpdate,
) -> SongProjectResponse:
    """Update project fields and/or add a story fragment."""
    from app.config import settings

    found = await store.update_project(
        project_id, data, db_path=settings.DB_PATH,
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )

    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    assert project is not None  # just updated
    return _project_to_response(project)


@router.post("/{project_id}/preview", status_code=status.HTTP_202_ACCEPTED)
async def create_preview(project_id: str) -> JobCreateResponse:
    """Generate a preview song from accumulated story fragments.

    Uses lyria-3-clip-preview model with 30s target duration.
    Requires at least one story fragment.
    """
    try:
        return await create_preview_job(project_id)
    except ValueError as exc:
        error_msg = str(exc)
        if error_msg == "no_story_fragments":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "no_story_fragments",
                    "message": "Add at least one story fragment before generating",
                },
            )
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "project_not_found", "project_id": project_id},
            )
        raise


@router.post("/{project_id}/final", status_code=status.HTTP_202_ACCEPTED)
async def create_final(project_id: str) -> JobCreateResponse:
    """Generate the final song from accumulated story fragments.

    Uses lyria-3-pro-preview model with 150s target duration.
    Requires at least one story fragment.
    """
    try:
        return await create_final_job(project_id)
    except ValueError as exc:
        error_msg = str(exc)
        if error_msg == "no_story_fragments":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "no_story_fragments",
                    "message": "Add at least one story fragment before generating",
                },
            )
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "project_not_found", "project_id": project_id},
            )
        raise


@router.post("/{project_id}/reference-audio")
async def upload_reference_audio(
    project_id: str, file: UploadFile,
) -> AudioReferenceResponse:
    """Upload an audio file as style reference for the project.

    Accepts MP3 files up to 20 MB. Analyzes the audio with Whisper
    (transcription + language detection) and pydub (duration, energy,
    tempo) to generate a style description used by Lyria 3.

    When MUSIC_PROVIDER=suno, the file is persisted for Suno Cover mode
    and a public reference_audio_url is returned.
    """
    from app.config import settings

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_format", "message": "Only MP3 files are supported"},
        )

    # Check project exists
    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )

    # Save uploaded file to temp
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    # Determine if we need to keep the file for Suno Cover mode
    music_provider = getattr(settings, "MUSIC_PROVIDER", "openclaw")
    is_suno = isinstance(music_provider, str) and music_provider == "suno"

    try:
        # Analyze
        result = analyze_audio(tmp_path)

        if hasattr(result, "error"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "analysis_failed", "detail": result.detail},
            )

        # Store description on project
        await store.update_project(
            project_id,
            SongProjectUpdate(reference_description=result.style_description),
            db_path=settings.DB_PATH,
        )

        ref_audio_url: str | None = None

        # Keep reference audio file for Suno Cover mode
        if is_suno:
            ref_audio.store_reference_audio(project_id, tmp_path)
            ref_audio_url = ref_audio.get_reference_audio_url(project_id)

        return AudioReferenceResponse(
            project_id=project_id,
            language=result.language,
            transcript_preview=result.transcript[:200] if result.transcript else "",
            duration_seconds=result.duration_seconds,
            energy=result.energy,
            estimated_tempo=result.estimated_tempo,
            style_description=result.style_description,
            reference_audio_url=ref_audio_url,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/ref-audio/{project_id}")
async def serve_reference_audio(project_id: str) -> FileResponse:
    """Serve a stored reference audio file for Suno Cover mode.

    Returns the MP3 file if it exists, otherwise 404.
    """
    ref_path = ref_audio.get_reference_audio_path(project_id)
    if ref_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "ref_audio_not_found", "project_id": project_id},
        )
    return FileResponse(
        path=str(ref_path),
        media_type="audio/mpeg",
        filename="reference.mp3",
    )
