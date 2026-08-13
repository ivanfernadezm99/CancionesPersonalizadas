# Delta for Job Orchestration

## MODIFIED Requirements

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

When a job fails due to Suno's artist rejection, the `error` field MUST contain the friendly Spanish translation produced by the provider — never the raw English Suno message.
(Previously: the raw English Suno rejection was persisted in `error` and surfaced to the frontend.)

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

#### Scenario: Artist-rejection failure surfaces translated error

- GIVEN a job that failed because Suno rejected an artist name
- WHEN GET /api/status/{job_id} is called
- THEN the `error` MUST equal the friendly Spanish artist message
- AND the `error` MUST NOT contain raw English Suno text

### RQ-JOB-06: Error Handling and Retries

The system SHOULD retry transient failures. Retry policy:

| Failure Type | Max Retries | Backoff |
|--------------|-------------|---------|
| LLM provider timeout | 1 | Immediate (different provider) |
| OpenClaw gateway 5xx | 2 | Linear 10s |
| Download URL 5xx | 3 | Exponential 2s, 4s, 8s |
| LLM malformed response | 1 | Immediate (different provider) |

A Suno artist-rejection (business error, code=400) MUST be treated as non-retryable: the job MUST fail immediately with the translated Spanish message.
(Previously: the raw English Suno rejection was persisted as the job failure error.)

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

#### Scenario: Suno artist rejection is non-retryable and translated

- GIVEN `SunoProvider._invoke` raises the translated artist message
- WHEN the worker handles the failure
- THEN the job MUST be marked "failed" without retry
- AND the job `error` MUST be the friendly Spanish message

### RQ-JOB-08: Reference Song Style on Legacy Endpoint

The legacy `POST /api/generate` (RQ-JOB-01) and `job_worker` MUST accept and propagate optional reference-style fields into the lyrics and voice/music prompts, mirroring the project flow.

| Req | Description | Priority |
|-----|-------------|----------|
| RQ-RS-01 | `GenerateRequest` (`app/models.py`) MUST accept optional `reference_song: str \| None` (max 200) and `reference_description: str \| None` (max 1000), both default `None`, matching `SongProjectCreate` constraints. | MUST |
| RQ-RS-02 | `job_worker` MUST propagate `request.reference_song` to `lyrics_generate(...)` so the lyrics prompt includes the reference, only when `reference_description` is `None`. | MUST |
| RQ-RS-03 | `job_worker` MUST propagate `request.reference_description` to `build_prompt(...)` (voice/music), prioritizing it over `reference_song` (matches `app/projects/__init__.py` behavior). | MUST |
| RQ-RS-04 | On completion, `job.metadata` MUST persist both `reference_song` and `reference_description` (as provided, or `None`) for auditability. | MUST |
| RQ-RS-05 | Legacy requests with both fields `None` MUST behave identically to before (optional fields, `None` default — backward compatible). | MUST |
| RQ-RS-06 | BOTH `project_worker` and `job_worker` MUST pass `reference_song` through the shared tag sanitizer before it reaches `lyrics_generate` and `build_prompt`, so both paths handle the reference identically (legacy `"Song - Artist"` values stripped; artist-only values produce no reference). | MUST |

(Previously: `project_worker` passed the raw `reference_song` to lyrics even when `reference_description` was present, while `job_worker` used `reference_description or reference_song` — the two paths diverged.)

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

#### Scenario: Consistent sanitization across both worker paths

- GIVEN a project flow (`project_worker`) and a legacy flow (`job_worker`) both carrying `reference_song="Bachata Rosa - Juan Luis Guerra"`
- WHEN each worker runs the pipeline
- THEN both workers MUST pass the sanitized `"Bachata Rosa"` to `lyrics_generate` and `build_prompt`
- AND the lyrics and voice prompts in both paths MUST contain `"Bachata Rosa"` with no artist token
