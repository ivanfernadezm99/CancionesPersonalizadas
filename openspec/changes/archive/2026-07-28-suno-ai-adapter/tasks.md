# Tasks: Suno AI Music Provider Adapter

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450–550 |
| 800-line budget risk (project) | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

> Project `review_budget: 800` in `openspec/config.yaml` — estimated 450-550 lines fits within single PR.

## Phase 1: Test — Provider Foundation (RED)

- [x] 1.1 Write `test_base_provider_abc_enforces_generate()` — verify ABC raises TypeError
- [x] 1.2 Write `test_config_suno_settings()` — verify env vars load correctly
- [x] 1.3 Write `test_openclaw_provider_delegates_to_client()` — mock OpenClawClient, assert delegation

## Phase 2: Implement — Provider Foundation (GREEN)

- [x] 2.1 Add `MUSIC_PROVIDER`, `SUNO_API_KEY`, `SUNO_BASE_URL`, `SUNO_DEFAULT_MODEL`, `PUBLIC_BASE_URL` to `app/config.py`
- [x] 2.2 Create `app/music/providers.py` — `BaseMusicProvider(ABC)`, `MusicGenerationError`, `SunoError`, `OpenClawProvider` wrapping OpenClawClient

## Phase 3: Test — SunoProvider (RED)

- [x] 3.1 Write `test_suno_invoke_returns_task_id()` — respx mock POST, assert task_id
- [x] 3.2 Write `test_suno_poll_completes()` — respx mock GET pending→complete, assert download URL
- [x] 3.3 Write `test_suno_cover_health_check_fail()` — respx HEAD 404, assert error
- [x] 3.4 Write `test_suno_generate_returns_path()` — respx mock full flow (POST+GET+download), assert Path

## Phase 4: Implement — SunoProvider (GREEN)

- [x] 4.1 Add `SunoProvider` — `_invoke()`, `_health_check()`, `_poll()` (5s→30s backoff, 300s timeout), `_download()`, `generate()`
- [x] 4.2 Refactor `app/music/__init__.py` — `_select_music_provider()`; `generate()` delegates to configured provider

## Phase 5: Test — Project Integration (RED)

- [x] 5.1 Write `test_select_music_provider_by_env()` — monkeypatch `MUSIC_PROVIDER`, assert provider type
- [x] 5.2 Write `test_ref_audio_upload_keeps_file_when_suno()` — upload, assert file persists
- [x] 5.3 Write `test_chaining_disabled_when_suno()` — mock `MUSIC_PROVIDER=suno`, assert chaining=false

## Phase 6: Implement — Project Integration (GREEN)

- [x] 6.1 Create `app/projects/ref_audio.py` — store/serve/cleanup for `{OUTPUT_DIR}/ref-audio/{id}/reference.mp3`
- [x] 6.2 Modify `app/projects/router.py` — keep ref audio file when `MUSIC_PROVIDER=suno`; add `GET /api/ref-audio/{project_id}`
- [x] 6.3 Modify `app/projects/__init__.py` — pass `reference_audio_url` to `generate()`; chaining guard: if suno + chaining, warn and disable

## Phase 7: Refactor (CLEAN)

- [x] 7.1 Update `app/music/__all__` exports if needed
- [x] 7.2 Verify existing tests pass with `MUSIC_PROVIDER=openclaw` (no regression)
