# Job Orchestration Specification

## Purpose

Manage the lifecycle of song generation as asynchronous background jobs. Accept generation requests, orchestrate the lyrics → music pipeline, persist job state in SQLite, and expose status polling. Handle errors, retries, and job cleanup.

## Requirements

### RQ-JOB-01: Generate Endpoint

The system MUST expose `POST /api/generate` that accepts generation parameters and returns a job ID immediately. The request body MAY include optional `reference_song` and `reference_description` fields.

**Request body:**

```json
{
  "recipient": "María",
  "relationship": "pareja",
  "occasion": "aniversario",
  "genre": "bachata",
  "mood": "romántica",
  "story": "Nuestro primer viaje juntos... (optional)",
  "voice": "female",
  "reference_song": "Coldplay - Yellow (optional, max 200 chars)",
  "reference_description": "Uplifting pop with warm piano (optional, max 1000 chars)"
}
```

**Response (202 Accepted):**

```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "estimated_total_seconds": 180,
  "endpoints": {
    "status": "/api/status/{job_id}",
    "stream": "/api/stream/{job_id}"
  }
}
```

#### Scenario: Successful job creation

- GIVEN valid generation parameters
- WHEN a POST request is sent to /api/generate
- THEN the response status MUST be 202
- AND the response MUST include a `job_id` (UUID v4)
- AND the initial status MUST be "queued"
- AND the response MUST include status and stream endpoint URLs

#### Scenario: Invalid input validation

- GIVEN missing required field "recipient"
- WHEN a POST request is sent to /api/generate
- THEN the response status MUST be 422
- AND the error details MUST indicate which field is missing

#### Scenario: System overload prevention

- GIVEN more than 5 jobs in "queued" or "processing" state
- WHEN a new POST /api/generate is received
- THEN the system MAY return 429 (Too Many Requests)
- AND the response MUST include a Retry-After header

### RQ-JOB-08: Reference Song Style on Legacy Endpoint

The legacy `POST /api/generate` (RQ-JOB-01) and `job_worker` MUST accept and propagate optional reference-style fields into the lyrics and voice/music prompts, mirroring the project flow.

| Req | Description | Priority |
|-----|-------------|----------|
| RQ-RS-01 | `GenerateRequest` (`app/models.py`) MUST accept optional `reference_song: str \| None` (max 200) and `reference_description: str \| None` (max 1000), both default `None`, matching `SongProjectCreate` constraints. | MUST |
| RQ-RS-02 | `job_worker` MUST propagate `request.reference_song` to `lyrics_generate(...)` so the lyrics prompt includes the reference, only when `reference_description` is `None`. | MUST |
| RQ-RS-03 | `job_worker` MUST propagate `request.reference_description` to `build_prompt(...)` (voice/music), prioritizing it over `reference_song` (matches `app/projects/__init__.py` behavior). | MUST |
| RQ-RS-04 | On completion, `job.metadata` MUST persist both `reference_song` and `reference_description` (as provided, or `None`) for auditability. | MUST |
| RQ-RS-05 | Legacy requests with both fields `None` MUST behave identically to before (optional fields, `None` default — backward compatible). | MUST |

#### Scenario: Legacy request with reference_description

- GIVEN a legacy `GenerateRequest` with `reference_description="Uplifting pop with warm piano"` and `reference_song=None`
- WHEN `job_worker` runs the pipeline
- THEN `lyrics_generate` and `build_prompt` both receive the `reference_description` value
- AND `job.metadata["reference_description"]` equals that value
- AND `job.metadata["reference_song"]` is `None`

#### Scenario: Legacy request with only reference_song

- GIVEN a legacy `GenerateRequest` with `reference_song="Coldplay - Yellow"` and `reference_description=None`
- WHEN `job_worker` runs the pipeline
- THEN `reference_song` is passed to `lyrics_generate`
- AND `reference_description` is NOT sent to `build_prompt`
- AND `job.metadata["reference_song"]` equals that value
- AND `job.metadata["reference_description"]` is `None`

#### Scenario: Legacy request without reference

- GIVEN a legacy `GenerateRequest` with `reference_song=None` and `reference_description=None`
- WHEN `job_worker` runs the pipeline
- THEN prompts receive no reference (identical behavior to pre-change)
- AND `job.metadata["reference_song"]` is `None`
- AND `job.metadata["reference_description"]` is `None`

### RQ-JOB-02: Status Endpoint

The system MUST expose `GET /api/status/{job_id}` that returns current job state.

**Response:**

```json
{
  "job_id": "uuid",
  "status": "music_generating",
  "progress": 0.6,
  "estimated_remaining_seconds": 45,
  "created_at": "2026-07-27T10:00:00Z",
  "updated_at": "2026-07-27T10:02:30Z",
  "error": null,
  "metadata": {
    "recipient": "María",
    "genre": "bachata",
    "duration_extended": false
  }
}
```

#### Scenario: Status of queued job

- GIVEN a recently created job
- WHEN GET /api/status/{job_id} is called within 2 seconds
- THEN the response MUST show status "queued"
- AND progress MUST be 0.0
- AND estimated_remaining_seconds SHOULD be the default estimate

#### Scenario: Status of completed job

- GIVEN a job that has finished successfully
- WHEN GET /api/status/{job_id} is called
- THEN the status MUST be "complete"
- AND progress MUST be 1.0
- AND estimated_remaining_seconds MUST be 0
- AND error MUST be null

#### Scenario: Status of failed job with error

- GIVEN a job that failed during music generation
- WHEN GET /api/status/{job_id} is called
- THEN the status MUST be "failed"
- AND error MUST be a non-empty string describing the failure
- AND progress MUST reflect the last completed step

#### Scenario: Non-existent job status

- GIVEN a random UUID that does not exist
- WHEN GET /api/status/{job_id} is called
- THEN the response MUST be 404
- AND the body MUST indicate the job was not found

### RQ-JOB-03: Status State Machine

The job status MUST follow a strict state machine:

```
queued → lyrics_generating → music_generating → processing → complete
                                                      ↓
                                                    failed
```

Each status transition MUST be recorded in the SQLite store with a timestamp.

#### Scenario: Full happy path lifecycle

- GIVEN valid generation parameters
- WHEN the job progresses through the full pipeline
- THEN the status transitions MUST be: queued → lyrics_generating → music_generating → processing → complete
- AND each transition MUST have a timestamp recorded in SQLite

#### Scenario: Failure during pipeline

- GIVEN lyrics generation fails (all LLM providers unreachable)
- WHEN the pipeline processes the job
- THEN the status MUST transition to "failed"
- AND the error message MUST be specific: "All LLM providers unavailable"

#### Scenario: Status cannot go backwards

- GIVEN a job at status "music_generating"
- WHEN the system attempts to set status to "queued"
- THEN the system MUST raise an error
- AND the status MUST remain "music_generating"

### RQ-JOB-04: SQLite Persistence

The system MUST persist job state in a SQLite database at a configurable path (`JOB_DB_PATH` env var, default `./data/jobs.db`).

**Schema (minimum):**

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'queued',
  params JSON NOT NULL,
  progress REAL DEFAULT 0.0,
  estimated_remaining INTEGER DEFAULT 180,
  error TEXT,
  metadata JSON DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE job_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
```

**Schema additions (for project-backed jobs):**

```sql
CREATE TABLE IF NOT EXISTS project_jobs (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id     TEXT NOT NULL REFERENCES jobs(job_id),
    job_type   TEXT NOT NULL CHECK(job_type IN ('preview', 'final')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, job_id)
);
```

#### Scenario: Job persisted on creation

- GIVEN a successful POST /api/generate
- WHEN the job is created
- THEN a row MUST exist in the `jobs` table with the returned job_id
- AND the status MUST be "queued"
- AND params MUST contain the full request body as JSON

#### Scenario: Status update persisted

- GIVEN a job transitions from "lyrics_generating" to "music_generating"
- WHEN the status update query completes
- THEN the jobs table MUST show the updated status
- AND the job_transitions table MUST have a record of the transition

#### Scenario: Database write failure

- GIVEN the SQLite database file cannot be written (permissions or disk full)
- WHEN the system attempts to write a job
- THEN the POST /api/generate MUST return 500
- AND the system MUST log a database error

#### Scenario: Project job linked

- GIVEN a successful POST /api/projects/{id}/preview
- WHEN the job is created
- THEN a row MUST exist in `jobs` AND in `project_jobs`
- AND the project_jobs row MUST have matching job_type

### RQ-JOB-05: Job Cleanup

The system MUST periodically clean up completed and failed jobs older than a configurable TTL. Default TTL: 24 hours. Cleanup interval: every hour.

#### Scenario: Completed job cleaned after TTL

- GIVEN a job that completed 25 hours ago
- WHEN the cleanup interval runs
- THEN the job MUST be deleted from the SQLite database
- AND the associated MP3 file MUST be deleted from disk

#### Scenario: Job within TTL is preserved

- GIVEN a job that completed 12 hours ago
- WHEN the cleanup interval runs
- THEN the job MUST remain in the database
- AND the MP3 file MUST remain on disk

#### Scenario: TTL configuration override

- GIVEN JOB_TTL_HOURS=48 is set in environment
- WHEN the cleanup runs
- THEN jobs older than 48 hours MUST be cleaned
- AND jobs newer than 48 hours MUST be preserved

### RQ-JOB-06: Error Handling and Retries

The system SHOULD retry transient failures. Retry policy:

| Failure Type | Max Retries | Backoff |
|--------------|-------------|---------|
| LLM provider timeout | 1 | Immediate (different provider) |
| OpenClaw gateway 5xx | 2 | Linear 10s |
| Download URL 5xx | 3 | Exponential 2s, 4s, 8s |
| LLM malformed response | 1 | Immediate (different provider) |

#### Scenario: Transient retry succeeds

- GIVEN an OpenClaw gateway returns 503 on first attempt
- WHEN the retry logic executes after 10 seconds
- THEN the second attempt MUST proceed
- AND the job MUST continue without being marked as failed

#### Scenario: Retry budget exhausted

- GIVEN OpenClaw returns 503 three times
- WHEN the retry budget is exhausted (max 2 retries)
- THEN the job MUST be marked as "failed"
- AND the error MUST reflect "OpenClaw gateway unavailable after 3 attempts"

#### Scenario: Non-retryable error

- GIVEN a 400 Bad Request from OpenClaw (invalid parameters)
- WHEN the error is received
- THEN the system MUST NOT retry
- AND the job MUST immediately be marked as "failed"

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

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| Job ID collision (UUID v4, astronomically unlikely) | Retry with new UUID; log warning |
| Server restart during active job | Job stays in last recorded state; no auto-resume |
| Multiple cleanup cycles on same job | Idempotent — second delete is no-op |
| SQLite WAL mode for concurrent reads | Enable WAL mode at connection |
| Request body > 100KB | Return 413 Payload Too Large |
| Long story field stored in params | SQLite TEXT can handle up to 1GB |
| Negative or zero TTL in config | Default to 24h; log configuration warning |

## Dependencies

- **Internal**: `lyrics-generation` — first pipeline step
- **Internal**: `music-generation` — second pipeline step
- **Internal**: `voice-configuration` — consumed during prompt building
- **Library**: `sqlite3` (stdlib), `uuid` (stdlib), `asyncio` (stdlib)
- **Design**: Background worker pattern to be designed in design phase

## Acceptance Criteria

- [ ] POST /api/generate returns 202 with valid job_id UUID
- [ ] Invalid input returns 422 with specific field errors
- [ ] GET /api/status/{job_id} returns correct status for each lifecycle state
- [ ] All status transitions follow the state machine (no backwards steps)
- [ ] SQLite persistence across server restart
- [ ] Completed jobs deleted after TTL (default 24h)
- [ ] Associated MP3 files deleted on job cleanup
- [ ] Transient errors retried according to policy
- [ ] Retry budget exhaustion marks job as failed with clear message
- [ ] Non-retryable errors immediately mark job as failed
