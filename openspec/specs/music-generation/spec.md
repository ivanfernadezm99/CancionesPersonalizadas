# Music Generation Specification

## Purpose

Generate MP3 audio from structured Spanish lyrics using Google Lyria 3 via the OpenClaw gateway. Handle async generation polling, audio post-processing for duration extension, and provide output files for streaming and download.

## Requirements

### RQ-MUS-01: OpenClaw Invocation

The system MUST invoke the OpenClaw `music_generate` tool via `POST http://localhost:18789/tools/invoke` with Bearer token authentication.

**Request payload:**

```json
{
  "tool": "music_generate",
  "args": {
    "prompt": "Genre and mood description in Spanish + English",
    "lyrics": "Full lyrics text with [Verse 1], [Chorus], [Bridge] markers",
    "instrumental": false,
    "model": "google/lyria-3-clip-preview",
    "format": "mp3"
  }
}
```

#### Scenario: Successful invocation

- GIVEN a valid lyrics string and style prompt
- WHEN the system calls `POST /tools/invoke`
- THEN the response MUST have `ok: true`
- AND the response MUST contain a `taskId` in the result
- AND the initial status MUST be "started"

#### Scenario: OpenClaw gateway unreachable

- GIVEN the OpenClaw gateway is down (port 18789 refuses connection)
- WHEN the system attempts to invoke music_generate
- THEN it MUST return a 502 error
- AND the job status MUST be set to "failed" with a clear gateway error message

#### Scenario: Invalid auth token

- GIVEN the OpenClaw token is invalid or expired
- WHEN the system calls the gateway
- THEN it MUST return a 502 error
- AND the system SHOULD log the auth failure for operator attention

### RQ-MUS-02: Async Polling

The system MUST poll for task completion after receiving a taskId, using the OpenClaw task status API. Polling interval SHOULD be 5 seconds with exponential backoff cap at 30 seconds.

Typical generation time: 30 seconds to 3 minutes.

#### Scenario: Normal completion

- GIVEN a taskId from a successful invocation
- WHEN the system polls every 5 seconds
- THEN within 180 seconds the status MUST become "completed"
- AND the result MUST contain a download URL for the MP3

#### Scenario: Generation timeout

- GIVEN a task that does not complete within 300 seconds (5 minutes)
- WHEN the polling loop reaches the timeout limit
- THEN the job MUST be marked as "failed"
- AND the error MUST say "music generation timed out after 300s"

#### Scenario: Task status returns error

- GIVEN a task whose status becomes "failed" during generation
- WHEN the system polls and receives a failed status
- THEN the job MUST be marked as "failed" immediately
- AND the error details from OpenClaw MUST be preserved

### RQ-MUS-03: Duration Extension

The system SHOULD extend generated audio to achieve 2-3 minutes total duration, since Lyria 3 typically produces 30-90 seconds.

Extension techniques (in priority order):
1. **Smart loop**: Crossfade-loop the segment for natural-sounding extension
2. **Stitch**: Generate multiple short segments and crossfade them
3. **Simple loop**: Append a looped version with fade-out
4. **Fallback**: Return shorter audio with a duration metadata header

#### Scenario: Smart loop produces target duration

- GIVEN a 60-second generated MP3
- WHEN the duration extension runs with target 150 seconds
- THEN the output MUST be between 120-180 seconds
- AND the audio MUST not have audible glitches at loop points
- AND the crossfade SHOULD be between 1-3 seconds

#### Scenario: Generation too short for quality extension

- GIVEN a 15-second generated MP3 (minimum viable)
- WHEN the duration extension runs
- THEN it MUST still attempt extension
- BUT if quality check fails (detectable artifacts), return the original with a `duration_extended: false` metadata flag

#### Scenario: pydub/ffmpeg not available

- GIVEN pydub cannot find ffmpeg installation
- WHEN the system attempts duration extension
- THEN it MUST log a warning
- AND return the generated audio at its original length
- AND set a metadata flag `duration_extended: false`

### RQ-MUS-04: Output Storage

The system MUST store the final MP3 file at a deterministic path keyed by job ID:

`{output_dir}/{job_id}/final.mp3`

The output directory MUST be configurable via `OUTPUT_DIR` environment variable (default: `./output/`).

#### Scenario: File storage success

- GIVEN a completed music generation with successful extension
- WHEN the output is written to disk
- THEN the file MUST exist at `{output_dir}/{job_id}/final.mp3`
- AND the file MUST be valid MP3 format (header check)
- AND the file MUST NOT be empty (> 1KB)

#### Scenario: Disk full or write error

- GIVEN the output directory is not writable or disk is full
- WHEN the system attempts to write the MP3
- THEN the job MUST be marked as "failed"
- AND the error MUST indicate a storage failure

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| OpenClaw returns taskId but status is unconfirmed for 30s | Continue polling — normal for Lyria 3 cold start |
| Lyria 3 produces instrumental-only (no lyrics sung) | Accept as-is; flag in job metadata |
| Generated MP3 duration > 180s naturally | Skip extension, use as-is |
| Gateway restart during generation | Job fails; user retries via POST /api/generate |
| Multiple concurrent OpenClaw invocations | Serialize via job queue — one generation at a time |
| OpenClaw returns 200 but malformed task response | Retry call once; if persists, fail job |
| Download URL from OpenClaw times out (HTTP 5xx) | Retry download up to 3 times with 2s backoff |

## Dependencies

- **External**: OpenClaw gateway at `http://localhost:18789` with valid Bearer token
- **External**: Google Lyria 3 model accessible via `google/lyria-3-clip-preview`
- **External**: ffmpeg installed on system (for pydub duration extension)
- **Internal**: `lyrics-generation` — provides the lyrics text
- **Internal**: `voice-configuration` — provides voice type for prompt construction
- **Internal**: `job-orchestration` — manages the async lifecycle
- **Internal**: `audio-streaming` — consumes the output MP3

## Acceptance Criteria

- [ ] OpenClaw `music_generate` invoked correctly with all required args
- [ ] Async polling completes within 5 minutes
- [ ] `final.mp3` stored at correct path and valid MP3 format
- [ ] Duration extension produces 120-180s output
- [ ] Gateway downtime returns clear 502 error
- [ ] Timeout scenarios handled with proper error messages
- [ ] Output directory configurable via env var
