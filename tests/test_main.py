"""Tests for app/main.py — FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def test_app(tmp_path: Path):
    """Create test app with patched settings."""
    from app.config import settings

    original_db = settings.DB_PATH
    original_output = settings.OUTPUT_DIR
    settings.DB_PATH = str(tmp_path / "test.db")
    settings.OUTPUT_DIR = str(tmp_path / "output")

    # Need to reload modules to pick up new settings
    # But we can't easily do that, so let's patch inside tests

    yield

    settings.DB_PATH = original_db
    settings.OUTPUT_DIR = original_output


class TestGenerateEndpoint:
    """Tests for POST /api/generate."""

    @pytest.mark.asyncio
    async def test_generate_returns_202(self, tmp_path: Path) -> None:
        """POST /api/generate should return 202 with job_id."""
        from app.config import settings
        from app.main import app

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("app.main.job_worker"):  # Don't actually run worker
                    response = await client.post(
                        "/api/generate",
                        json={
                            "recipient": "María",
                            "relationship": "pareja",
                            "occasion": "aniversario",
                            "genre": "bachata",
                            "mood": "romántica",
                            "voice": "female",
                        },
                    )

                    assert response.status_code == 202
                    data = response.json()
                    assert "job_id" in data
                    assert data["status"] == "queued"
                    assert "endpoints" in data
                    assert "status" in data["endpoints"]
                    assert "stream" in data["endpoints"]
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_generate_returns_422_on_validation_error(
        self, tmp_path: Path,
    ) -> None:
        """POST /api/generate should return 422 for invalid input."""
        from app.config import settings
        from app.main import app

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/generate",
                    json={"recipient": ""},  # Missing required fields
                )

                assert response.status_code == 422
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_generate_429_when_at_capacity(self) -> None:
        """Rate limiting should reject with 429 when at capacity."""
        from app.config import settings
        from app.main import _acquire_generation_slot, _release_generation_slot

        original_max = settings.MAX_CONCURRENT_JOBS
        try:
            settings.MAX_CONCURRENT_JOBS = 2

            # First two should succeed
            assert await _acquire_generation_slot() is True
            assert await _acquire_generation_slot() is True

            # Third should be rejected
            assert await _acquire_generation_slot() is False

            # Release one
            await _release_generation_slot()

            # Now one more should succeed
            assert await _acquire_generation_slot() is True

            # Release all
            await _release_generation_slot()
            await _release_generation_slot()
        finally:
            settings.MAX_CONCURRENT_JOBS = original_max


class TestStatusEndpoint:
    """Tests for GET /api/status/{job_id}."""

    @pytest.mark.asyncio
    async def test_status_returns_job_info(self, tmp_path: Path) -> None:
        """GET /api/status/{id} should return job status."""
        from app.config import settings
        from app.jobs import create_job
        from app.main import app
        from app.models import GenerateRequest

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = str(tmp_path / "test.db")

            # Create a job
            job_id = await create_job(
                GenerateRequest(
                    recipient="Test", relationship="x", occasion="x",
                    genre="pop", mood="happy", voice="female",
                ),
                db_path=settings.DB_PATH,
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/status/{job_id}")

                assert response.status_code == 200
                data = response.json()
                assert data["job_id"] == job_id
                assert data["status"] == "queued"
        finally:
            settings.DB_PATH = original_db

    @pytest.mark.asyncio
    async def test_status_returns_404(self, tmp_path: Path) -> None:
        """GET /api/status for non-existent job should return 404."""
        from app.config import settings
        from app.main import app

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = str(tmp_path / "test.db")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/status/nonexistent")

                assert response.status_code == 404
        finally:
            settings.DB_PATH = original_db


class TestStreamEndpoint:
    """Tests for GET /api/stream/{job_id}."""

    @pytest.mark.asyncio
    async def test_stream_via_app(self, tmp_path: Path) -> None:
        """Stream endpoint should work through the full app."""
        from app.config import settings
        from app.jobs import create_job, update_status
        from app.main import app
        from app.models import GenerateRequest

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "test.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            job_id = await create_job(
                GenerateRequest(
                    recipient="Test", relationship="x", occasion="x",
                    genre="pop", mood="happy", voice="female",
                ),
                db_path=settings.DB_PATH,
            )

            # Progress to complete
            await update_status(job_id, "lyrics_generating", db_path=settings.DB_PATH)
            await update_status(job_id, "music_generating", db_path=settings.DB_PATH)
            await update_status(job_id, "processing", db_path=settings.DB_PATH)
            await update_status(job_id, "complete", db_path=settings.DB_PATH)

            # Create MP3 file
            out_dir = Path(settings.OUTPUT_DIR) / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "final.mp3").write_bytes(b"MP3 audio data here")

            # Create paid project and link job
            import aiosqlite
            from datetime import datetime, timezone
            from app.projects.store import init_schema

            conn = await aiosqlite.connect(settings.DB_PATH)
            conn.row_factory = aiosqlite.Row
            try:
                await conn.execute("PRAGMA journal_mode=WAL")
                await init_schema(settings.DB_PATH, conn=conn)
                now = datetime.now(timezone.utc).isoformat()
                project_id = f"proj-{job_id}"
                await conn.execute(
                    """INSERT OR IGNORE INTO projects
                       (id, recipient, relationship, genre, mood, voice,
                        status, paid_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'paid', ?, ?, ?)""",
                    (project_id, "Test", "test", "pop", "happy", "female", now, now, now),
                )
                await conn.execute(
                    """INSERT OR IGNORE INTO project_jobs (project_id, job_id, job_type, created_at)
                       VALUES (?, ?, 'final', ?)""",
                    (project_id, job_id, now),
                )
                await conn.commit()
            finally:
                await conn.close()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/stream/{job_id}")

                assert response.status_code == 200
                assert response.headers.get("content-type") == "audio/mpeg"
                assert response.headers.get("X-Paid-Content") == "true"
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output


class TestRootEndpoint:
    """Tests for root endpoint."""

    @pytest.mark.asyncio
    async def test_root_returns_info(self, tmp_path: Path) -> None:
        """GET / should return API info."""
        from app.config import settings
        from app.main import app

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = str(tmp_path / "test.db")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/")
                assert response.status_code == 200
                data = response.json()
                assert "name" in data
                assert "version" in data
        finally:
            settings.DB_PATH = original_db
