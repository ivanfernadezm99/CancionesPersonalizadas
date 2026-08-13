# Suno Provider Specification

**Purpose**: Music via Suno REST API — text-to-music and Cover — with polling, model selection, output storage.

## Requirements

### RQ-SUNO-01: Text-to-Music

`POST /api/generate` with `prompt`, `lyrics`, `model`. Returns generation ID for polling.

When `SunoProvider._invoke` receives a response whose error message indicates Suno's artist rejection (e.g. `Your tags contain artist name ...`), the provider MUST raise the error translated to a friendly Spanish message instead of the raw English text. The translated message MUST be: "El nombre de la canción de referencia contiene un artista. Por favor quitá el nombre del artista y probá de nuevo."

- GIVEN lyrics + prompt WHEN `generate()` called THEN Suno API receives params AND generation ID returned
- GIVEN HTTP 429 WHEN received THEN wait Retry-After AND retry
- GIVEN a response with `code=400` and a message matching the artist-rejection pattern WHEN `_invoke` raises THEN the raised error MUST be the friendly Spanish translation
- GIVEN any other Suno error message WHEN `_invoke` raises THEN the original message MUST be preserved unchanged

### RQ-SUNO-02: Cover Mode

Reference audio URL + lyrics. Verify URL returns HTTP 200 before invoking.

- GIVEN reachable URL + lyrics WHEN Cover invoked THEN request includes `reference_audio_url` AND produces cover
- GIVEN URL returns 404 WHEN checked THEN job fails BEFORE Suno AND error "reference audio unavailable"

### RQ-SUNO-03: Model Selection

Support V4, V4_5, V4_5ALL, V5. `SUNO_MODEL` env var (default V4_5).

- GIVEN `SUNO_MODEL` unset WHEN generating THEN use V4_5
- GIVEN request with `model=V5` WHEN generating THEN API uses V5

### RQ-SUNO-04: Async Polling

Poll `GET /api/generate/{id}`. Interval 5s exp backoff cap 30s. Timeout 300s.

- GIVEN generation ID WHEN polling THEN within 300s status="complete" AND download URL returned
- GIVEN generation >300s WHEN timeout THEN job failed AND error "Suno generation timed out"

### RQ-SUNO-05: Output Storage

Store at `{output_dir}/{job_id}/final.mp3` (same as RQ-MUS-04).

- GIVEN completed Suno gen WHEN MP3 downloaded AND written THEN file exists AND valid MP3

### RQ-SUNO-06: Configuration

Require `SUNO_API_KEY` and `SUNO_BASE_URL` when `MUSIC_PROVIDER=suno`. Validated at startup.

- GIVEN `MUSIC_PROVIDER=suno` without `SUNO_API_KEY` WHEN Settings validated THEN startup error
- GIVEN `MUSIC_PROVIDER=suno` with valid config WHEN Settings load THEN Suno client OK
