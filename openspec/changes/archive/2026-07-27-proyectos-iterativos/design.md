# Design: Proyectos Iterativos

## Technical Approach

Additive layer over existing single-shot pipeline. Projects create child jobs in the existing `jobs` table, reusing status/stream/cleanup for free. A `project_worker` runs the same pipeline steps as `job_worker` but with project-specific overrides (model, reference_song, duration). Model names are fixed to the actual OpenClaw names (`lyria-3-clip-preview` / `lyria-3-pro-preview`).

## Architecture Decisions

### Decision: Project worker vs. branching job_worker

| Option | Tradeoffs | Decision |
|--------|-----------|----------|
| Branch `job_worker` on metadata | Single codepath but conditionals couple jobs+projects | ❌ Rejected — mixes concerns |
| New `project_worker` in `app/projects/` | Duplicates pipeline glue, but clean separation, easy to test independently | ✅ Chosen — additive, no risk to existing flow |
| Extract shared `_run_pipeline()` | Cleanest but heavy refactor of stable code | ❌ Over-engineered for this scope |

`project_worker` calls the SAME shared functions (`lyrics_generate`, `build_prompt`, `music_generate`, `extend_duration`) with project-specific params. No changes to `job_worker`.

### Decision: Model name fix

Current `"google/lyria-3"` likely normalizes to `lyria-3-clip-preview` or is wrong. Fix by parameterizing `OpenClawClient.invoke(lyrics, prompt, model)`. Default stays `"google/lyria-3"` (backward-compat). Project flow overrides explicitly.

### Decision: Output directory for project jobs

`music_generate()` currently uses a random UUID for the output subdirectory. Add optional `job_id` param — when provided, use it as the subdirectory so the stream router (`{OUTPUT_DIR}/{job_id}/final.mp3`) resolves correctly. This also fixes the existing stream endpoint which expects `{job_id}` subdirectory.

### Decision: Story accumulation for project jobs

Worker reads `get_accumulated_story(project_id)` and passes concatenated fragments as the `story` param to `lyrics_generate()`. No schema changes needed.

## Component Flow

```
POST /api/projects/{id}/preview  or  /final
  │
  ▼
projects.orchestrator
  ├── get_project(id)                    → validates exists
  ├── get_accumulated_story(id)          → builds full story
  ├── create_job(GenerateRequest)        → jobs table
  │     └── metadata: {project_id, model, duration_target, reference_song}
  ├── link_project_job(id, job_id, type) → project_jobs table
  ├── asyncio.create_task(project_worker(job_id))
  └── return 202 { job_id, endpoints }
         │
         ▼
   GET /api/status/{job_id}  ──→  jobs.get_job()  (works free)
   GET /api/stream/{job_id}  ──→  stream router    (works free)
```

```
project_worker(job_id):
  Job metadata ──→ lyrics_generate(recipient, relationship, occasion="personalizada",
                                    genre, mood, story=accumulated_story,
                                    reference_song=...)
       │
       ▼
  build_prompt(voice_id, genre, mood, reference_song=...)
       │
       ▼
  music_generate(lyrics, voice_prompt, model=metadata.model, job_id=job_id)
       │
       ▼
  extend_duration(path, target_seconds=metadata.duration_target)
       │
       ▼
  update_status(complete) ──→ streamable via /api/stream/{job_id}
```

## Route Definitions

All under `app/projects/router.py` using FastAPI `APIRouter(prefix="/api/projects")`.

### POST /api/projects
- **Request**: `SongProjectCreate` (recipient, relationship, genre, mood, voice, reference_song?)
- **Response 201**: `{"id": "<uuid>", "status": "draft", "endpoints": {"project": "/api/projects/{id}"}}`
- **Error 422**: validation_error

### PATCH /api/projects/{id}
- **Request**: `SongProjectUpdate` (genre?, mood?, voice?, reference_song?, fragment?)
- **Response 200**: `SongProjectResponse` (full project with fragments)
- **Error 404**: project_not_found

### POST /api/projects/{id}/preview
- **Request**: (no body — uses accumulated project data)
- **Response 202**: `JobCreateResponse` (job_id, status, endpoints)
- **Constraints**: Minimum 1 story fragment required → 400 if empty
- **Model**: `lyria-3-clip-preview`, **Duration**: 30s (no extension needed)
- **Rate limited**: Same `MAX_CONCURRENT_JOBS` slot

### POST /api/projects/{id}/final
- **Request**: (no body — uses accumulated project data)
- **Response 202**: `JobCreateResponse`
- **Model**: `lyria-3-pro-preview`, **Duration**: 150s (extension applied)
- **Rate limited**: Same as preview

### GET /api/projects/{id}
- **Response 200**: `SongProjectResponse` (fragments, previews/jobs with status)
- **Error 404**: project_not_found

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/projects/__init__.py` | Modify | Add orchestration: create_project, create_preview, create_final, project_worker |
| `app/projects/router.py` | Create | FastAPI APIRouter with 5 project endpoints |
| `app/main.py` | Modify | Register project router, import project orchestration |
| `app/music/openclaw.py` | Modify | `invoke()` accepts `model` parameter |
| `app/music/__init__.py` | Modify | `generate()` accepts `model` and optional `job_id` params; pass through |
| `app/voice/__init__.py` | Modify | `build_prompt()` accepts optional `reference_song` |
| `app/lyrics/prompts.py` | Modify | `build_user_prompt()` accepts optional `reference_song` |
| `app/lyrics/__init__.py` | Modify | `generate()` accepts and passes through `reference_song` |
| `app/config.py` | Modify | Add `PREVIEW_TARGET_SECONDS: int = 30` and `FINAL_TARGET_SECONDS: int = 150` |

## Interfaces

### OpenClawClient.invoke (modified)
```python
async def invoke(self, lyrics: str, prompt: str, model: str = "google/lyria-3") -> str
```
Payload uses `model` directly: `"model": model`.

### music.generate (modified)
```python
async def generate(
    lyrics: str, voice_prompt: str,
    model: str = "google/lyria-3",
    job_id: str | None = None,
) -> Path
```
When `job_id` is provided, saves to `{OUTPUT_DIR}/{job_id}/generated.mp3` instead of a random UUID. Backward-compat: legacy calls without job_id keep the random UUID behavior.

### build_prompt (modified)
```python
def build_prompt(voice_id: str, genre: str, mood: str, reference_song: str | None = None) -> str
```
When `reference_song` provided, appends: `f" Inspirada en el estilo de {reference_song}."`

### build_user_prompt (modified)
```python
def build_user_prompt(
    recipient: str, relationship: str, occasion: str,
    genre: str, mood: str, story: str | None = None,
    reference_song: str | None = None,
) -> str
```
When `reference_song` provided, appends musical style hint.

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | `build_prompt` with reference_song | Test prompt includes reference text |
| Unit | `build_user_prompt` with reference_song | Test prompt includes style note |
| Unit | Lyrics `generate` passes reference_song | Mock providers, verify prompt |
| Unit | `OpenClawClient.invoke` model param | Verify payload.model value |
| Unit | `project_worker` dispatches correct model | Mock all pipeline steps, verify calls |
| Integration | Create project → add fragment → preview → status | Full API call chain |
| Integration | Create project → final → stream | End-to-end with real job creation |
| Regression | Legacy `POST /api/generate` unchanged | Verify existing test suite passes |
| Regression | Existing model default preserved | Verify `invoke()` defaults to `google/lyria-3` |

## Edge Cases

- **Empty fragments → preview/final**: Return 400 `{"error": "no_story_fragments", "message": "Add at least one story fragment before generating"}`
- **Story > 2000 chars**: Truncate in `get_accumulated_story()` at 2000 chars (consistent with `GenerateRequest.story` limit)
- **Concurrent previews**: Allowed — multiple preview jobs for the same project produce distinct job_ids. No locking needed.
- **Preview duration**: `lyria-3-clip-preview` returns ~30s MP3; skip `extend_duration()` entirely for previews
- **Missing model**: `lyria-3-pro-preview` may produce varying output lengths; `extend_duration(150)` handles any input length gracefully
- **Rate limiting**: Preview/final use the same `MAX_CONCURRENT_JOBS` slot mechanism; reject 429 if at capacity
- **Project not found**: 404 on any `{id}` route

## Migration / Rollback

No migration — projects use the same `jobs.db` via existing table creation (`CREATE TABLE IF NOT EXISTS`). Routes are additive. Rollback by removing `include_router(project_router)` from `app/main.py`. Model parameterization is backward-compatible.
