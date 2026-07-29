"""Streaming router — GET /api/stream/{job_id}.

Returns audio/mpeg streaming with HTTP Range support.
Supports preview (30s truncation via ?preview=true) and
payment gating (402 on full stream if project not paid).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.jobs import get_job
from app.stream import stream_generator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


async def _range_generator_internal(
    file_path: Path,
    start: int,
    content_length: int,
) -> AsyncGenerator[bytes, None]:
    """Read a portion of a file in chunks as an async generator."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = content_length
        while remaining > 0:
            chunk_size = min(65536, remaining)
            data = f.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            yield data


def _build_stream_response(
    file_path: Path,
    status_code: int,
    headers: dict[str, str],
    range_header: str | None = None,
    content_limit: int | None = None,
) -> StreamingResponse | Response:
    """Build a StreamingResponse for the given file.

    Supports HTTP Range requests when range_header is provided.
    When content_limit is set, only that many bytes are served and
    Content-Range reflects the actual file size as the total.
    """
    actual_file_size = file_path.stat().st_size
    effective_size = (
        min(actual_file_size, content_limit) if content_limit is not None else actual_file_size
    )

    if range_header:
        try:
            start_str, _, end_str = range_header.replace("bytes=", "").partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else effective_size - 1

            if start > end or start >= effective_size:
                headers["Content-Range"] = f"bytes */{actual_file_size}"
                return Response(status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE, headers=headers)

            if not end_str:  # open-ended range
                end = effective_size - 1

            end = min(end, effective_size - 1)
            response_length = end - start + 1

            headers["Content-Range"] = f"bytes {start}-{end}/{actual_file_size}"
            headers["Content-Length"] = str(response_length)
            return StreamingResponse(
                _range_generator_internal(file_path, start, response_length),
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers=headers,
                media_type="audio/mpeg",
            )
        except (ValueError, IndexError):
            pass

    # Full file or limited response
    headers["Content-Length"] = str(effective_size)
    return StreamingResponse(
        _range_generator_internal(file_path, 0, effective_size),
        status_code=status_code,
        headers=headers,
        media_type="audio/mpeg",
    )


def _get_preview_byte_limit(file_path: Path) -> int:
    """Calculate maximum bytes to serve for a 30-second preview.

    Uses estimated 128kbps bitrate: 128 * 1024 / 8 = 16384 bytes/sec.
    """
    file_size = file_path.stat().st_size
    preview_bytes = settings.PREVIEW_TARGET_SECONDS * 16384
    return min(file_size, preview_bytes)


async def _get_project_by_job(
    job_id: str,
    db_path: str,
) -> dict[str, Any] | None:
    """Look up a project associated with a job via the project_jobs table.

    Returns the project dict, or None if no link found.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        cursor = await conn.execute(
            """SELECT p.* FROM projects p
               JOIN project_jobs pj ON pj.project_id = p.id
               WHERE pj.job_id = ?""",
            (job_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await conn.close()


@router.get("/api/stream/{job_id}")
async def stream_audio(
    job_id: str,
    request: Request,
    preview: bool = False,
) -> Response:
    """Stream the generated MP3 for a completed job.

    Supports HTTP Range requests for browser seeking.

    Query params:
        preview (bool): If true, serve only the first 30 seconds (free preview).

    Payment gating:
        Full streams (preview=false) require the project status to be "paid".
        Returns 402 Payment Required if the project is not paid.
    """
    job = await get_job(job_id, db_path=settings.DB_PATH)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        )

    headers: dict[str, str] = {
        "X-Job-Status": job["status"],
        "Accept-Ranges": "bytes",
    }

    if job["status"] == "complete":
        # Check for MP3 file
        file_path = Path(settings.OUTPUT_DIR) / job_id / "final.mp3"
        if not file_path.exists():
            # Try generated.mp3
            file_path = Path(settings.OUTPUT_DIR) / job_id / "generated.mp3"

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"error": "file_not_found", "job_id": job_id},
            )

        range_header = request.headers.get("range")

        if preview:
            # Preview mode: free for all, truncated to ~30s
            headers["X-Freemium-Preview"] = "true"
            preview_limit = _get_preview_byte_limit(file_path)
            return _build_stream_response(
                file_path=file_path,
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers=headers,
                range_header=range_header,
                content_limit=preview_limit,
            )

        # Full stream: check payment status
        project = await _get_project_by_job(job_id, db_path=settings.DB_PATH)
        if project is None or project["status"] != "paid":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "payment_required",
                    "message": "Full stream requires payment. Use ?preview=true for a free preview.",
                    "job_id": job_id,
                },
            )

        headers["X-Paid-Content"] = "true"
        return _build_stream_response(
            file_path=file_path,
            status_code=status.HTTP_200_OK,
            headers=headers,
            range_header=range_header,
        )

    if job["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": job.get("error", "Job failed"), "job_id": job_id},
        )

    # In-progress statuses
    headers["Retry-After"] = str(job.get("estimated_remaining", 60))
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "job_in_progress",
            "job_id": job_id,
            "status": job["status"],
        },
        headers=headers,
    )
