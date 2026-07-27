"""Tests for app/jobs/cleanup.py — TTL-based job cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.jobs import create_job, get_job
from app.jobs.cleanup import cleanup_old_jobs, start_cleanup_scheduler
from app.jobs.store import get_connection
from app.models import GenerateRequest

# Common SQL to age a job record
_AGE_SQL = (
    "UPDATE jobs SET created_at = '2020-01-01T00:00:00',"
    " updated_at = '2020-01-01T00:00:00' WHERE job_id = ?"
)


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


def make_output_dir(tmp_path: Path, job_id: str) -> Path:
    """Create a fake output directory for a job."""
    out_dir = tmp_path / "output" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final.mp3").write_text("fake mp3 content")
    return out_dir


async def _age_job(db_path: str, job_id: str) -> None:
    """Set a job's timestamps to be very old."""
    conn = await get_connection(db_path)
    try:
        await conn.execute(_AGE_SQL, (job_id,))
        await conn.commit()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cleanup_removes_old_jobs(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Jobs older than TTL should be deleted."""
    job_id = await create_job(sample_request, db_path=db_path)
    output_dir = make_output_dir(tmp_path, job_id)
    await _age_job(db_path, job_id)

    deleted = await cleanup_old_jobs(
        ttl_hours=1, db_path=db_path, output_dir=str(tmp_path / "output"),
    )
    assert job_id in deleted
    assert not output_dir.exists(), "Output directory should be deleted"


@pytest.mark.asyncio
async def test_cleanup_preserves_recent_jobs(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Jobs within TTL should be preserved."""
    job_id = await create_job(sample_request, db_path=db_path)
    make_output_dir(tmp_path, job_id)

    deleted = await cleanup_old_jobs(ttl_hours=9999, db_path=db_path)
    assert job_id not in deleted

    record = await get_job(job_id, db_path=db_path)
    assert record is not None


@pytest.mark.asyncio
async def test_cleanup_no_jobs(db_path: str) -> None:
    """Cleanup with no jobs should return empty list."""
    deleted = await cleanup_old_jobs(db_path=db_path)
    assert deleted == []


@pytest.mark.asyncio
async def test_cleanup_mixed_ages(
    db_path: str, sample_request: GenerateRequest,
) -> None:
    """Only old jobs should be cleaned, recent ones preserved."""
    old_id = await create_job(sample_request, db_path=db_path)
    new_id = await create_job(sample_request, db_path=db_path)

    await _age_job(db_path, old_id)

    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert old_id in deleted
    assert new_id not in deleted


@pytest.mark.asyncio
async def test_cleanup_output_directory(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Output directories for cleaned jobs should be removed."""
    job_id = await create_job(sample_request, db_path=db_path)
    output_dir = make_output_dir(tmp_path, job_id)
    await _age_job(db_path, job_id)

    await cleanup_old_jobs(
        ttl_hours=1, output_dir=str(tmp_path / "output"), db_path=db_path,
    )
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_cleanup_output_directory_missing(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Cleanup should not fail if output directory is missing."""
    job_id = await create_job(sample_request, db_path=db_path)
    await _age_job(db_path, job_id)

    deleted = await cleanup_old_jobs(
        ttl_hours=1, output_dir=str(tmp_path / "output"), db_path=db_path,
    )
    assert job_id in deleted


@pytest.mark.asyncio
async def test_cleanup_custom_ttl(
    db_path: str, sample_request: GenerateRequest,
) -> None:
    """Custom TTL should be respected."""
    # Create a job 2 hours ago
    job_id = await create_job(sample_request, db_path=db_path)
    conn = await get_connection(db_path)
    try:
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await conn.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ? WHERE job_id = ?",
            (two_hours_ago, two_hours_ago, job_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    # TTL of 1 hour should clean this
    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert job_id in deleted

    # Re-create and test TTL of 3 hours should NOT clean
    job_id2 = await create_job(sample_request, db_path=db_path)
    conn2 = await get_connection(db_path)
    try:
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await conn2.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ? WHERE job_id = ?",
            (two_hours_ago, two_hours_ago, job_id2),
        )
        await conn2.commit()
    finally:
        await conn2.close()

    deleted2 = await cleanup_old_jobs(ttl_hours=3, db_path=db_path)
    assert job_id2 not in deleted2


@pytest.mark.asyncio
async def test_cleanup_is_idempotent(
    db_path: str, sample_request: GenerateRequest,
) -> None:
    """Running cleanup twice should not error."""
    job_id = await create_job(sample_request, db_path=db_path)
    await _age_job(db_path, job_id)

    await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert deleted == []


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_starts_and_cancels(
    db_path: str, sample_request: GenerateRequest,
) -> None:
    """start_cleanup_scheduler() should create a cancellable task."""
    import asyncio

    job_id = await create_job(sample_request, db_path=db_path)
    await _age_job(db_path, job_id)

    task, stop_event = start_cleanup_scheduler(
        interval_seconds=1,
        ttl_hours=1,
        db_path=db_path,
    )

    await asyncio.sleep(1.5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert job_id not in deleted
