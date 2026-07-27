# Tasks: Canciones Automáticas

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1600 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-forecast |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Base | Est. |
|------|------|----|------|------|
| 1 | Foundation + Jobs | PR 1 | feature/canciones-automaticas | ~500 |
| 2 | Voice + Lyrics | PR 2 | PR 1 branch | ~350 |
| 3 | Music + Stream + App | PR 3 | PR 2 branch | ~500 |
| 4 | Integration Tests | PR 4 | PR 3 branch | ~250 |

## Phase 1: Foundation (PR 1)

- [x] 1.1 Init git repo, pyproject.toml, .gitignore, ruff/black/mypy config
- [x] 1.2 `app/config.py` — pydantic-settings BaseSettings (LLM keys, OpenClaw, DB path)
- [x] 1.3 `app/models.py` — GenerateRequest, JobStatusResponse, LyricsResult, VoiceConfig
- [x] 1.4 TDD: `app/jobs/store.py` — SQLite conn, WAL mode, schema creation
- [x] 1.5 TDD: `app/jobs/state.py` — JobStateMachine with transition validation
- [x] 1.6 TDD: `app/jobs/__init__.py` — create_job, get_job, update_status, count_active
- [x] 1.7 TDD: `app/jobs/cleanup.py` — TTL cleanup, 1h interval scheduler
- [x] 1.8 TDD: Tests — all transitions, DB ops, cleanup behavior

## Phase 2: Voice + Lyrics (PR 2) ✅

- [x] 2.1 TDD: `app/voice/registry.py` — VoiceConfig dict, startup validation
- [x] 2.2 TDD: `app/voice/__init__.py` — build_prompt(), get_available_voices()
- [x] 2.3 TDD: Tests — prompt tokens, invalid voice → ValueError, new voice registration
- [x] 2.4 `app/lyrics/prompts.py` — Spanish prompt templates per genre (8 genres)
- [x] 2.5 TDD: `app/lyrics/providers.py` — OpenAI/Gemini/OpenRouter clients + cascade
- [x] 2.6 TDD: `app/lyrics/__init__.py` — generate() orchestrates cascade
- [x] 2.7 TDD: Tests — cascade failover, output structure, no-key → LyricsGenerationError

## Phase 3: Music + Stream + App (PR 3)

- [x] 3.1 TDD: `app/music/openclaw.py` — client invoke/poll/download with retry
- [x] 3.2 TDD: `app/music/durext.py` — smart_crossfade_loop, simple_loop, extend_duration
- [x] 3.3 TDD: `app/music/__init__.py` — generate(), extend_duration() public API
- [x] 3.4 TDD: Tests — OpenClaw invoke/poll/retry, durext with synthetic MP3
- [x] 3.5 TDD: `app/stream/__init__.py` — async generator with disconnect guard
- [x] 3.6 TDD: `app/stream/router.py` — GET /api/stream/{id} with Range support
- [x] 3.7 TDD: Tests — 200/206/404/409/410/416, client disconnect cleanup
- [x] 3.8 `app/jobs/worker.py` — job_worker orchestrating lyrics→music→processing
- [x] 3.9 `app/main.py` — FastAPI app, lifespan, Semaphore(5), register routers

## Phase 4: Integration Tests (PR 4) ✅

- [x] 4.1 `tests/conftest.py` — fixtures: test DB, mock OpenClaw/LLM, sample MP3
- [x] 4.2 TDD: POST /api/generate → 202 + job row created
- [x] 4.3 TDD: GET /api/status → full state machine progression
- [x] 4.4 TDD: GET /api/stream → 200/206 with real MP3 fixture
- [x] 4.5 TDD: Rate limit — 2 concurrent with MAX=1 → 1 OK, 1× 429
- [x] 4.6 TDD: Job cleanup — insert old → trigger → assert deleted
- [x] 4.7 TDD: Startup — missing API key → app fails to start
