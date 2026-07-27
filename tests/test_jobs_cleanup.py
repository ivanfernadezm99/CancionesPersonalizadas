"""Tests for app/jobs/cleanup.py — TTL-based job cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import GenerateRequest
from app.jobs import create_job
from app.jobs.cleanup import cleanup_old_jobs, start_cleanup_scheduler


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


@pytest.mark.asyncio
async def test_cleanup_removes_old_jobs(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Jobs older than TTL should be deleted."""
    job_id = await create_job(sample_request, db_path=db_path)
    output_dir = make_output_dir(tmp_path, job_id)

    # Set the job's created_at to be very old
    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (job_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    # Run cleanup with 1 hour TTL
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

    # Run cleanup with large TTL
    deleted = await cleanup_old_jobs(ttl_hours=9999, db_path=db_path)
    assert job_id not in deleted

    # Verify job still exists
    from app.jobs import get_job
    record = await get_job(job_id, db_path=db_path)
    assert record is not None


@pytest.mark.asyncio
async def test_cleanup_no_jobs(db_path: str) -> None:
    """Cleanup with no jobs should return empty list."""
    deleted = await cleanup_old_jobs(db_path=db_path)
    assert deleted == []


@pytest.mark.asyncio
async def test_cleanup_mixed_ages(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Only old jobs should be cleaned, recent ones preserved."""
    old_id = await create_job(sample_request, db_path=db_path)
    new_id = await create_job(sample_request, db_path=db_path)

    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        # Make old_id very old
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (old_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

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

    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (job_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    await cleanup_old_jobs(ttl_hours=1, output_dir=str(tmp_path / "output"), db_path=db_path)
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_cleanup_output_directory_missing(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Cleanup should not fail if output directory is missing."""
    job_id = await create_job(sample_request, db_path=db_path)

    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (job_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    # No output dir created — should not crash
    deleted = await cleanup_old_jobs(ttl_hours=1, output_dir=str(tmp_path / "output"), db_path=db_path)
    assert job_id in deleted


@pytest.mark.asyncio
async def test_cleanup_custom_ttl(
    db_path: str, sample_request: GenerateRequest, tmp_path: Path,
) -> None:
    """Custom TTL should be respected."""
    import aiosqlite
    from app.jobs.store import get_connection

    # Create a job 2 hours ago
    job_id = await create_job(sample_request, db_path=db_path)
    conn = await get_connection(db_path)
    try:
        # Set created_at to 2 hours ago
        from datetime import datetime, timezone, timedelta
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

    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (job_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    # Second run — should be no-op
    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert deleted == []


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_starts_and_cancels(
    db_path: str, sample_request: GenerateRequest,
) -> None:
    """start_cleanup_scheduler() should create a cancellable task."""
    import asyncio

    job_id = await create_job(sample_request, db_path=db_path)
    import aiosqlite
    from app.jobs.store import get_connection
    conn = await get_connection(db_path)
    try:
        await conn.execute(
            "UPDATE jobs SET created_at = '2020-01-01T00:00:00', updated_at = '2020-01-01T00:00:00' WHERE job_id = ?",
            (job_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    # Start scheduler with very short interval for testing
    task, stop_event = start_cleanup_scheduler(
        interval_seconds=1,
        ttl_hours=1,
        db_path=db_path,
    )

    # Let it run a cycle
    await asyncio.sleep(1.5)

    # Cancel via task.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Job should have been cleaned by the scheduler run
    deleted = await cleanup_old_jobs(ttl_hours=1, db_path=db_path)
    assert job_id not in deleted  # already cleaned
