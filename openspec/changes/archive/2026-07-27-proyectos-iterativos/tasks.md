# Tasks: Proyectos Iterativos

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~460 (320 additions + ~140 deletions) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | single-pr |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation + model param + voice/lyrics ref song | PR 1 | Config, OpenClaw model, music/voice/lyrics refactor with tests |
| 2 | Project orchestrator + router | PR 1 | project_worker, __init__.py orchestration, router.py, main.py registration |
| 3 | Integration tests | PR 1 | Full-chain tests for project flow |

## Phase 1: Foundation — Config & Model Param

- [x] 1.1 Add `PREVIEW_TARGET_SECONDS: int = 30` and `FINAL_TARGET_SECONDS: int = 150` to `app/config.py`
- [x] 1.2 Add `model: str = "google/lyria-3-clip-preview"` param to `OpenClawClient.invoke()` in `app/music/openclaw.py`; use it in payload
- [x] 1.3 Add `model` and `job_id` params to `app/music/__init__.py` generate(); use `job_id` for output path, pass model to client
- [x] 1.4 Test: `OpenClawClient.invoke` uses `payload["model"]` matching the param
- [x] 1.5 Test: `music.generate` with job_id outputs to `{OUTPUT_DIR}/{job_id}/`; without uses random UUID

## Phase 2: Voice & Lyrics — Reference Song

- [x] 2.1 Add `reference_song: str | None = None` to `app/voice/__init__.py:build_prompt()`; append `" Inspirada en el estilo de {reference_song}."` when set
- [x] 2.2 Add `reference_song: str | None = None` to `app/lyrics/prompts.py:build_user_prompt()`; append style reference when set
- [x] 2.3 Add `reference_song` param to `app/lyrics/__init__.py:generate()`; pass through to `build_user_prompt`
- [x] 2.4 Test: `build_prompt` with reference_song includes style text; without is unchanged
- [x] 2.5 Test: `build_user_prompt` with reference_song includes style guidance; without is unchanged

## Phase 3: Project Orchestrator

- [x] 3.1 Add `create_project()` in `app/projects/__init__.py` — calls `store.create_project()`, returns project_id
- [x] 3.2 Add `create_preview_job()` in `app/projects/__init__.py` — validates fragments exist, calls `store.get_accumulated_story()`, creates job with `lyria-3-clip-preview` model, links via `store.link_project_job()`, launches `project_worker()`, returns `JobCreateResponse`
- [x] 3.3 Add `create_final_job()` — same flow with `lyria-3-pro-preview` model, `extend_duration(target_seconds=settings.FINAL_TARGET_SECONDS)`
- [x] 3.4 Add `project_worker(job_id)` in `app/projects/__init__.py` — reads job metadata, calls lyrics/music pipeline with model+reference_song overrides; skips extend_duration for previews
- [x] 3.5 Test: `project_worker` dispatches correct model per job type (mock pipeline)
- [x] 3.6 Test: preview job skips `extend_duration`; final job calls it with 150s target

## Phase 4: Router & Wiring

- [x] 4.1 Create `app/projects/router.py` with `APIRouter(prefix="/api/projects")`
- [x] 4.2 Impl POST `/api/projects` — create project, return 201 with id
- [x] 4.3 Impl PATCH `/api/projects/{id}` — update project fields + optional fragment, return 200
- [x] 4.4 Impl POST `/api/projects/{id}/preview` — validate fragments, call orchestrator, return 202
- [x] 4.5 Impl POST `/api/projects/{id}/final` — same flow, return 202
- [x] 4.6 Impl GET `/api/projects/{id}` — return full project with fragments + previews, 404 if missing
- [x] 4.7 Register router in `app/main.py`: `from app.projects.router import router as projects_router` + `app.include_router(projects_router)`
- [x] 4.8 Test: all 5 routes via httpx TestClient (unit + integration)
- [x] 4.9 Test: POST preview with 0 fragments returns 400
- [x] 4.10 Test: GET /api/projects/{missing} returns 404
