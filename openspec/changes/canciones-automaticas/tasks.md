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

## Phase 2: Voice + Lyrics (PR 2)

- [ ] 2.1 TDD: `app/voice/registry.py` — VoiceConfig dict, startup validation
- [ ] 2.2 TDD: `app/voice/__init__.py` — build_prompt(), get_available_voices()
- [ ] 2.3 TDD: Tests — prompt tokens, invalid voice → 422, new voice registration
- [ ] 2.4 `app/lyrics/prompts.py` — Spanish prompt templates per genre
- [ ] 2.5 TDD: `app/lyrics/providers.py` — OpenAI/Gemini/OpenRouter clients + cascade
- [ ] 2.6 TDD: `app/lyrics/__init__.py` — generate() orchestrates cascade
- [ ] 2.7 TDD: Tests — cascade failover, output structure, no-key startup 503

## Phase 3: Music + Stream + App (PR 3)

- [ ] 3.1 TDD: `app/music/openclaw.py` — client invoke/poll/download with retry
- [ ] 3.2 TDD: `app/music/durext.py` — smart_crossfade_loop, simple_loop, extend_duration
- [ ] 3.3 TDD: `app/music/__init__.py` — generate(), extend_duration() public API
- [ ] 3.4 TDD: Tests — OpenClaw invoke/poll/retry, durext with synthetic MP3
- [ ] 3.5 TDD: `app/stream/__init__.py` — async generator with disconnect guard
- [ ] 3.6 TDD: `app/stream/router.py` — GET /api/stream/{id} with Range support
- [ ] 3.7 TDD: Tests — 200/206/404/409/410/416, client disconnect cleanup
- [ ] 3.8 `app/jobs/worker.py` — job_worker orchestrating lyrics→music→processing
- [ ] 3.9 `app/main.py` — FastAPI app, lifespan, Semaphore(5), register routers

## Phase 4: Integration Tests (PR 4)

- [ ] 4.1 `tests/conftest.py` — fixtures: test DB, mock OpenClaw/LLM, sample MP3
- [ ] 4.2 TDD: POST /api/generate → 202 + job row created
- [ ] 4.3 TDD: GET /api/status → full state machine progression
- [ ] 4.4 TDD: GET /api/stream → 200/206 with real MP3 fixture
- [ ] 4.5 TDD: Rate limit — 6 concurrent → 5 OK, 1× 429
- [ ] 4.6 TDD: Job cleanup — insert old → trigger → assert deleted
- [ ] 4.7 TDD: Startup — missing API key → app fails to start
