"""FastAPI application entry point for Canciones Automáticas.

Provides the API server with rate limiting, background job processing,
and endpoints for generation, status polling, and audio streaming.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import settings
from app.jobs import create_job, get_job
from app.jobs.cleanup import start_cleanup_scheduler
from app.jobs.worker import job_worker
from app.models import GenerateRequest, JobCreateResponse, JobStatusResponse
from app.stream.router import router as stream_router
from app.voice.registry import validate_registry

logger = logging.getLogger(__name__)

# ── Rate Limiting ────────────────────────────────────────────────────────────

_active_requests: int = 0
_active_requests_lock = asyncio.Lock()


async def _acquire_generation_slot() -> bool:
    """Try to acquire a generation slot.

    Returns True if slot acquired, False if at capacity.
    """
    global _active_requests
    async with _active_requests_lock:
        if _active_requests >= settings.MAX_CONCURRENT_JOBS:
            return False
        _active_requests += 1
        return True


async def _release_generation_slot() -> None:
    """Release a previously acquired generation slot."""
    global _active_requests
    async with _active_requests_lock:
        _active_requests = max(0, _active_requests - 1)


# ── Lifespan ─────────────────────────────────────────────────────────────────

_cleanup_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init DB, validate voice registry, start cleanup."""
    global _cleanup_task

    # Validate voice registry
    try:
        validate_registry()
        logger.info("Voice registry validated successfully")
    except ValueError as exc:
        logger.warning("Voice registry validation: %s", exc)

    # Start cleanup scheduler
    task, stop_event = start_cleanup_scheduler(
        interval_seconds=settings.CLEANUP_INTERVAL_SECONDS,
        ttl_hours=settings.JOB_TTL_HOURS,
        db_path=settings.DB_PATH,
        output_dir=settings.OUTPUT_DIR,
    )
    _cleanup_task = task

    logger.info(
        "Application started: max_concurrent=%d, cleanup_interval=%ds, ttl=%dh",
        settings.MAX_CONCURRENT_JOBS,
        settings.CLEANUP_INTERVAL_SECONDS,
        settings.JOB_TTL_HOURS,
    )

    yield

    # Shutdown
    stop_event.set()
    if _cleanup_task:
        _cleanup_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await _cleanup_task
    logger.info("Application shutdown complete")


# ── App Creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Canciones Automáticas",
    description="AI-powered personalized romantic song generator in Spanish",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Error Handlers ───────────────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # noqa: ARG001
    """Ensure HTTP exceptions return JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:  # noqa: ARG001
    """Handle Pydantic validation errors with clear messages."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation_error", "detail": exc.errors()},
    )


# ── Root ─────────────────────────────────────────────────────────────────────


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint returning API info."""
    return {
        "name": "Canciones Automáticas",
        "version": "0.1.0",
        "description": "AI-powered personalized romantic song generator in Spanish",
    }


# ── Generate Endpoint ────────────────────────────────────────────────────────


@app.post("/api/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_song(request: GenerateRequest) -> JobCreateResponse:
    """Create a new song generation job.

    Validates input, checks rate limit, creates job, and launches
    background worker. Returns 202 with job tracking endpoints.
    """
    # Check rate limit
    if not await _acquire_generation_slot():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "too_many_requests",
                    "message": "Server at capacity, try again later"},
            headers={"Retry-After": "30"},
        )

    try:
        job_id = await create_job(request, db_path=settings.DB_PATH)

        # Launch background worker
        asyncio.create_task(job_worker(job_id))

        logger.info(
            "Job created: %s (recipient=%s, genre=%s)", job_id, request.recipient, request.genre,
        )

        return JobCreateResponse(
            job_id=job_id,
            status="queued",
            estimated_total_seconds=180,
            endpoints={
                "status": f"/api/status/{job_id}",
                "stream": f"/api/stream/{job_id}",
            },
        )
    finally:
        await _release_generation_slot()


# ── Status Endpoint ──────────────────────────────────────────────────────────


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get the current status of a generation job."""
    job = await get_job(job_id, db_path=settings.DB_PATH)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        )

    import json as json_module

    metadata: dict[str, object] = {}
    with suppress(json_module.JSONDecodeError, TypeError):
        metadata = json_module.loads(job.get("metadata") or "{}")

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job.get("progress", 0.0),
        estimated_remaining_seconds=job.get("estimated_remaining", 0),
        error=job.get("error"),
        metadata=metadata,
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


# ── Register Routers ─────────────────────────────────────────────────────────

app.include_router(stream_router)
