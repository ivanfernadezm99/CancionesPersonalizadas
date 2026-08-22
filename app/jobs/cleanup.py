"""Periodic TTL-based cleanup of old jobs and their output directories."""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from app.jobs.store import get_connection, init_db

logger = logging.getLogger(__name__)


async def cleanup_old_jobs(
    *,
    ttl_hours: int = 24,
    db_path: str = "jobs.db",
    output_dir: str | None = None,
) -> list[str]:
    """Delete jobs older than ttl_hours and their output directories.

    Returns a list of deleted job IDs.
    """
    now = datetime.utcnow()
    deleted: list[str] = []

    conn = await get_connection(db_path)
    try:
        await init_db(conn)

        # Get all jobs and check age in Python
        cursor = await conn.execute("SELECT job_id, status, created_at FROM jobs")
        all_jobs = await cursor.fetchall()

        for row in all_jobs:
            # Completed jobs are replayable assets (preview/full songs): NEVER
            # delete them nor their files — the songs panel replays them.
            if row["status"] == "complete":
                continue

            job_id = row["job_id"]
            created_at_str = row["created_at"]

            try:
                created_at_str = created_at_str.replace("+00:00", "").replace("Z", "")
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                continue

            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours < ttl_hours:
                continue

            # Delete job (transitions first due to FK), plus its project_jobs
            # link so no orphaned preview rows remain. project_jobs lives in the
            # projects schema — skip it defensively when a jobs-only DB is used
            # (e.g. tests or a fresh standalone instance).
            await conn.execute("DELETE FROM job_transitions WHERE job_id = ?", (job_id,))
            has_project_jobs = await conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_jobs'"
            )
            if await has_project_jobs.fetchone():
                await conn.execute("DELETE FROM project_jobs WHERE job_id = ?", (job_id,))
            await conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            deleted.append(job_id)

            # Remove output directory
            if output_dir:
                job_output = Path(output_dir) / job_id
                if job_output.exists():
                    shutil.rmtree(job_output, ignore_errors=True)

        await conn.commit()
    finally:
        await conn.close()

    if deleted:
        logger.info("Cleaned up %d old jobs: %s", len(deleted), ", ".join(deleted))

    return deleted


def start_cleanup_scheduler(
    *,
    interval_seconds: int = 3600,
    ttl_hours: int = 24,
    db_path: str = "jobs.db",
    output_dir: str | None = None,
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Start the cleanup scheduler as an asyncio task.

    Runs cleanup every `interval_seconds`, respecting `ttl_hours`.
    Returns (task, stop_event). Call stop_event.set() then await task to stop.
    """
    stop_event = asyncio.Event()

    async def _run() -> None:
        while not stop_event.is_set():
            try:
                await cleanup_old_jobs(
                    ttl_hours=ttl_hours,
                    db_path=db_path,
                    output_dir=output_dir,
                )
            except Exception:
                logger.exception("Cleanup cycle failed")

            # Wait for interval or stop signal
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                return  # stop_event was set
            except asyncio.TimeoutError:
                pass  # Normal timeout — run another cycle

    task = asyncio.ensure_future(_run())
    return task, stop_event
