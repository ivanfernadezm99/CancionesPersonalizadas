# Apply Progress: Canciones Automáticas

## Status: PR 1 ✅ COMPLETE | PR 2 ✅ COMPLETE | PR 3 🔲 | PR 4 🔲

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

## Verification (PR 2)

- **pytest**: 108/108 passed (65 PR1 + 43 new)
- **ruff**: All checks passed
- **mypy**: No issues found

## Git Log (PR 2)

```
(commits will appear after commit step)
```

## Files Changed (PR 2)

```
app/voice/__init__.py
app/voice/registry.py
app/lyrics/__init__.py
app/lyrics/prompts.py
app/lyrics/providers.py
tests/test_voice_registry.py
tests/test_voice_prompt.py
tests/test_lyrics_providers.py
tests/test_lyrics_generate.py
```

## Next: PR 3 — Music + Stream + App (Phase 3)
