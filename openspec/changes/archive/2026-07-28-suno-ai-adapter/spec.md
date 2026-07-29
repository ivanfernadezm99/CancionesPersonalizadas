# SDD Spec: Suno AI Music Provider Adapter

## MODIFIED Capability: music-generation

### MODIFIED Requirements

#### RQ-MUS-05: Model Selection by Job Type

OpenClaw: `lyria-3-clip-preview` for previews, clip-chaining or pro-preview for finals. Suno: uses V4/V4_5/V4_5ALL/V5 — no clip-chaining.
(Previously: unconditional OpenClaw model selection)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw preview | preview job, OpenClaw | music_generate invoked | model=`lyria-3-clip-preview` |
| OpenClaw final chained | final, `chaining_enabled`, OpenClaw | generation starts | clip-chain, NOT pro-preview |
| OpenClaw final fallback | final, no chaining, OpenClaw | starts | use `lyria-3-pro-preview` |
| OpenClaw existing gen | POST /api/generate, OpenClaw | invoked | model=`lyria-3-clip-preview` |

#### RQ-MUS-06: Reference Song in Prompt

OpenClaw: include ref as "al estilo de {song}". Suno: handled via Cover mode (RQ-SUNO-02).
(Previously: always appended unconditionally)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw with ref | `reference_song` set, OpenClaw | prompt built | include "al estilo de {song}" |
| OpenClaw no ref | no `reference_song`, OpenClaw | prompt built | no style reference added |

### ADDED Requirements

#### RQ-MUS-07: Provider Abstraction

Implement `BaseMusicProvider(ABC)` with `async generate(lyrics, voice_prompt, *, reference_audio=None) -> Path`.

- GIVEN BaseMusicProvider subclass WHEN instantiated THEN MUST implement `generate()`
- GIVEN subclass without `generate()` WHEN instantiated THEN TypeError raised

#### RQ-MUS-08: Config-Level Selection

`MUSIC_PROVIDER` env var (`openclaw`|`suno`, default `openclaw`). `app/music/__init__.py` delegates to configured provider. `openclaw` = pre-change behavior.

- GIVEN `MUSIC_PROVIDER=openclaw` WHEN `generate()` called THEN behavior matches pre-abstraction
- GIVEN invalid provider WHEN Settings init THEN config error raised

#### RQ-MUS-09: OpenClawProvider Wrapper

Wraps `OpenClawClient` without modifying it. Behavior identical to pre-abstraction.

- GIVEN `OpenClawProvider` WHEN `generate()` called THEN client methods called with same params AND Path matches pre-abstraction

## MODIFIED Capability: song-projects

### MODIFIED Requirements

#### RQ-PRJ-04: Generate Final Song

`POST /api/projects/{id}/final`. OpenClaw: clip-chain when `chaining_enabled`, else pro-preview. Suno: single generate call — chaining irrelevant.
(Previously: always OpenClaw, no provider branching)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw chained | `chaining_enabled`, OpenClaw | POST /final | 202 + job_id, clip-chaining |
| OpenClaw no chain | no chaining, OpenClaw | POST /final | 202 + job_id, pro-preview, no stitch |
| Suno single call | `music_provider=suno` | POST /final | 202 + job_id, SunoProvider, NO chaining |
| No fragments | project without fragments | POST /final | 422 |

## NEW Capability: suno-provider

**Purpose**: Music via Suno REST API — text-to-music and Cover — with polling, model selection, output storage.

#### RQ-SUNO-01: Text-to-Music

`POST /api/generate` with `prompt`, `lyrics`, `model`. Returns generation ID for polling.

- GIVEN lyrics + prompt WHEN `generate()` called THEN Suno API receives params AND generation ID returned
- GIVEN HTTP 429 WHEN received THEN wait Retry-After AND retry

#### RQ-SUNO-02: Cover Mode

Reference audio URL + lyrics. Verify URL returns HTTP 200 before invoking.

- GIVEN reachable URL + lyrics WHEN Cover invoked THEN request includes `reference_audio_url` AND produces cover
- GIVEN URL returns 404 WHEN checked THEN job fails BEFORE Suno AND error "reference audio unavailable"

#### RQ-SUNO-03: Model Selection

Support V4, V4_5, V4_5ALL, V5. `SUNO_MODEL` env var (default V4_5).

- GIVEN `SUNO_MODEL` unset WHEN generating THEN use V4_5
- GIVEN request with `model=V5` WHEN generating THEN API uses V5

#### RQ-SUNO-04: Async Polling

Poll `GET /api/generate/{id}`. Interval 5s exp backoff cap 30s. Timeout 300s.

- GIVEN generation ID WHEN polling THEN within 300s status="complete" AND download URL returned
- GIVEN generation >300s WHEN timeout THEN job failed AND error "Suno generation timed out"

#### RQ-SUNO-05: Output Storage

Store at `{output_dir}/{job_id}/final.mp3` (same as RQ-MUS-04).

- GIVEN completed Suno gen WHEN MP3 downloaded AND written THEN file exists AND valid MP3

#### RQ-SUNO-06: Configuration

Require `SUNO_API_KEY` and `SUNO_BASE_URL` when `MUSIC_PROVIDER=suno`. Validated at startup.

- GIVEN `MUSIC_PROVIDER=suno` without `SUNO_API_KEY` WHEN Settings validated THEN startup error
- GIVEN `MUSIC_PROVIDER=suno` with valid config WHEN Settings load THEN Suno client OK
