"""Tests for app/stream/router.py — GET /api/stream/{job_id}."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import GenerateRequest


@pytest.fixture
def app_with_routes(tmp_path: Path):
    """Create a test FastAPI app with the stream router registered and a mock app."""
    from fastapi import FastAPI

    from app.stream.router import router

    app = FastAPI()
    app.include_router(router)

    # Store tmp_path in app state for test use
    app.state.test_output_dir = str(tmp_path)
    return app


@pytest.fixture
def client(app_with_routes):
    """Create test client."""
    transport = ASGITransport(app=app_with_routes)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_job_row(
    db_path: str,
    job_id: str,
    status: str = "complete",
    error: str | None = None,
) -> None:
    """Insert a job row directly into the test DB."""
    from app.jobs.store import get_connection, init_db

    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        params = GenerateRequest(
            recipient="Test",
            relationship="test",
            occasion="test",
            genre="pop",
            mood="happy",
            voice="female",
        )
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            """INSERT INTO jobs (job_id, status, params, progress, error, created_at, updated_at)
               VALUES (?, ?, ?, 1.0, ?, ?, ?)""",
            (job_id, status, params.model_dump_json(), error, now, now),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _create_mp3(output_dir: str, job_id: str, size_kb: int = 100) -> Path:
    """Create a mock MP3 file for the job_id."""
    out_dir = Path(output_dir) / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / "final.mp3"
    file_path.write_bytes(b"X" * size_kb * 1024)
    return file_path


class TestStreamRouter:
    """Tests for GET /api/stream/{job_id}."""

    @pytest.mark.asyncio
    async def test_stream_returns_200_for_completed_job(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Completed job should return 200 with audio/mpeg."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            await _create_job_row(settings.DB_PATH, "job-complete", status="complete")
            await _create_mp3(settings.OUTPUT_DIR, "job-complete")

            response = await client.get("/api/stream/job-complete")

            assert response.status_code == 200
            assert response.headers.get("content-type") == "audio/mpeg"
            assert response.headers.get("X-Job-Status") == "complete"
            assert response.headers.get("X-Freemium-Preview") == "true"
            assert response.headers.get("accept-ranges") == "bytes"
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_stream_returns_404_for_missing_job(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Non-existent job should return 404."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            response = await client.get("/api/stream/nonexistent")

            assert response.status_code == 404
            data = response.json()
            assert "error" in data or "detail" in data
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_stream_returns_409_for_in_progress_job(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """In-progress job should return 409."""
        from app.config import settings

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = str(tmp_path / "test.db")

            await _create_job_row(settings.DB_PATH, "job-inprogress", status="music_generating")

            response = await client.get("/api/stream/job-inprogress")

            assert response.status_code == 409
            data = response.json()
            assert "error" in data or "detail" in data
            headers_lower = str(response.headers).lower()
            assert "retry-after" in headers_lower
        finally:
            settings.DB_PATH = original_db

    @pytest.mark.asyncio
    async def test_stream_returns_410_for_failed_job(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Failed job should return 410."""
        from app.config import settings

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = str(tmp_path / "test.db")

            await _create_job_row(
                settings.DB_PATH, "job-failed", status="failed", error="Music gen error",
            )

            response = await client.get("/api/stream/job-failed")

            assert response.status_code == 410
        finally:
            settings.DB_PATH = original_db

    @pytest.mark.asyncio
    async def test_stream_range_request_returns_206(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Range request should return 206 Partial Content."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            await _create_job_row(settings.DB_PATH, "job-range", status="complete")
            file_path = await _create_mp3(settings.OUTPUT_DIR, "job-range", size_kb=500)

            file_size = file_path.stat().st_size
            response = await client.get(
                "/api/stream/job-range",
                headers={"Range": "bytes=0-1023"},
            )

            assert response.status_code == 206
            assert response.headers.get("content-type") == "audio/mpeg"
            assert f"bytes 0-1023/{file_size}" in response.headers.get("content-range", "")
            assert len(response.content) == 1024
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_stream_open_ended_range(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Open-ended Range should return remaining bytes."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            await _create_job_row(settings.DB_PATH, "job-open", status="complete")
            file_path = await _create_mp3(settings.OUTPUT_DIR, "job-open", size_kb=100)

            file_size = file_path.stat().st_size
            response = await client.get(
                "/api/stream/job-open",
                headers={"Range": "bytes=1000-"},
            )

            assert response.status_code == 206
            assert f"1000-{file_size - 1}/{file_size}" in response.headers.get("content-range", "")
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_stream_invalid_range_returns_416(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Invalid range should return 416."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            await _create_job_row(settings.DB_PATH, "job-416", status="complete")
            file_path = await _create_mp3(settings.OUTPUT_DIR, "job-416", size_kb=10)

            file_size = file_path.stat().st_size
            response = await client.get(
                "/api/stream/job-416",
                headers={"Range": f"bytes={file_size + 1000}-{file_size + 9999}"},
            )

            assert response.status_code == 416
            assert f"bytes */{file_size}" in response.headers.get("content-range", "")
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_stream_no_mp3_file_returns_410(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Completed job with missing MP3 should return 410."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            await _create_job_row(settings.DB_PATH, "job-nofile", status="complete")
            # Don't create MP3 file

            response = await client.get("/api/stream/job-nofile")

            assert response.status_code == 410
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output
