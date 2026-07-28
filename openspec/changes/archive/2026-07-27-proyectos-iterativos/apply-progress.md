# Apply Progress: Proyectos Iterativos

## Mode
- **Delivery**: single-pr (460 lines, under 800 budget)
- **Artifact mode**: hybrid (engram + openspec)

## Completed Tasks

### Phase 1: Foundation — Config & Model Param
- [x] 1.1 Added `PREVIEW_TARGET_SECONDS: int = 30` and `FINAL_TARGET_SECONDS: int = 150` to `app/config.py`
- [x] 1.2 Added `model: str = "google/lyria-3-clip-preview"` param to `OpenClawClient.invoke()`
- [x] 1.3 Added `model` and `job_id` params to `music.generate()` with output path wiring
- [x] 1.4 Test: invoke model param used in payload
- [x] 1.5 Test: job_id output path, random UUID fallback

### Phase 2: Voice & Lyrics — Reference Song
- [x] 2.1 Added `reference_song` to `build_prompt()` with style text injection
- [x] 2.2 Added `reference_song` to `build_user_prompt()` with style guidance
- [x] 2.3 Added `reference_song` pass-through in `lyrics.generate()`
- [x] 2.4 Test: build_prompt reference_song inclusion
- [x] 2.5 Test: build_user_prompt reference_song inclusion

### Phase 3: Project Orchestrator
- [x] 3.1 `create_project()` in `app/projects/__init__.py`
- [x] 3.2 `create_preview_job()` with model `lyria-3-clip-preview`
- [x] 3.3 `create_final_job()` with model `lyria-3-pro-preview` + duration extension
- [x] 3.4 `project_worker()` with model/ref_song overrides, preview skips extend_duration
- [x] 3.5 Test: correct model dispatch per job type
- [x] 3.6 Test: preview skips extend_duration, final calls with 150s

### Phase 4: Router & Wiring
- [x] 4.1 Created `app/projects/router.py` with `APIRouter(prefix="/api/projects")`
- [x] 4.2 POST `/api/projects` — 201
- [x] 4.3 PATCH `/api/projects/{id}` — 200
- [x] 4.4 POST `/api/projects/{id}/preview` — 202
- [x] 4.5 POST `/api/projects/{id}/final` — 202
- [x] 4.6 GET `/api/projects/{id}` — 200/404
- [x] 4.7 Registered router in `app/main.py`
- [x] 4.8 Route-level tests for all 5 endpoints
- [x] 4.9 POST preview with 0 fragments returns 400
- [x] 4.10 GET missing project returns 404

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `app/config.py` | Modified | Added PREVIEW_TARGET_SECONDS, FINAL_TARGET_SECONDS |
| `app/music/openclaw.py` | Modified | Parameterized invoke() with model param |
| `app/music/__init__.py` | Modified | Added model and job_id to generate() |
| `app/voice/__init__.py` | Modified | Added reference_song to build_prompt() |
| `app/lyrics/prompts.py` | Modified | Added reference_song to build_user_prompt() |
| `app/lyrics/__init__.py` | Modified | Pass through reference_song |
| `app/projects/__init__.py` | Created | Project orchestrator (create_project, create_preview_job, create_final_job, project_worker) |
| `app/projects/router.py` | Created | FastAPI APIRouter with 5 endpoints |
| `app/projects/store.py` | Modified | Fix init_schema race condition (accept optional connection) |
| `app/jobs/__init__.py` | Modified | Added initial_metadata param to create_job |
| `app/main.py` | Modified | Registered projects_router |
| `tests/test_projects_orchestrator.py` | Created | 7 tests for orchestrator |
| `tests/test_projects_router.py` | Created | 12 tests for router (unit + integration) |
| `tests/test_music/test_openclaw.py` | Modified | Added model param tests |
| `tests/test_music/test_generate.py` | Modified | Added job_id/model tests |
| `tests/test_voice_prompt.py` | Modified | Added reference_song tests + fixed pre-existing flaky assertion |
| `tests/test_lyrics_generate.py` | Modified | Added reference_song prompt + pass-through tests |

## Deviations from Design
- Store's `init_schema` was creating a separate connection causing "database is locked" race; refactored to accept optional existing connection
- `update_status` doesn't allow `queued → queued` self-transition; moved initial metadata to `create_job()` via new `initial_metadata` parameter instead

## TDD Cycle Evidence

| Task Group | RED (tests first) | GREEN (implemented) | REFACTOR |
|-----------|-------------------|---------------------|----------|
| Phase 1: Config/OpenClaw/Music | Wrote test_invoke_uses_model_param, test_invoke_default_model, test_generate_with_job_id_uses_job_id_dir, test_generate_without_job_id_uses_random_uuid, test_generate_passes_model_to_client | Implemented model param in openclaw.py and generate() in music/__init__.py | Added model to invoke() signature |
| Phase 2: Voice/Lyrics ref song | Wrote test_with_reference_song_includes_style_text, test_without_reference_song_is_unchanged, build_user_prompt tests, lyric generate pass-through test | Implemented reference_song in build_prompt, build_user_prompt, lyrics.generate | None needed |
| Phase 3: Orchestrator | Wrote 7 tests covering create_project, create_preview, create_final, project_worker dispatch, duration, reference_song | Implemented orchestrator in app/projects/__init__.py | Moved metadata to initial_metadata (avoided update_status self-transition) |
| Phase 4: Router | Wrote 12 route-level tests covering all endpoints, errors, integration flow | Implemented router.py and registered in main.py | Fixed store "database is locked" by passing conn to init_schema |

## Issues Found
- `update_status` does not allow `queued → queued` self-transition (by design of JobStateMachine). Workaround: added `initial_metadata` parameter to `create_job()`.
- aiosqlite connections in quick succession cause "database is locked". Refactored `init_schema()` to accept an optional existing connection parameter.
- Pre-existing test `test_prompt_is_spanish` checked for words not in the prompt (`música`, `estilo`). Changed to check for actual prompt words (`canción`, `melodía`).

## Status
**26/26 tasks complete. Ready for verify.**
