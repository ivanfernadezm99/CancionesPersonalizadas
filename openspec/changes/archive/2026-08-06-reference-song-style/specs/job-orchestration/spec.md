# Delta for job-orchestration

## MODIFIED Requirements

### RQ-JOB-01: Generate Endpoint

The system MUST expose `POST /api/generate` that accepts generation parameters and returns a job ID immediately. The request body MAY include optional `reference_song` and `reference_description` fields.
(Previously: request body had no reference-style fields.)

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

## Requirements

| Req | Description | Priority |
|-----|-------------|----------|
| RQ-RS-01 | `GenerateRequest` (`app/models.py`) MUST accept optional `reference_song: str \| None` (max 200) and `reference_description: str \| None` (max 1000), both default `None`, matching `SongProjectCreate` constraints. | MUST |
| RQ-RS-02 | `job_worker` MUST propagate `request.reference_song` to `lyrics_generate(...)` so the lyrics prompt includes the reference, only when `reference_description` is `None`. | MUST |
| RQ-RS-03 | `job_worker` MUST propagate `request.reference_description` to `build_prompt(...)` (voice/music), prioritizing it over `reference_song` (matches `app/projects/__init__.py` behavior). | MUST |
| RQ-RS-04 | On completion, `job.metadata` MUST persist both `reference_song` and `reference_description` (as provided, or `None`) for auditability. | MUST |
| RQ-RS-05 | Legacy requests with both fields `None` MUST behave identically to before (optional fields, `None` default — backward compatible). | MUST |

## Acceptance Scenarios

File: `tests/jobs/test_worker_reference.py` (TDD, respx + pytest-asyncio).

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

## Capability Impact

- **Modified**: `job-orchestration` — legacy endpoint (RQ-JOB-01) and `job_worker` now accept and propagate `reference_song`/`reference_description` into lyrics and voice/music prompts.

## Backward Compatibility

Both fields are optional with `None` default. Existing in-flight jobs parse without them; `GenerateRequest` contract is backward compatible and requires no data migration. Rolling back is a plain revert of `app/models.py` and `app/jobs/worker.py`.

## Exclusions

- **Frontend** (POSCuentasCorrientes): no UI wiring.
- **Clipchain / Suno cover**: unchanged (already injects `reference_description`; chaining forced-off with Suno).
- **OpenClaw**: does not consume reference audio — text-only injection (provider limitation, untouched).
- **Reference audio upload** on legacy: no `project_id` to store audio; text-only support (`reference_song`/`reference_description`), no `reference_audio_url`.
