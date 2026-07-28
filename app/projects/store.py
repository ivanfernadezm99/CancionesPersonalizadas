"""SQLite store for song projects, story fragments, and project-job links."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.models import SongProjectCreate, SongProjectUpdate

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    recipient       TEXT NOT NULL,
    relationship    TEXT NOT NULL,
    genre           TEXT NOT NULL DEFAULT 'balada romántica',
    mood            TEXT NOT NULL DEFAULT 'romántico',
    voice           TEXT NOT NULL DEFAULT 'male',
    reference_song  TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK(status IN ('draft', 'complete')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_fragments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fragment        TEXT NOT NULL,
    sort_order      INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_jobs (
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    job_type        TEXT NOT NULL CHECK(job_type IN ('preview', 'final')),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (project_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_fragments_project ON story_fragments(project_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_pj_project ON project_jobs(project_id);
"""


async def _get_conn(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_schema(db_path: str, conn: aiosqlite.Connection | None = None) -> None:
    if conn is not None:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
        return
    conn = await _get_conn(db_path)
    try:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
    finally:
        await conn.close()


async def create_project(data: SongProjectCreate, *, db_path: str) -> str:
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = await _get_conn(db_path)
    try:
        await init_schema(db_path, conn=conn)
        await conn.execute(
            """INSERT INTO projects (id, recipient, relationship, genre, mood, voice,
                                      reference_song, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, data.recipient, data.relationship, data.genre,
             data.mood, data.voice, data.reference_song, now, now),
        )
        await conn.commit()
    finally:
        await conn.close()
    return project_id


async def get_project(project_id: str, *, db_path: str) -> dict[str, Any] | None:
    conn = await _get_conn(db_path)
    try:
        await init_schema(db_path, conn=conn)
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        project = dict(row)

        # Load fragments
        frag_cursor = await conn.execute(
            "SELECT * FROM story_fragments WHERE project_id = ? ORDER BY sort_order",
            (project_id,),
        )
        project["fragments"] = [dict(r) async for r in frag_cursor]

        # Load previews
        pj_cursor = await conn.execute(
            """SELECT pj.job_id, pj.job_type, pj.created_at, j.status
               FROM project_jobs pj
               LEFT JOIN jobs j ON j.job_id = pj.job_id
               WHERE pj.project_id = ?
               ORDER BY pj.created_at DESC""",
            (project_id,),
        )
        project["previews"] = [dict(r) async for r in pj_cursor]

        return project
    finally:
        await conn.close()


async def update_project(
    project_id: str, data: SongProjectUpdate, *, db_path: str,
) -> bool:
    """Update project settings and optionally add a story fragment. Returns True if found."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _get_conn(db_path)
    try:
        await init_schema(db_path, conn=conn)

        # Check exists
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if await cursor.fetchone() is None:
            return False

        # Update scalar fields if provided
        updates: list[str] = []
        params: list[Any] = []
        for field in ("genre", "mood", "voice", "reference_song"):
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(project_id)
            await conn.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        # Add story fragment if provided
        if data.fragment:
            # Get next sort_order
            count_cursor = await conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM story_fragments WHERE project_id = ?",
                (project_id,),
            )
            row = await count_cursor.fetchone()
            next_order = int(row[0]) if row else 1

            await conn.execute(
                """INSERT INTO story_fragments (project_id, fragment, sort_order, created_at)
                   VALUES (?, ?, ?, ?)""",
                (project_id, data.fragment.text, next_order, now),
            )
            # Also bump updated_at
            await conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )

        await conn.commit()
        return True
    finally:
        await conn.close()


async def link_project_job(
    project_id: str, job_id: str, job_type: str, *, db_path: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = await _get_conn(db_path)
    try:
        await init_schema(db_path, conn=conn)
        await conn.execute(
            "INSERT INTO project_jobs (project_id, job_id, job_type, created_at) VALUES (?, ?, ?, ?)",
            (project_id, job_id, job_type, now),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_accumulated_story(project_id: str, *, db_path: str) -> str:
    """Return all story fragments concatenated, newest last."""
    conn = await _get_conn(db_path)
    try:
        await init_schema(db_path, conn=conn)
        cursor = await conn.execute(
            "SELECT fragment FROM story_fragments WHERE project_id = ? ORDER BY sort_order",
            (project_id,),
        )
        fragments = [row["fragment"] async for row in cursor]
        return " ".join(fragments)
    finally:
        await conn.close()
