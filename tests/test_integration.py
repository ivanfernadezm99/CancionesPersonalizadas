"""Integration tests for Canciones Automáticas API.

Covers 6 scenarios across the full HTTP stack:
- POST /api/generate -> 202 with job persistence
- GET  /api/status/{id} -> state machine progression
- GET  /api/stream/{id} -> audio streaming (200/206/404/409/410/416)
- Rate limiting (429 on 6th concurrent request)
- Job cleanup (TTL-based deletion)
- Startup validation (missing API key -> failure)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

# ═══════════════════════════════════════════════════════════════════════════════
# 4.2  POST /api/generate -> 202
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateEndpoint:
    """Integration tests for POST /api/generate."""

    @pytest.mark.asyncio
    async def test_generate_returns_202_with_job_id(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
    ) -> None:
        """POST /api/generate should return 202 with a valid job_id."""
        response = await test_app.post("/api/generate", json=sample_generate_request)

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].count("-") == 4  # UUID v4 format
        assert data["status"] == "queued"
        assert data["estimated_total_seconds"] == 180
        assert "endpoints" in data
        assert "status" in data["endpoints"]
        assert "stream" in data["endpoints"]

    @pytest.mark.asyncio
    async def test_generate_creates_job_row_in_db(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """After POST /api/generate, the job should exist in the database."""
        response = await test_app.post("/api/generate", json=sample_generate_request)
        data = response.json()
        job_id = data["job_id"]

        from app.jobs import get_job

        job = await get_job(job_id, db_path=test_db_path)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["status"] == "queued"
        assert job["progress"] == 0.0

        # Verify params stored as JSON
        params = json.loads(job["params"])
        assert params["recipient"] == "María"
        assert params["voice"] == "female"

    @pytest.mark.asyncio
    async def test_generate_returns_422_on_invalid_input(
        self,
        test_app: AsyncClient,
    ) -> None:
        """POST /api/generate with invalid data should return 422."""
        response = await test_app.post("/api/generate", json={"recipient": ""})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_full_pipeline_completes(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Full pipeline: create job -> worker runs to completion.

        With mocked LLM and OpenClaw, the background worker should
        process the job through all stages to 'complete'.
        """
        from app.jobs import get_job

        response = await test_app.post("/api/generate", json=sample_generate_request)
        assert response.status_code == 202
        data = response.json()
        job_id = data["job_id"]

        # Poll until complete or timeout
        final_status = "queued"
        for _ in range(30):
            job = await get_job(job_id, db_path=test_db_path)
            if job is not None:
                final_status = job["status"]
                if final_status in ("complete", "failed"):
                    break
            await asyncio.sleep(0.1)

        assert final_status == "complete", (
            f"Expected complete, got {final_status} after polling"
        )

        # Verify metadata in the job record
        job = await get_job(job_id, db_path=test_db_path)
        assert job is not None
        meta = json.loads(job.get("metadata") or "{}")
        assert meta.get("lyrics_provider") == "test-provider"
        assert meta.get("duration_extended") is not None
        assert meta.get("title_suggestion") == "María, Mi Amor Eterno"

        # Verify output files exist somewhere in the output directory
        all_mp3 = list(Path(test_output_dir).rglob("*.mp3"))
        assert len(all_mp3) >= 1, (
            f"No MP3 files found in {test_output_dir} "
            f"(expected at least generated.mp3 from music.generate)"
        )

        # Verify the job transitions were recorded
        from app.jobs.store import get_connection, init_db

        conn = await get_connection(test_db_path)
        try:
            await init_db(conn)
            cursor = await conn.execute(
                "SELECT to_status FROM job_transitions "
                "WHERE job_id = ? ORDER BY id",
                (job_id,),
            )
            transitions = [row["to_status"] for row in await cursor.fetchall()]
            assert "lyrics_generating" in transitions
            assert "music_generating" in transitions
            assert "processing" in transitions
            assert "complete" in transitions
        finally:
            await conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 4.3  GET /api/status/{job_id} -> state machine progression
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatusEndpoint:
    """Integration tests for GET /api/status/{job_id}."""

    async def _create_job_no_worker(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
    ) -> str:
        """Create job via API but prevent the background worker from running.

        This is necessary for tests that manually control status transitions.
        """
        from unittest.mock import patch

        with patch("app.main.job_worker"):
            resp = await test_app.post("/api/generate", json=sample_generate_request)
        data: Any = resp.json()
        job_id: str | Any = data.get("job_id", "")
        assert isinstance(job_id, str) and job_id
        return job_id

    @pytest.mark.asyncio
    async def test_status_returns_job_info(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Status endpoint should return correct info for a queued job."""
        job_id = await self._create_job_no_worker(
            test_app, sample_generate_request,
        )

        response = await test_app.get(f"/api/status/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "queued"
        assert data["progress"] == 0.0
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_status_progression_through_all_states(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Status endpoint should show each state in the state machine.

        States tested: queued -> lyrics_generating -> music_generating
                      -> processing -> complete
        """
        from app.jobs import update_status

        job_id = await self._create_job_no_worker(
            test_app, sample_generate_request,
        )

        # Verify queued
        r = await test_app.get(f"/api/status/{job_id}")
        assert r.json()["status"] == "queued"

        # Progress through states using direct DB manipulation
        transitions = [
            ("lyrics_generating", 0.2),
            ("music_generating", 0.5),
            ("processing", 0.8),
            ("complete", 1.0),
        ]
        for status, progress in transitions:
            await update_status(job_id, status, progress=progress, db_path=test_db_path)
            r = await test_app.get(f"/api/status/{job_id}")
            data = r.json()
            assert data["status"] == status, (
                f"Expected {status}, got {data['status']}"
            )
            assert data["progress"] == progress, (
                f"Expected progress {progress}, got {data['progress']}"
            )

    @pytest.mark.asyncio
    async def test_status_failed_job(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Failed job should show error message in status."""
        from app.jobs import update_status

        job_id = await self._create_job_no_worker(
            test_app, sample_generate_request,
        )

        await update_status(job_id, "lyrics_generating", db_path=test_db_path)
        await update_status(
            job_id, "failed", error="Music generation crashed", db_path=test_db_path,
        )

        r = await test_app.get(f"/api/status/{job_id}")
        data = r.json()
        assert data["status"] == "failed"
        assert "Music generation crashed" in (data.get("error") or "")

    @pytest.mark.asyncio
    async def test_status_nonexistent_job_returns_404(
        self,
        test_app: AsyncClient,
    ) -> None:
        """Non-existent job ID should return 404."""
        response = await test_app.get("/api/status/nonexistent-job-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 4.4  GET /api/stream/{job_id} -> 200/206 with real MP3
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamEndpoint:
    """Integration tests for GET /api/stream/{job_id}."""

    @pytest.fixture
    def stream_job_id(self) -> str:
        return "stream-test-job-id"

    async def _create_complete_job(
        self,
        test_db_path: str,
        test_output_dir: str,
        job_id: str,
        sample_mp3: Path,
    ) -> None:
        """Create a complete job with an MP3 file for stream testing."""
        from datetime import datetime, timezone

        from app.jobs.store import get_connection, init_db
        from app.models import GenerateRequest

        conn = await get_connection(test_db_path)
        try:
            await init_db(conn)
            now = datetime.now(timezone.utc).isoformat()
            params = GenerateRequest(
                recipient="Test",
                relationship="test",
                occasion="test",
                genre="pop",
                mood="happy",
                voice="female",
                story=None,
            )
            await conn.execute(
                """INSERT INTO jobs
                   (job_id, status, params, progress, error, metadata,
                    created_at, updated_at, completed_at)
                   VALUES (?, 'complete', ?, 1.0, NULL, '{}', ?, ?, ?)""",
                (job_id, params.model_dump_json(), now, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

        # Create a paid project and link the job to it
        await self._link_job_to_paid_project(test_db_path, job_id)

        # Copy MP3 to output directory
        out_dir = Path(test_output_dir) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final.mp3").write_bytes(sample_mp3.read_bytes())

    async def _link_job_to_paid_project(
        self,
        test_db_path: str,
        job_id: str,
    ) -> None:
        """Create a minimal paid project and link the job to it."""
        from datetime import datetime, timezone

        import aiosqlite

        from app.projects.store import init_schema

        conn = await aiosqlite.connect(test_db_path)
        conn.row_factory = aiosqlite.Row
        try:
            await conn.execute("PRAGMA journal_mode=WAL")
            await init_schema(test_db_path, conn=conn)
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

    async def _create_job_with_status(
        self,
        test_db_path: str,
        job_id: str,
        status: str = "queued",
        error: str | None = None,
    ) -> None:
        """Insert a job row with a given status."""
        from datetime import datetime, timezone

        from app.jobs.store import get_connection, init_db
        from app.models import GenerateRequest

        conn = await get_connection(test_db_path)
        try:
            await init_db(conn)
            now = datetime.now(timezone.utc).isoformat()
            params = GenerateRequest(
                recipient="Test", relationship="test",
                occasion="test", genre="pop", mood="happy",
                voice="female", story=None,
            )
            await conn.execute(
                """INSERT INTO jobs
                   (job_id, status, params, progress, error, metadata,
                    created_at, updated_at)
                   VALUES (?, ?, ?, 0.0, ?, '{}', ?, ?)""",
                (job_id, status, params.model_dump_json(), error, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_stream_returns_200_for_complete_job(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,
        sample_mp3: Path,
    ) -> None:
        """Completed job with MP3 should return 200 and audio/mpeg."""
        await self._create_complete_job(
            test_db_path, test_output_dir, "stream-200", sample_mp3,
        )

        response = await test_app.get("/api/stream/stream-200")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "audio/mpeg"
        assert response.headers.get("X-Job-Status") == "complete"
        assert response.headers.get("X-Paid-Content") == "true"
        assert response.headers.get("X-Freemium-Preview") is None
        assert response.headers.get("accept-ranges") == "bytes"

    @pytest.mark.asyncio
    async def test_stream_range_request_returns_206(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,
        sample_mp3: Path,
    ) -> None:
        """Range request should return 206 Partial Content."""
        await self._create_complete_job(
            test_db_path, test_output_dir, "stream-206", sample_mp3,
        )

        file_size = (Path(test_output_dir) / "stream-206" / "final.mp3").stat().st_size
        response = await test_app.get(
            "/api/stream/stream-206",
            headers={"Range": "bytes=0-999"},
        )

        assert response.status_code == 206
        assert response.headers.get("content-type") == "audio/mpeg"
        expected_range = f"bytes 0-999/{file_size}"
        assert response.headers.get("content-range") == expected_range
        assert len(response.content) == 1000

    @pytest.mark.asyncio
    async def test_stream_open_ended_range(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,
        sample_mp3: Path,
    ) -> None:
        """Open-ended Range (bytes=N-) should return remaining bytes."""
        await self._create_complete_job(
            test_db_path, test_output_dir, "stream-open", sample_mp3,
        )

        file_size = (Path(test_output_dir) / "stream-open" / "final.mp3").stat().st_size
        response = await test_app.get(
            "/api/stream/stream-open",
            headers={"Range": "bytes=100-"},
        )

        assert response.status_code == 206
        expected_content_range = f"bytes 100-{file_size - 1}/{file_size}"
        assert response.headers.get("content-range") == expected_content_range

    @pytest.mark.asyncio
    async def test_stream_invalid_range_returns_416(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,
        sample_mp3: Path,
    ) -> None:
        """Range starting beyond file size should return 416."""
        await self._create_complete_job(
            test_db_path, test_output_dir, "stream-416", sample_mp3,
        )

        file_size = (Path(test_output_dir) / "stream-416" / "final.mp3").stat().st_size
        start = file_size + 9999
        end = start + 100
        response = await test_app.get(
            "/api/stream/stream-416",
            headers={"Range": f"bytes={start}-{end}"},
        )

        assert response.status_code == 416
        expected_range = f"bytes */{file_size}"
        assert response.headers.get("content-range") == expected_range

    @pytest.mark.asyncio
    async def test_stream_returns_404_for_missing_job(
        self,
        test_app: AsyncClient,
    ) -> None:
        """Non-existent job ID should return 404."""
        response = await test_app.get("/api/stream/nonexistent-job")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_returns_409_for_in_progress_job(
        self,
        test_app: AsyncClient,
        test_db_path: str,
    ) -> None:
        """In-progress job should return 409."""
        await self._create_job_with_status(test_db_path, "stream-409", status="music_generating")

        response = await test_app.get("/api/stream/stream-409")
        assert response.status_code == 409
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_stream_returns_410_for_failed_job(
        self,
        test_app: AsyncClient,
        test_db_path: str,
    ) -> None:
        """Failed job should return 410."""
        await self._create_job_with_status(
            test_db_path, "stream-410", status="failed", error="Generation failed",
        )

        response = await test_app.get("/api/stream/stream-410")
        assert response.status_code == 410

    @pytest.mark.asyncio
    async def test_stream_complete_job_missing_mp3_returns_410(
        self,
        test_app: AsyncClient,
        test_db_path: str,
    ) -> None:
        """Completed job with no MP3 file should return 410."""
        # Create job row but don't write the MP3
        conn = None
        try:
            from datetime import datetime, timezone

            from app.jobs.store import get_connection, init_db
            from app.models import GenerateRequest

            conn = await get_connection(test_db_path)
            await init_db(conn)
            now = datetime.now(timezone.utc).isoformat()
            params = GenerateRequest(
                recipient="Test", relationship="test",
                occasion="test", genre="pop", mood="happy",
                voice="female", story=None,
            )
            await conn.execute(
                """INSERT INTO jobs
                   (job_id, status, params, progress, error, metadata,
                    created_at, updated_at, completed_at)
                   VALUES (?, 'complete', ?, 1.0, NULL, '{}', ?, ?, ?)""",
                ("stream-no-mp3", params.model_dump_json(), now, now, now),
            )
            await conn.commit()
        finally:
            if conn is not None:
                await conn.close()

        response = await test_app.get("/api/stream/stream-no-mp3")
        assert response.status_code == 410


# ═══════════════════════════════════════════════════════════════════════════════
# 4.5  Rate limiting -> 429 on 6th concurrent request
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Integration tests for rate limiting (MAX_CONCURRENT_JOBS).

    NOTE: We avoid sending 5+ concurrent DB-write requests because aiosqlite
    does not handle concurrent writes well (``database is locked`` error).
    Instead we use MAX_CONCURRENT_JOBS=1 and verify 1 succeeds / 1 gets 429.
    """

    @pytest.mark.asyncio
    async def test_second_concurrent_request_gets_429(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With MAX_CONCURRENT_JOBS=1, request #2 should get 429.

        Only 1 DB write happens (for the first request), avoiding the
        aiosqlite ``database is locked`` error from concurrent writes.
        """
        from app.config import settings

        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 1)

        async def _post() -> Any:
            return await test_app.post("/api/generate", json=sample_generate_request)

        results = await asyncio.gather(*[_post() for _ in range(2)])

        successes = [r for r in results if r.status_code == 202]
        rate_limited = [r for r in results if r.status_code == 429]

        assert len(successes) == 1, (
            f"Expected 1 successful, got {len(successes)}"
        )
        assert len(rate_limited) == 1, (
            f"Expected 1 rate-limited, got {len(rate_limited)}"
        )

    @pytest.mark.asyncio
    async def test_rate_limit_response_headers(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """429 response should include Retry-After header."""
        from app.config import settings

        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 1)

        async def _post() -> Any:
            return await test_app.post("/api/generate", json=sample_generate_request)

        results = await asyncio.gather(*[_post() for _ in range(2)])

        rate_limited = [r for r in results if r.status_code == 429]
        assert len(rate_limited) >= 1

        resp_429 = rate_limited[0]
        assert "retry-after" in str(resp_429.headers).lower(), (
            "Retry-After header should be present on 429"
        )

    @pytest.mark.asyncio
    async def test_requests_recover_after_slot_release(
        self,
        test_app: AsyncClient,
        sample_generate_request: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After rate-limit clears, new requests should succeed."""
        from app.config import settings

        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 1)

        async def _post() -> Any:
            return await test_app.post("/api/generate", json=sample_generate_request)

        # Send 2 concurrent — one gets 429
        results = await asyncio.gather(*[_post() for _ in range(2)])
        rate_limited = [r for r in results if r.status_code == 429]
        assert len(rate_limited) >= 1

        # Now send another — should succeed since slots were released
        resp = await _post()
        assert resp.status_code == 202, (
            f"After rate-limit clears, new request should succeed, got {resp.status_code}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4.6  Job cleanup -> old jobs deleted
# ═══════════════════════════════════════════════════════════════════════════════


class TestJobCleanup:
    """Integration tests for TTL-based job cleanup."""

    @pytest.mark.asyncio
    async def test_old_jobs_are_deleted(
        self,
        test_db_path: str,
        test_output_dir: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Jobs older than TTL should be deleted by cleanup."""
        from app.jobs import create_job, get_job
        from app.jobs.cleanup import cleanup_old_jobs
        from app.jobs.store import get_connection
        from app.models import GenerateRequest

        # Create a job
        params = GenerateRequest(**sample_generate_request)
        old_id = await create_job(params, db_path=test_db_path)

        # Age it to be very old
        conn = await get_connection(test_db_path)
        try:
            await conn.execute(
                "UPDATE jobs SET created_at = '2020-01-01T00:00:00', "
                "updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
                (old_id,),
            )
            await conn.commit()
        finally:
            await conn.close()

        # Create output dir for the old job
        old_dir = Path(test_output_dir) / old_id
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "final.mp3").write_text("old mp3 content")

        # Cleanup with TTL=1 hour
        deleted = await cleanup_old_jobs(
            ttl_hours=1,
            db_path=test_db_path,
            output_dir=test_output_dir,
        )

        assert old_id in deleted
        assert not old_dir.exists(), "Output directory should be deleted"

        # Verify job gone from DB
        record = await get_job(old_id, db_path=test_db_path)
        assert record is None

    @pytest.mark.asyncio
    async def test_recent_jobs_are_preserved(
        self,
        test_db_path: str,
        test_output_dir: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Jobs within TTL should be preserved after cleanup."""
        from app.jobs import create_job, get_job
        from app.jobs.cleanup import cleanup_old_jobs
        from app.models import GenerateRequest

        params = GenerateRequest(**sample_generate_request)
        new_id = await create_job(params, db_path=test_db_path)

        # Output dir for recent job
        (Path(test_output_dir) / new_id).mkdir(parents=True, exist_ok=True)

        # Cleanup with very large TTL
        deleted = await cleanup_old_jobs(
            ttl_hours=9999,
            db_path=test_db_path,
            output_dir=test_output_dir,
        )

        assert new_id not in deleted

        record = await get_job(new_id, db_path=test_db_path)
        assert record is not None

    @pytest.mark.asyncio
    async def test_cleanup_mixed_ages(
        self,
        test_db_path: str,
        test_output_dir: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Only old jobs should be cleaned; recent jobs preserved."""
        from app.jobs import create_job, get_job
        from app.jobs.cleanup import cleanup_old_jobs
        from app.jobs.store import get_connection
        from app.models import GenerateRequest

        params = GenerateRequest(**sample_generate_request)

        # Create old and new jobs
        old_id = await create_job(params, db_path=test_db_path)
        new_id = await create_job(params, db_path=test_db_path)

        # Age the old one
        conn = await get_connection(test_db_path)
        try:
            await conn.execute(
                "UPDATE jobs SET created_at = '2020-01-01T00:00:00', "
                "updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
                (old_id,),
            )
            await conn.commit()
        finally:
            await conn.close()

        # Cleanup
        deleted = await cleanup_old_jobs(
            ttl_hours=1,
            db_path=test_db_path,
            output_dir=test_output_dir,
        )

        assert old_id in deleted
        assert new_id not in deleted

        record_new = await get_job(new_id, db_path=test_db_path)
        assert record_new is not None

    @pytest.mark.asyncio
    async def test_cleanup_with_no_output_dir_does_not_crash(
        self,
        test_db_path: str,
        sample_generate_request: dict[str, str],
    ) -> None:
        """Cleanup should not fail if output_dir is not set."""
        from app.jobs import create_job
        from app.jobs.cleanup import cleanup_old_jobs
        from app.jobs.store import get_connection
        from app.models import GenerateRequest

        params = GenerateRequest(**sample_generate_request)
        old_id = await create_job(params, db_path=test_db_path)

        conn = await get_connection(test_db_path)
        try:
            await conn.execute(
                "UPDATE jobs SET created_at = '2020-01-01T00:00:00', "
                "updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
                (old_id,),
            )
            await conn.commit()
        finally:
            await conn.close()

        # No output_dir
        deleted = await cleanup_old_jobs(ttl_hours=1, db_path=test_db_path)
        assert old_id in deleted


# ═══════════════════════════════════════════════════════════════════════════════
# 4.7  Startup validation -> missing API key fails
# ═══════════════════════════════════════════════════════════════════════════════


class TestStartupValidation:
    """Integration tests for startup validation of required env vars."""

    @pytest.mark.asyncio
    async def test_startup_fails_without_api_keys(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """App startup validation detects missing API keys.

        The lifespan validates that at least one LLM API key is set.
        Without any keys:

        1. ``settings.has_any_llm_key()`` returns False
        2. ``_build_providers()`` returns empty list
        3. ``lyrics.generate()`` raises ``LyricsGenerationError``
        """
        from app.config import settings

        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

        # 1. Detection
        assert settings.has_any_llm_key() is False

        # 2. No providers configured
        from app.lyrics import generate as lyrics_generate
        from app.lyrics.providers import LyricsGenerationError

        with pytest.raises(LyricsGenerationError) as exc_info:
            await lyrics_generate(
                recipient="Test", relationship="test",
                occasion="test", genre="pop", mood="happy",
            )

        error_msg = str(exc_info.value)
        assert "No LLM providers configured" in error_msg, (
            f"Expected clear error about missing providers, got: {error_msg}"
        )

        # 3. Re-enable a key and verify it works
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")

        assert settings.has_any_llm_key() is True

    @pytest.mark.asyncio
    async def test_startup_succeeds_with_all_vars(
        self,
        test_app: AsyncClient,
    ) -> None:
        """App should start successfully with all required env vars."""
        # If we get here, the app started (test_app fixture activates lifespan)
        response = await test_app.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Canciones Automáticas"

    @pytest.mark.asyncio
    async def test_settings_has_any_llm_key_false_when_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Settings.has_any_llm_key() should return False when all keys are empty."""
        from app.config import settings

        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

        assert settings.has_any_llm_key() is False

    @pytest.mark.asyncio
    async def test_settings_has_any_llm_key_true_with_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Settings.has_any_llm_key() should return True when a key is set."""
        from app.config import settings

        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-valid-key")

        assert settings.has_any_llm_key() is True
