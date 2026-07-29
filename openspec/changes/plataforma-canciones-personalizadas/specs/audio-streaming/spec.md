# Delta for Audio Streaming

## ADDED Requirements

### RQ-STR-05: Preview Parameter

The system MUST support `?preview=true` query parameter on `GET /api/stream/{job_id}`. When `preview=true`, the endpoint MUST return the first 30 seconds of audio. When omitted or `false`, full song streaming MUST require the project to be `paid`.

#### Scenario: Preview always allowed

- GIVEN a completed job for an unpaid project
- WHEN GET /api/stream/{job_id}?preview=true
- THEN response MUST be 200 with `audio/mpeg`
- AND the audio MUST be truncated to 30s
- AND `X-Freemium-Preview: true` header MUST be present

#### Scenario: Full song requires payment

- GIVEN a completed job for a project with status `preview_ready`
- WHEN GET /api/stream/{job_id} (without preview=true)
- THEN response MUST be 402 (Payment Required)
- AND body MUST include `{"detail": "Full song requires payment"}`

#### Scenario: Full song served after payment

- GIVEN a completed job for a project with status `paid`
- WHEN GET /api/stream/{job_id} (without preview=true)
- THEN response MUST be 200 with `audio/mpeg`
- AND the audio MUST be the full song

## MODIFIED Requirements

### RQ-STR-03: Freemium Preview Restriction

The system MUST restrict full audio to paid projects. The `/api/stream/{job_id}?preview=true` endpoint MUST serve a 30s clip without payment. The `/api/stream/{job_id}` (no param) endpoint MUST verify project payment status before serving the full file.
(Previously: all streaming was free, full download deferred to v1)

#### Scenario: Preview header for unpaid project

- GIVEN a completed job for an unpaid project
- WHEN GET /api/stream/{job_id}?preview=true
- THEN `X-Freemium-Preview: true` header MUST be present
- AND audio duration MUST be <= 30s

#### Scenario: Full stream header for paid project

- GIVEN a completed job for a paid project
- WHEN GET /api/stream/{job_id}
- THEN `X-Job-Status: complete` header MUST be present
- AND `X-Paid-Content: true` header MUST be present

## REMOVED Requirements

### RQ-STR-03 (Preview Restriction — original)

(Reason: Replaced by RQ-STR-03 above. The old restriction prevented ALL full downloads; the new one allows paid full downloads.)
(Migration: Update any tests that assert all streaming is free — they must now expect 402 for unpaid full requests.)

