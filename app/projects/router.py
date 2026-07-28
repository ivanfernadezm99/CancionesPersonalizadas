"""FastAPI router for song project management.

Provides endpoints for creating, reading, updating projects, and
generating preview/final songs via the project orchestrator.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models import (
    JobCreateResponse,
    SongProjectCreate,
    SongProjectResponse,
    SongProjectUpdate,
    StoryFragmentResponse,
    ProjectPreview,
)
from app.projects import create_final_job, create_preview_job
from app.projects import create_project as orch_create_project
from app.projects import store

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
