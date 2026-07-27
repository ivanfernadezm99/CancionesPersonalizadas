"""SQLite connection manager and schema initialization."""

from __future__ import annotations

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued','lyrics_generating','music_generating',
                                     'processing','complete','failed')),
    params          TEXT NOT NULL,
    progress        REAL NOT NULL DEFAULT 0.0,
    estimated_remaining INTEGER DEFAULT 180,
    error           TEXT,
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS job_transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_transitions_job ON job_transitions(job_id);
"""


async def get_connection(db_path: str) -> aiosqlite.Connection:
    """Create and return an aiosqlite connection with WAL mode enabled."""
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db(conn: aiosqlite.Connection) -> None:
    """Initialize the database schema (tables, indexes). Idempotent."""
    await conn.executescript(SCHEMA_SQL)
    await conn.commit()
