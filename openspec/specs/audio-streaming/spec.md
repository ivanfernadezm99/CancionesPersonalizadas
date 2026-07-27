# Audio Streaming Specification

## Purpose

Provide freemium audio preview of generated songs via a REST streaming endpoint. Users with a job ID can stream the generated MP3 in-browser without downloading the full file. Full download is deferred to v1+ (payment-gated).

## Requirements

### RQ-STR-01: Stream Endpoint

The system MUST expose `GET /api/stream/{job_id}` that returns the generated MP3 as an `audio/mpeg` streaming response.

#### Scenario: Successful stream of completed job

- GIVEN a job with status "completed" and a valid MP3 at `{output_dir}/{job_id}/final.mp3`
- WHEN a GET request is made to `/api/stream/{job_id}`
- THEN the response status MUST be 200
- AND the Content-Type header MUST be `audio/mpeg`
- AND the response body MUST contain valid MP3 binary data
- AND the Content-Length header SHOULD be present

#### Scenario: Stream non-existent job

- GIVEN a job_id that does not exist in the SQLite store
- WHEN a GET request is made to `/api/stream/{job_id}`
- THEN the response status MUST be 404
- AND the response body MUST contain a clear error message

#### Scenario: Stream in-progress job

- GIVEN a job with status "lyrics_generating" or "music_generating"
- WHEN a GET request is made to `/api/stream/{job_id}`
- THEN the response status MUST be 409 (Conflict) or 425 (Too Early)
- AND the response MUST include the current job status in the body
- AND the response SHOULD include a Retry-After header with estimated seconds

#### Scenario: Stream failed job

- GIVEN a job with status "failed"
- WHEN a GET request is made to `/api/stream/{job_id}`
- THEN the response status MUST be 410 (Gone)
- AND the response body MUST include the error reason from the job

### RQ-STR-02: Range Request Support

The system SHOULD support HTTP Range requests for browser-based audio playback seeking. When a Range header is present, the system MUST respond with `206 Partial Content`.

#### Scenario: Range request for specific byte range

- GIVEN a completed job with a 500KB MP3 file
- WHEN a GET request is made with `Range: bytes=0-1023`
- THEN the response status MUST be 206
- AND Content-Range header MUST be `bytes 0-1023/{total_size}`
- AND the response body MUST contain exactly 1024 bytes

#### Scenario: Range request with open-ended range

- GIVEN a completed job
- WHEN a GET request is made with `Range: bytes=1000-`
- THEN the response status MUST be 206
- AND Content-Range MUST be `bytes 1000-{last_byte}/{total_size}`
- AND the body MUST contain all bytes from 1000 to end

#### Scenario: Invalid range request

- GIVEN a completed job with a 500KB MP3
- WHEN a GET request is made with `Range: bytes=999999-9999999` (beyond file size)
- THEN the response status MUST be 416 (Range Not Satisfiable)
- AND Content-Range MUST be `bytes */{total_size}`

### RQ-STR-03: Freemium Preview Restriction

The system MUST NOT allow full file download in v0. The `/api/stream/{job_id}` endpoint is the only way to access generated audio. A dedicated download endpoint is deferred to v1 (payment-gated).

#### Scenario: Direct filesystem access blocked

- GIVEN a completed job
- WHEN a request is made to any path other than `/api/stream/{job_id}`
- THEN the system MUST return 404 for any non-registered paths
- AND the output directory MUST NOT be served as static files

#### Scenario: Stream header metadata

- GIVEN a streaming response for a completed job
- WHEN the response is inspected
- THEN it SHOULD include a `X-Freemium-Preview: true` header
- AND it SHOULD include a `X-Job-Status: complete` header

### RQ-STR-04: Streaming Performance

The system SHOULD use asynchronous file reading to avoid blocking the event loop during stream. Use FastAPI `StreamingResponse` with an async generator.

#### Scenario: Concurrent streams

- GIVEN two simultaneous GET requests to different job stream endpoints
- WHEN both jobs are completed
- THEN both streams MUST serve audio without blocking each other
- AND both responses MUST complete within 2x the single-stream time

#### Scenario: Client disconnects early

- GIVEN a client that starts streaming and disconnects after 5 seconds
- WHEN the client disconnects
- THEN the server MUST clean up the streaming task
- AND MUST NOT continue reading the file for that disconnected client

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| MP3 file deleted before streaming completes | Abort stream with 500 error |
| Job completed but MP3 file missing from disk | Return 410 with "file not found" error |
| Very large file (> 50MB unexpected) | Stream normally; file size check at generation time |
| Browser sends multiple Range requests (seeking) | Support all valid Range headers per HTTP spec |
| Head request to /api/stream/{job_id} | Return 200 with Content-Type and Content-Length (no body) |

## Dependencies

- **Internal**: `job-orchestration` — provides job status and job_id validation
- **Internal**: `music-generation` — produces the MP3 file at `{output_dir}/{job_id}/final.mp3`
- **Library**: FastAPI `StreamingResponse` + `FileResponse` (stdlib)

## Acceptance Criteria

- [ ] GET /api/stream/{job_id} returns 200 with audio/mpeg for completed jobs
- [ ] GET /api/stream/{job_id} returns 404 for non-existent jobs
- [ ] GET /api/stream/{job_id} returns 409 for in-progress jobs
- [ ] GET /api/stream/{job_id} returns 410 for failed jobs
- [ ] Range requests return 206 with correct Content-Range
- [ ] Invalid ranges return 416
- [ ] Concurrent streams do not block
- [ ] Client disconnect cleans up resources
- [ ] No direct filesystem access to output directory
