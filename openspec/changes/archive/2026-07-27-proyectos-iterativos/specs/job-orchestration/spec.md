# Delta for Job Orchestration

## ADDED Requirements

### RQ-JOB-07: Project-Backed Jobs

Jobs MAY be created through project routes (`/api/projects/{id}/preview`, `/api/projects/{id}/final`). These jobs MUST be linked to the parent project via the `project_jobs` table. The project_id is stored in the link table — not in the jobs table params.

#### Scenario: Preview job linked to project

- GIVEN a project with id "proj-123"
- WHEN POST /api/projects/proj-123/preview creates a job with job_id "job-abc"
- THEN `project_jobs` MUST have a row (proj-123, job-abc, "preview")
- AND `GET /api/status/job-abc` MUST work identically to any other job

#### Scenario: Final job linked to project

- GIVEN a project with id "proj-123"
- WHEN POST /api/projects/proj-123/final creates a job with job_id "job-xyz"
- THEN `project_jobs` MUST have a row (proj-123, job-xyz, "final")
- AND status polling and streaming MUST work for this job

#### Scenario: Existing generate endpoint unchanged

- GIVEN a project exists
- WHEN POST /api/generate is called directly (not through project routes)
- THEN it MUST NOT create any project_jobs rows
- AND it MUST behave exactly as before this change

## MODIFIED Requirements

### RQ-JOB-04: SQLite Persistence

The system MUST persist job state in a SQLite database at a configurable path (`JOB_DB_PATH` env var, default `./data/jobs.db`).

**Schema additions:**

```sql
CREATE TABLE IF NOT EXISTS project_jobs (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id     TEXT NOT NULL REFERENCES jobs(job_id),
    job_type   TEXT NOT NULL CHECK(job_type IN ('preview', 'final')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, job_id)
);
```
(Previously: single jobs + job_transitions tables, no project_jobs table)

#### Scenario: Job persisted on creation (unchanged)

- GIVEN a successful POST /api/generate
- WHEN the job is created
- THEN a row MUST exist in the `jobs` table with the returned job_id
- AND the status MUST be "queued"

#### Scenario: Project job linked (new)

- GIVEN a successful POST /api/projects/{id}/preview
- WHEN the job is created
- THEN a row MUST exist in `jobs` AND in `project_jobs`
- AND the project_jobs row MUST have matching job_type
