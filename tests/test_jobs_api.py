"""Tests for app/jobs/__init__.py — public job API."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import GenerateRequest
from app.jobs import create_job, get_job, update_status, count_active_jobs


@pytest.fixture
def sample_request() -> GenerateRequest:
    return GenerateRequest(
        recipient="María",
        relationship="pareja",
        occasion="aniversario",
        genre="bachata",
        mood="romántica",
        voice="female",
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "jobs.db")


@pytest.mark.asyncio
async def test_create_job_returns_string_id(db_path: str, sample_request: GenerateRequest) -> None:
    """create_job() should return a non-empty string job ID."""
    job_id = await create_job(sample_request, db_path=db_path)
    assert isinstance(job_id, str)
    assert len(job_id) > 0


@pytest.mark.asyncio
async def test_create_job_generates_uuid(db_path: str, sample_request: GenerateRequest) -> None:
    """create_job() should return UUID v4 formatted IDs."""
    job_id = await create_job(sample_request, db_path=db_path)
    # UUID v4 format: 8-4-4-4-12 hex digits
    parts = job_id.split("-")
    assert len(parts) == 5
    assert len(parts[0]) == 8
    assert len(parts[1]) == 4
    assert len(parts[2]) == 4
    assert len(parts[3]) == 4
    assert len(parts[4]) == 12
    # All hex
    int(job_id.replace("-", ""), 16)


@pytest.mark.asyncio
async def test_create_job_unique_ids(db_path: str, sample_request: GenerateRequest) -> None:
    """Each create_job() call should return a unique ID."""
    id1 = await create_job(sample_request, db_path=db_path)
    id2 = await create_job(sample_request, db_path=db_path)
    assert id1 != id2


@pytest.mark.asyncio
async def test_get_job_returns_record(db_path: str, sample_request: GenerateRequest) -> None:
    """get_job() should return a JobRecord for an existing job."""
    job_id = await create_job(sample_request, db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record is not None
    assert record["job_id"] == job_id
    assert record["status"] == "queued"
    assert record["progress"] == 0.0


@pytest.mark.asyncio
async def test_get_job_params_json(db_path: str, sample_request: GenerateRequest) -> None:
    """The params field should contain the full request as JSON."""
    job_id = await create_job(sample_request, db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    import json
    params = json.loads(record["params"])
    assert params["recipient"] == "María"
    assert params["relationship"] == "pareja"
    assert params["occasion"] == "aniversario"
    assert params["genre"] == "bachata"
    assert params["mood"] == "romántica"
    assert params["voice"] == "female"


@pytest.mark.asyncio
async def test_get_job_nonexistent_returns_none(db_path: str) -> None:
    """get_job() should return None for non-existent job."""
    record = await get_job("nonexistent-id", db_path=db_path)
    assert record is None


@pytest.mark.asyncio
async def test_create_job_sets_created_at(db_path: str, sample_request: GenerateRequest) -> None:
    """created_at and updated_at should be set to ISO 8601 strings."""
    job_id = await create_job(sample_request, db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["created_at"]  # non-empty
    assert record["updated_at"]  # non-empty
    assert "T" in record["created_at"]  # ISO format
    assert "T" in record["updated_at"]


@pytest.mark.asyncio
async def test_create_job_estimated_remaining(db_path: str, sample_request: GenerateRequest) -> None:
    """Default estimated_remaining should be 180 seconds."""
    job_id = await create_job(sample_request, db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["estimated_remaining"] == 180


@pytest.mark.asyncio
async def test_update_status_transition(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() should change the job status."""
    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "lyrics_generating", db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["status"] == "lyrics_generating"


@pytest.mark.asyncio
async def test_update_status_with_error(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() should store error message when provided."""
    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "failed", error="Something went wrong", db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["status"] == "failed"
    assert record["error"] == "Something went wrong"


@pytest.mark.asyncio
async def test_update_status_with_extra(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() should accept extra keyword arguments for metadata updates."""
    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "lyrics_generating", db_path=db_path)
    await update_status(job_id, "music_generating", progress=0.5, db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["progress"] == 0.5


@pytest.mark.asyncio
async def test_update_status_sets_completed_at(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() to complete or failed should set completed_at."""
    job_id = await create_job(sample_request, db_path=db_path)

    # Complete
    await update_status(job_id, "lyrics_generating", db_path=db_path)
    await update_status(job_id, "music_generating", db_path=db_path)
    await update_status(job_id, "processing", db_path=db_path)
    await update_status(job_id, "complete", db_path=db_path)
    record = await get_job(job_id, db_path=db_path)
    assert record["completed_at"] is not None
    assert "T" in record["completed_at"]

    # Failed
    job_id2 = await create_job(sample_request, db_path=db_path)
    await update_status(job_id2, "lyrics_generating", db_path=db_path)
    await update_status(job_id2, "failed", error="test error", db_path=db_path)
    record2 = await get_job(job_id2, db_path=db_path)
    assert record2["completed_at"] is not None


@pytest.mark.asyncio
async def test_update_status_records_transition(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() should insert a row in job_transitions."""
    import aiosqlite
    from app.jobs.store import get_connection, init_db

    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "lyrics_generating", db_path=db_path)

    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        cursor = await conn.execute(
            "SELECT from_status, to_status, error FROM job_transitions WHERE job_id = ? ORDER BY id",
            (job_id,),
        )
        rows = await cursor.fetchall()

        # First row: queued → lyrics_generating
        assert len(rows) >= 1
        # The transition for queued→lyrics_generating
        row = rows[-1]  # last transition
        assert row["from_status"] == "queued"
        assert row["to_status"] == "lyrics_generating"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_status_invalid_transition_raises(db_path: str, sample_request: GenerateRequest) -> None:
    """update_status() should raise on invalid transitions."""
    from app.jobs.state import InvalidTransitionError

    job_id = await create_job(sample_request, db_path=db_path)
    with pytest.raises(InvalidTransitionError):
        await update_status(job_id, "complete", db_path=db_path)  # skip stages


@pytest.mark.asyncio
async def test_count_active_jobs_zero(db_path: str) -> None:
    """count_active_jobs() should return 0 when no jobs exist."""
    count = await count_active_jobs(db_path=db_path)
    assert count == 0


@pytest.mark.asyncio
async def test_count_active_jobs_includes_queued(db_path: str, sample_request: GenerateRequest) -> None:
    """count_active_jobs() should count queued jobs as active."""
    await create_job(sample_request, db_path=db_path)
    count = await count_active_jobs(db_path=db_path)
    assert count == 1


@pytest.mark.asyncio
async def test_count_active_jobs_excludes_complete(db_path: str, sample_request: GenerateRequest) -> None:
    """count_active_jobs() should not count complete jobs."""
    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "lyrics_generating", db_path=db_path)
    await update_status(job_id, "music_generating", db_path=db_path)
    await update_status(job_id, "processing", db_path=db_path)
    await update_status(job_id, "complete", db_path=db_path)
    count = await count_active_jobs(db_path=db_path)
    assert count == 0


@pytest.mark.asyncio
async def test_count_active_jobs_excludes_failed(db_path: str, sample_request: GenerateRequest) -> None:
    """count_active_jobs() should not count failed jobs."""
    job_id = await create_job(sample_request, db_path=db_path)
    await update_status(job_id, "failed", error="failed", db_path=db_path)
    count = await count_active_jobs(db_path=db_path)
    assert count == 0


@pytest.mark.asyncio
async def test_count_active_jobs_multiple(db_path: str, sample_request: GenerateRequest) -> None:
    """count_active_jobs() should count all non-terminal jobs."""
    await create_job(sample_request, db_path=db_path)
    await create_job(sample_request, db_path=db_path)
    j3 = await create_job(sample_request, db_path=db_path)
    await update_status(j3, "lyrics_generating", db_path=db_path)
    count = await count_active_jobs(db_path=db_path)
    assert count == 3
