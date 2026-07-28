"""Public job API: create, get, update status, count active jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.jobs.state import JobStateMachine
from app.jobs.store import get_connection, init_db
from app.models import GenerateRequest


async def create_job(
    params: GenerateRequest,
    *,
    db_path: str = "jobs.db",
    initial_metadata: str | None = None,
) -> str:
    """Create a new job in queued status. Returns the job_id (UUID v4).

    Args:
        params: Generation parameters.
        db_path: Path to the SQLite database.
        initial_metadata: Optional JSON string to store as initial metadata.

    Returns:
        The new job's UUID string.
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    metadata_value = initial_metadata or "{}"

    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        await conn.execute(
            """INSERT INTO jobs (job_id, status, params, progress, estimated_remaining,
                                 error, metadata, created_at, updated_at)
               VALUES (?, 'queued', ?, 0.0, 180, NULL, ?, ?, ?)""",
            (job_id, params.model_dump_json(), metadata_value, now, now),
        )
        await conn.commit()
    finally:
        await conn.close()

    return job_id


async def get_job(
    job_id: str,
    *,
    db_path: str = "jobs.db",
) -> dict[str, Any] | None:
    """Retrieve a job record by ID. Returns None if not found."""
    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        cursor = await conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await conn.close()


async def update_status(
    job_id: str,
    new_status: str,
    *,
    error: str | None = None,
    db_path: str = "jobs.db",
    **extra: Any,
) -> None:
    """Update job status with state machine validation.

    Records a transition in job_transitions table.
    Accepts extra keyword args to update other columns (progress, metadata, etc.).
    """
    now = datetime.now(timezone.utc).isoformat()

    conn = await get_connection(db_path)
    try:
        await init_db(conn)

        # Get current status
        cursor = await conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Job {job_id} not found")

        from_status = row["status"]

        # Validate transition
        JobStateMachine.validate(from_status, new_status)

        # Build SET clause
        set_parts = ["status = ?", "updated_at = ?"]
        values: list[Any] = [new_status, now]

        if error is not None:
            set_parts.append("error = ?")
            values.append(error)

        for key, val in extra.items():
            set_parts.append(f"{key} = ?")
            values.append(val)

        # Set completed_at for terminal states
        if new_status in ("complete", "failed"):
            set_parts.append("completed_at = ?")
            values.append(now)

        # Update jobs table
        values.append(job_id)
        await conn.execute(
            f"UPDATE jobs SET {', '.join(set_parts)} WHERE job_id = ?",
            values,
        )

        # Record transition
        await conn.execute(
            """INSERT INTO job_transitions (job_id, from_status, to_status, timestamp, error)
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, from_status, new_status, now, error),
        )

        await conn.commit()
    finally:
        await conn.close()


async def count_active_jobs(
    *,
    db_path: str = "jobs.db",
) -> int:
    """Count jobs that are not in terminal states (complete/failed)."""
    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('complete', 'failed')",
        )
        row = await cursor.fetchone()
        assert row is not None, "COUNT(*) should always return a row"
        return int(row[0])
    finally:
        await conn.close()
