"""Tests for app/jobs/store.py — SQLite connection manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs.store import get_connection, init_db


@pytest.mark.asyncio
async def test_get_connection_returns_aiosqlite_connection(tmp_path: Path) -> None:
    """get_connection() should return an aiosqlite Connection."""
    db_path = str(tmp_path / "test.db")
    conn = await get_connection(db_path)
    try:
        # The connection should be usable
        cursor = await conn.execute("SELECT 1")
        row = await cursor.fetchone()
        assert row[0] == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_connection_enables_wal_mode(tmp_path: Path) -> None:
    """get_connection() should enable WAL journal mode."""
    db_path = str(tmp_path / "test_wal.db")
    conn = await get_connection(db_path)
    try:
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].upper() == "WAL", f"Expected WAL, got {row[0]}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_creates_tables(tmp_path: Path) -> None:
    """init_db() should create the jobs and job_transitions tables."""
    db_path = str(tmp_path / "test_schema.db")
    conn = await get_connection(db_path)
    try:
        await init_db(conn)

        # Check tables exist (exclude sqlite_ internal tables)
        sql = (
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        cursor = await conn.execute(sql)
        tables = [row[0] for row in await cursor.fetchall()]
        assert "jobs" in tables
        assert "job_transitions" in tables
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_creates_indexes(tmp_path: Path) -> None:
    """init_db() should create indexes on status, created_at, and job_id."""
    db_path = str(tmp_path / "test_indexes.db")
    conn = await get_connection(db_path)
    try:
        await init_db(conn)

        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in await cursor.fetchall()}
        assert "idx_jobs_status" in indexes
        assert "idx_jobs_created" in indexes
        assert "idx_transitions_job" in indexes
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_is_idempotent(tmp_path: Path) -> None:
    """init_db() should be safe to call multiple times."""
    db_path = str(tmp_path / "test_idem.db")
    conn = await get_connection(db_path)
    try:
        await init_db(conn)
        # Call again — should not raise
        await init_db(conn)

        sql = (
            "SELECT COUNT(*) FROM sqlite_master"
            " WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        cursor = await conn.execute(sql)
        count = (await cursor.fetchone())[0]
        assert count == 2  # jobs + job_transitions
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_db_schema_columns(tmp_path: Path) -> None:
    """Verify the jobs table has the expected schema."""
    db_path = str(tmp_path / "test_cols.db")
    conn = await get_connection(db_path)
    try:
        await init_db(conn)

        cursor = await conn.execute("PRAGMA table_info(jobs)")
        columns = {row[1] for row in await cursor.fetchall()}
        expected = {
            "job_id", "status", "params", "progress",
            "estimated_remaining", "error", "metadata",
            "created_at", "updated_at", "completed_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        cursor = await conn.execute("PRAGMA table_info(job_transitions)")
        columns = {row[1] for row in await cursor.fetchall()}
        expected = {"id", "job_id", "from_status", "to_status", "timestamp", "error"}
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"
    finally:
        await conn.close()
