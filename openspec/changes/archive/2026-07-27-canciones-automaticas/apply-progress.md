# Apply Progress: Canciones Automáticas

## Status: PR 1 ✅ COMPLETE | PR 2 ✅ COMPLETE | PR 3 ✅ COMPLETE | PR 4 ✅ COMPLETE

## PR 1: Foundation + Jobs (Phase 1)

### Tasks Completed

| Task | Status | Details |
|------|--------|---------|
| 1.1 | ✅ | git init, pyproject.toml, .gitignore, ruff/black/mypy config |
| 1.2 | ✅ | app/config.py — pydantic-settings BaseSettings |
| 1.3 | ✅ | app/models.py — GenerateRequest, JobStatusResponse, LyricsResult, VoiceConfig |
| 1.4 | ✅ | app/jobs/store.py — SQLite conn, WAL mode, schema (TDD: 6 tests) |
| 1.5 | ✅ | app/jobs/state.py — JobStateMachine (TDD: 31 tests) |
| 1.6 | ✅ | app/jobs/__init__.py — create_job, get_job, update_status, count_active (TDD: 19 tests) |
| 1.7 | ✅ | app/jobs/cleanup.py — TTL cleanup, scheduler (TDD: 9 tests) |
| 1.8 | ✅ | All tests for transitions, DB ops, cleanup (total: 65 tests) |

## PR 2: Voice + Lyrics (Phase 2)

### Tasks Completed

| Task | Status | Details |
|------|--------|---------|
| 2.1 | ✅ | `app/voice/registry.py` — VoiceConfig dict, validate_registry(), get_voice() (TDD: 9 tests) |
| 2.2 | ✅ | `app/voice/__init__.py` — build_prompt(), get_available_voices() (TDD: 12 tests) |
| 2.3 | ✅ | Tests — prompt tokens, invalid voice → ValueError, new voice registration |
| 2.4 | ✅ | `app/lyrics/prompts.py` — SYSTEM_PROMPT, build_user_prompt(), genre templates (8 genres) |
| 2.5 | ✅ | `app/lyrics/providers.py` — OpenAIProvider, GeminiProvider, OpenRouterProvider, cascade_providers() (TDD: 16 tests) |
| 2.6 | ✅ | `app/lyrics/__init__.py` — generate() orchestrator (TDD: 6 tests) |
| 2.7 | ✅ | Tests — cascade failover, output structure, missing API key → LyricsGenerationError |

## PR 3: Music + Stream + App (Phase 3)

### Tasks Completed

| Task | Status | Details |
|------|--------|---------|
| 3.1 | ✅ | `app/music/openclaw.py` — OpenClawClient with invoke/poll/download + retry (TDD: 16 tests) |
| 3.2 | ✅ | `app/music/durext.py` — smart_crossfade_loop, simple_loop, extend_duration (TDD: 10 tests) |
| 3.3 | ✅ | `app/music/__init__.py` — generate(), extend_duration() public API (TDD: 7 tests) |
| 3.4 | ✅ | Tests — OpenClaw invoke/poll/retry with respx, durext with synthetic MP3 |
| 3.5 | ✅ | `app/stream/__init__.py` — stream_generator with disconnect guard (TDD: 6 tests) |
| 3.6 | ✅ | `app/stream/router.py` — GET /api/stream/{id} with Range support (TDD: 8 tests) |
| 3.7 | ✅ | Tests — 200/206/404/409/410/416, client disconnect cleanup |
| 3.8 | ✅ | `app/jobs/worker.py` — job_worker orchestrating lyrics→music→processing (7 tests) |
| 3.9 | ✅ | `app/main.py` — FastAPI app, lifespan, rate limiting, all routers (7 tests) |

## PR 4: Integration Tests (Phase 4)

### Tasks Completed

| Task | Status | Details |
|------|--------|---------|
| 4.1 | ✅ | `tests/conftest.py` — shared fixtures (test_db, mock_openclaw, mock_llm_providers, sample_mp3, test_app) |
| 4.2 | ✅ | POST /api/generate → 202 integration test (4 tests: 202 + job_id, DB row created, 422 validation, full pipeline) |
| 4.3 | ✅ | GET /api/status → state machine progression (4 tests: queued info, all states, failed job, 404) |
| 4.4 | ✅ | GET /api/stream → 200/206 with MP3 fixture (8 tests: 200, 206 range, open-ended range, 416, 404, 409, 410, missing MP3 410) |
| 4.5 | ✅ | Rate limiting — 2 concurrent with MAX=1 (3 tests: 1×202 + 1×429, Retry-After header, recovery) |
| 4.6 | ✅ | Job cleanup — TTL deletion (4 tests: old removed, recent preserved, mixed ages, no output dir) |
| 4.7 | ✅ | Startup validation — missing API key (4 tests: has_any_llm_key(), lyrics fail, starts with keys) |

## Verification (PR 4)

- **pytest**: 196/196 passed (169 existing + 27 new)
- **ruff**: All checks passed
- **mypy**: No new issues (pre-existing errors only in older test files)

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 4.2 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 4 cases | ✅ Clean |
| 4.3 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 4 cases | ✅ Clean |
| 4.4 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 8 cases | ✅ Clean |
| 4.5 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 3 cases | ✅ Clean |
| 4.6 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 4 cases | ✅ Clean |
| 4.7 | `test_integration.py` | Integration | N/A (new) | ✅ Written | ✅ Passed | ✅ 4 cases | ✅ Clean |

## Files Changed (PR 4)

```
tests/conftest.py          — Shared fixtures: test_db, mock_openclaw, mock_llm_providers, sample_mp3, test_app
tests/test_integration.py  — 27 integration tests for all endpoints, rate limiting, cleanup, startup validation
pyproject.toml             — Fixed httpx-mock → respx dev dependency
app/main.py                — Added lifespan validation for missing LLM API keys
openspec/.../apply-progress.md — Updated with PR 4 status
openspec/.../tasks.md          — All tasks marked complete
```

## Deviations from Design

- **Startup validation via httpx**: The ASGI transport (httpx) handles lifespan startup/failed events internally without propagating them as request exceptions. Testing startup validation required testing the downstream effects (lyrics generation failure) rather than relying on transport-level exceptions.
- **Rate limiting test concurrency**: aiosqlite doesn't handle concurrent writes well (`database is locked`). Used MAX_CONCURRENT_JOBS=1 so only 1 DB write happens, avoiding lock contention.
- **Mock LLM provider**: Had to explicitly set `result.provider = "test-provider"` since `_parse_lyrics_json()` sets an empty provider string — mimicking how real providers set `result.provider = self.name`.

## Issues Found

- aiosqlite `database is locked` on concurrent writes — same limitation as PR 3. Rate limiting tests limit concurrent DB access.
- ASGI lifespan exceptions not propagated by httpx transport — documented for future reference.
- Pydantic + mypy: `Field(None)` default not recognized by mypy as optional; need explicit `story=None` in calls.

## Final Test Summary

- **Total tests**: 196 (169 pre-existing + 27 new)
- **Test layers**: Unit (169), Integration (27)
- **Coverage areas**: All API endpoints, rate limiting, cleanup, startup validation, state machine
