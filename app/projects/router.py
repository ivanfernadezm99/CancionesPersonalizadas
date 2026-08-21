"""FastAPI router for song project management.

Provides endpoints for creating, reading, updating projects,
uploading audio references, and generating preview/final songs.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.audio_analysis import AudioAnalysisError, analyze_audio
from app.auth.dependencies import get_current_user
from app.lyrics import generate as lyrics_generate
from app.lyrics.providers import LyricsGenerationError
from app.models import (
    AudioReferenceResponse,
    CheckoutResponse,
    JobCreateResponse,
    LyricsResult,
    ProjectPreview,
    ReplaceFragmentsRequest,
    SongProjectCreate,
    SongProjectResponse,
    SongProjectUpdate,
    StoryFragmentResponse,
)
from app.projects import create_final_job, create_preview_job, ref_audio, store
from app.projects import create_project as orch_create_project
from app.projects.draft import normalize_draft
from app.projects.payment import create_checkout

router = APIRouter(prefix="/api/projects")


async def _check_project_ownership(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Verify the requester owns the project before a mutation.

    Returns the project dict. Raises 404 if not found, 401 if unauthenticated
    on an owned project, or 403 if the authenticated user doesn't match.
    """
    from app.config import settings, is_superadmin

    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "project_not_found",
                "project_id": project_id,
            },
        )
    owner = project.get("user_id")
    if owner:
        user_id = str(getattr(request.state, "user_id", "") or "")
        email = str(getattr(request.state, "email", "") or "")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "unauthorized"},
            )
        if user_id != owner and not is_superadmin(user_id, email):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "project_forbidden"},
            )
    else:
        # Auto-adopt unowned projects when an authenticated user accesses
        # them, so projects created before login become recoverable via
        # GET /api/projects/mine ("Mis canciones").
        user_id = str(getattr(request.state, "user_id", "") or "")
        if user_id:
            await store.link_project_to_user(project_id, user_id, db_path=settings.DB_PATH)
            project["user_id"] = user_id
    return project


def _project_to_response(project: dict[str, Any]) -> SongProjectResponse:
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
            status=p.get("status") or "unknown",
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
        user_id=project.get("user_id"),
        reference_song=project.get("reference_song"),
        reference_description=project.get("reference_description"),
        reference_audio_url=(
            ref_audio.get_reference_audio_url(project["id"])
            if ref_audio.has_reference_audio(project["id"])
            else None
        ),
        idea=project.get("idea"),
        status=project["status"],
        fragments=fragments,
        previews=previews,
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(data: SongProjectCreate, request: Request) -> dict[str, Any]:
    """Create a new song project.

    Returns the project ID and status.
    """
    user_id = str(getattr(request.state, "user_id", "") or "")
    project_id = await orch_create_project(data, user_id=user_id)
    return {
        "id": project_id,
        "status": "draft",
        "endpoints": {"project": f"/api/projects/{project_id}"},
    }


@router.get("")
async def list_projects(request: Request) -> list[SongProjectResponse]:
    """List the authenticated user's projects (newest first)."""
    from app.config import settings

    user_id = str(getattr(request.state, "user_id", "") or "")
    projects = await store.list_projects(user_id, db_path=settings.DB_PATH)
    return [_project_to_response(p) for p in projects]


@router.get("/mine")
async def my_projects(
    user: dict[str, str] = Depends(get_current_user),  # noqa: B008
) -> list[SongProjectResponse]:
    """List the projects of the authenticated user.

    Superadmin (SUPERADMIN_USER_IDS) sees ALL projects; regular users see
    only their own.
    """
    from app.config import settings, is_superadmin

    if is_superadmin(user.get("user_id", ""), user.get("email", "")):
        projects = await store.list_all_projects(db_path=settings.DB_PATH)
    else:
        projects = await store.list_projects(user["user_id"], db_path=settings.DB_PATH)
    return [_project_to_response(p) for p in projects]


@router.get("/lookup")
async def lookup_by_email(email: str) -> list[dict[str, str]]:
    """Look up minimal project info by customer email for song recovery.

    Returns only id, recipient, status, created_at — never fragments or
    other internal fields.
    """
    from app.config import settings

    if not email or not email.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "email_required", "message": "Email parameter is required"},
        )
    projects = await store.lookup_projects_by_email(email, db_path=settings.DB_PATH)
    return [
        {
            "id": p["id"],
            "recipient": p["recipient"],
            "status": p["status"],
            "created_at": p["created_at"],
        }
        for p in projects
    ]


@router.get("/stats")
async def get_stats() -> dict[str, int]:
    """Public usage stats for the landing counter.

    Returns completed preview and full-song generations:
    ``{"previews": int, "songs": int}``. Public (no JWT) so the marketing
    landing can consume it directly.
    """
    from app.config import settings
    return await store.get_usage_stats(db_path=settings.DB_PATH)


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request) -> SongProjectResponse:
    """Get a project by ID with all fragments and previews."""
    project = await _check_project_ownership(project_id, request)
    return _project_to_response(project)


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    data: SongProjectUpdate,
    request: Request,
) -> SongProjectResponse:
    """Update project fields and/or add a story fragment."""
    await _check_project_ownership(project_id, request)

    from app.config import settings

    found = await store.update_project(
        project_id,
        data,
        db_path=settings.DB_PATH,
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )

    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    assert project is not None  # just updated
    return _project_to_response(project)


COMPLETED_STATUSES = frozenset({"paid", "completed"})


@router.put("/{project_id}/fragments")
async def replace_fragments(
    project_id: str,
    data: ReplaceFragmentsRequest,
    request: Request,
) -> SongProjectResponse:
    """Replace the full story fragment list of a project.

    Returns 409 Conflict if the project is already paid or completed.
    """
    project = await _check_project_ownership(project_id, request)

    if project["status"] in COMPLETED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "project_locked",
                "message": "Fragments cannot be replaced once the project is paid or completed",
                "project_id": project_id,
                "current_status": project["status"],
            },
        )

    from app.config import settings

    found = await store.replace_fragments(
        project_id,
        data.fragments,
        db_path=settings.DB_PATH,
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )

    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    assert project is not None  # just replaced
    return _project_to_response(project)


@router.post("/{project_id}/preview", status_code=status.HTTP_202_ACCEPTED)
async def create_preview(project_id: str, request: Request) -> JobCreateResponse:
    """Generate a preview song from accumulated story fragments.

    Uses lyria-3-clip-preview model with 30s target duration.
    Requires at least one story fragment.
    Requires a valid Cloudflare Turnstile token when TURNSTILE_SECRET_KEY is set.
    """
    from app.auth.turnstile import verify_turnstile

    await verify_turnstile(request)

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
            ) from exc
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "project_not_found", "project_id": project_id},
            ) from exc
        raise


@router.post("/{project_id}/final", status_code=status.HTTP_202_ACCEPTED)
async def create_final(project_id: str, request: Request) -> JobCreateResponse:
    """Generate the final song from accumulated story fragments.

    Uses lyria-3-pro-preview model with 150s target duration.
    Requires at least one story fragment and a 'paid' project status.
    Returns 402 Payment Required if the project has not been paid.
    """

    project = await _check_project_ownership(project_id, request)

    if project["status"] != "paid":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "payment_required",
                "message": "Project must be paid before generating the final song",
                "project_id": project_id,
                "current_status": project["status"],
            },
        )

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
            ) from exc
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "project_not_found", "project_id": project_id},
            ) from exc
        raise


@router.post("/{project_id}/lyrics-draft", response_model=LyricsResult)
async def lyrics_draft(project_id: str, request: Request) -> LyricsResult:
    """Generate editable draft lyrics for a project (RQ-DRAFT-01).

    Combines the project's recipient, accumulated story fragments, and the
    optional ``idea`` seed, then calls the lyrics generation cascade with a
    hard-coded ``occasion="personalizada"`` (there is no occasion column).

    Maps any ``LyricsGenerationError`` (all providers failed OR draft < 10
    lines) to a 503 "all LLM providers unavailable".
    """
    from app.config import settings

    project = await _check_project_ownership(project_id, request)

    story = await store.get_accumulated_story(project_id, db_path=settings.DB_PATH)
    idea = project.get("idea")

    try:
        result = await lyrics_generate(
            recipient=project["recipient"],
            relationship=project["relationship"],
            occasion="personalizada",
            genre=project["genre"],
            mood=project["mood"],
            story=story,
            idea=idea,
            reference_song=project.get("reference_song"),
            reference_description=project.get("reference_description"),
        )
    except LyricsGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "all_llm_providers_unavailable",
                "message": "all LLM providers unavailable",
            },
        ) from exc

    try:
        return normalize_draft(result)
    except LyricsGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "all_llm_providers_unavailable",
                "message": "all LLM providers unavailable",
            },
        ) from exc


@router.post("/{project_id}/reference-audio")
async def upload_reference_audio(
    project_id: str,
    file: UploadFile,
    request: Request,
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

    # Check project exists + ownership
    await _check_project_ownership(project_id, request)

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

        if isinstance(result, AudioAnalysisError):
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


# Register the checkout route on the projects router (under /api/projects/{id}/checkout)
router.add_api_route(
    "/{project_id}/checkout",
    create_checkout,
    methods=["POST"],
    response_model=CheckoutResponse,
)


@router.get("/ref-audio/{project_id}")
async def serve_reference_audio(project_id: str, request: Request) -> FileResponse:
    """Serve a stored reference audio file for Suno Cover mode.

    Returns the MP3 file if it exists, otherwise 404.
    """
    await _check_project_ownership(project_id, request)
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
