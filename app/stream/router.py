"""Streaming router — GET /api/stream/{job_id}.

Returns audio/mpeg streaming with HTTP Range support.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.jobs import get_job
from app.stream import stream_generator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


def _build_stream_response(
    file_path: Path,
    status_code: int,
    headers: dict[str, str],
    range_header: str | None = None,
) -> StreamingResponse | Response:
    """Build a StreamingResponse for the given file.

    Supports HTTP Range requests when range_header is provided.
    """
    file_size = file_path.stat().st_size

    if range_header:
        try:
            start_str, _, end_str = range_header.replace("bytes=", "").partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1

            if start > end or start >= file_size:
                headers["Content-Range"] = f"bytes */{file_size}"
                return Response(status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE, headers=headers)

            if not end_str:  # open-ended range
                end = file_size - 1

            end = min(end, file_size - 1)
            content_length = end - start + 1

            async def _range_generator() -> AsyncGenerator[bytes, None]:
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

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(content_length)
            return StreamingResponse(
                _range_generator(),
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers=headers,
                media_type="audio/mpeg",
            )
        except (ValueError, IndexError):
            pass

    # Full file response
    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        stream_generator(file_path),
        status_code=status_code,
        headers=headers,
        media_type="audio/mpeg",
    )


@router.get("/api/stream/{job_id}")
async def stream_audio(job_id: str, request: Request) -> Response:
    """Stream the generated MP3 for a completed job.

    Supports HTTP Range requests for browser seeking.
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

        headers["X-Freemium-Preview"] = "true"

        range_header = request.headers.get("range")
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
