"""Seed demo preview jobs so the sample songs are streamable.

The `jobs` table is currently empty, so `/api/stream/{job_id}` returns
404 `job_not_found` even though the actual generated MP3s exist under
`output/{job_id}/generated.mp3`. This script inserts two demo rows
(status='complete') and links them to an existing demo project
(`9af8de3c-d2a0-42e8-9070-a252f9c61b8a`, recipient "Brenda") with
`job_type='preview'`, so the project's `previews[]` and the stream
endpoint both resolve.

Design choice: reuse the existing Brenda project instead of creating a
new 'demo' project — it already has fragments and keeps the demo data
self-contained.

The script is idempotent: it uses INSERT OR IGNORE on the primary keys,
so re-running it never duplicates rows.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "jobs.db"

# job_id -> output/{job_id}/generated.mp3 must exist
DEMO_JOB_IDS = (
    "2fedeaee-41e7-46fa-b42a-c2a5740b22f2",
    "8d3ef9158d34e9227eb1849b4808874f",
)

DEMO_PROJECT_ID = "9af8de3c-d2a0-42e8-9070-a252f9c61b8a"


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA journal_mode=WAL")

        inserted_jobs = 0
        for job_id in DEMO_JOB_IDS:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    job_id, status, params, progress, estimated_remaining,
                    error, metadata, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    "complete",
                    "{}",
                    1.0,
                    0,
                    None,
                    "{}",
                    now,
                    now,
                    now,
                ),
            )
            inserted_jobs += cur.rowcount

        cur = con.execute(
            """
            INSERT OR IGNORE INTO project_jobs (project_id, job_id, job_type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (DEMO_PROJECT_ID, DEMO_JOB_IDS[0], "preview", now),
        )
        inserted_jobs += cur.rowcount
        cur = con.execute(
            """
            INSERT OR IGNORE INTO project_jobs (project_id, job_id, job_type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (DEMO_PROJECT_ID, DEMO_JOB_IDS[1], "preview", now),
        )
        inserted_jobs += cur.rowcount

        con.commit()
    finally:
        con.close()

    print(f"Seeded {inserted_jobs} row(s) into {DB_PATH} (0 = already present, nothing changed).")


if __name__ == "__main__":
    main()
