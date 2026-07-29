"""Tests for payment gating in app/stream/router.py — Phase 4.

Tests:
- test_preview_free: ?preview=true returns 206 with X-Freemium-Preview header
- test_full_without_payment: returns 402 Payment Required
- test_full_with_payment: returns 206 with X-Paid-Content header
- test_preview_range: preview with Range header returns correctly truncated 206
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from app.models import GenerateRequest


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_routes(tmp_path: Path):
    """Create a test FastAPI app with the stream router registered."""
    from fastapi import FastAPI

    from app.stream.router import router

    app = FastAPI()
    app.include_router(router)
    app.state.test_output_dir = str(tmp_path)
    return app


@pytest.fixture
def client(app_with_routes):
    """Create test client."""
    transport = ASGITransport(app=app_with_routes)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Helpers ───────────────────────────────────────────────────────────────────


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


async def _create_project_and_link(
    db_path: str,
    project_id: str,
    job_id: str,
    status: str = "paid",
) -> None:
    """Create a project row and link it to a job."""
    from app.projects.store import init_schema
    from datetime import datetime, timezone

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        await init_schema(db_path, conn=conn)

        now = datetime.now(timezone.utc).isoformat()
        paid_at = now if status == "paid" else None

        await conn.execute(
            """INSERT OR IGNORE INTO projects
               (id, recipient, relationship, genre, mood, voice,
                status, paid_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, "Test", "test", "pop", "happy", "female",
             status, paid_at, now, now),
        )

        await conn.execute(
            """INSERT OR IGNORE INTO project_jobs (project_id, job_id, job_type, created_at)
               VALUES (?, ?, ?, ?)""",
            (project_id, job_id, "final", now),
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


async def _get_test_app_settings(tmp_path: Path) -> dict[str, Any]:
    """Return settings overrides pointing to temp paths."""
    return {
        "DB_PATH": str(tmp_path / "test_gating.db"),
        "OUTPUT_DIR": str(tmp_path / "output"),
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestStreamGating:
    """Tests for payment-gated streaming (Phase 4)."""

    @pytest.mark.asyncio
    async def test_preview_free(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """?preview=true returns 206 Partial Content with X-Freemium-Preview header."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            cfg = await _get_test_app_settings(tmp_path)
            settings.DB_PATH = cfg["DB_PATH"]
            settings.OUTPUT_DIR = cfg["OUTPUT_DIR"]

            await _create_job_row(settings.DB_PATH, "job-preview", status="complete")
            # Unpaid project — preview should still work
            await _create_project_and_link(
                settings.DB_PATH, "proj-preview", "job-preview", status="draft",
            )
            await _create_mp3(settings.OUTPUT_DIR, "job-preview")

            response = await client.get("/api/stream/job-preview?preview=true")

            assert response.status_code == 206
            assert response.headers.get("content-type") == "audio/mpeg"
            assert response.headers.get("X-Freemium-Preview") == "true"
            assert response.headers.get("X-Paid-Content") is None
            assert response.headers.get("accept-ranges") == "bytes"
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_full_without_payment(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Full stream without payment returns 402."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            cfg = await _get_test_app_settings(tmp_path)
            settings.DB_PATH = cfg["DB_PATH"]
            settings.OUTPUT_DIR = cfg["OUTPUT_DIR"]

            await _create_job_row(settings.DB_PATH, "job-unpaid", status="complete")
            await _create_project_and_link(
                settings.DB_PATH, "proj-unpaid", "job-unpaid", status="draft",
            )
            await _create_mp3(settings.OUTPUT_DIR, "job-unpaid")

            response = await client.get("/api/stream/job-unpaid")

            assert response.status_code == 402
            data = response.json()
            assert "error" in data or "detail" in data
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_full_with_payment(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Full stream with paid project returns 206 with X-Paid-Content header."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            cfg = await _get_test_app_settings(tmp_path)
            settings.DB_PATH = cfg["DB_PATH"]
            settings.OUTPUT_DIR = cfg["OUTPUT_DIR"]

            await _create_job_row(settings.DB_PATH, "job-paid", status="complete")
            await _create_project_and_link(
                settings.DB_PATH, "proj-paid", "job-paid", status="paid",
            )
            file_path = await _create_mp3(settings.OUTPUT_DIR, "job-paid", size_kb=50)

            response = await client.get("/api/stream/job-paid")

            # Full file without Range header returns 200
            assert response.status_code == 200
            assert response.headers.get("content-type") == "audio/mpeg"
            assert response.headers.get("X-Paid-Content") == "true"
            assert response.headers.get("X-Freemium-Preview") is None
            # Should have Content-Length indicating full content
            file_size = file_path.stat().st_size
            assert int(response.headers.get("content-length", "0")) == file_size
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_preview_range(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        """Preview with Range header returns correctly truncated partial content."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            cfg = await _get_test_app_settings(tmp_path)
            settings.DB_PATH = cfg["DB_PATH"]
            settings.OUTPUT_DIR = cfg["OUTPUT_DIR"]

            await _create_job_row(settings.DB_PATH, "job-prange", status="complete")
            await _create_project_and_link(
                settings.DB_PATH, "proj-prange", "job-prange", status="draft",
            )
            file_path = await _create_mp3(settings.OUTPUT_DIR, "job-prange", size_kb=500)

            file_size = file_path.stat().st_size
            response = await client.get(
                "/api/stream/job-prange?preview=true",
                headers={"Range": "bytes=0-1023"},
            )

            assert response.status_code == 206
            assert response.headers.get("X-Freemium-Preview") == "true"
            assert response.headers.get("content-type") == "audio/mpeg"
            assert f"0-1023/{file_size}" in response.headers.get("content-range", "")
            assert len(response.content) == 1024
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output
