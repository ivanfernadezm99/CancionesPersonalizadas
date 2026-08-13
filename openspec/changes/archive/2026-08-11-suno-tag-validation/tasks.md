# Tasks: Suno Tag Validation (artist names in reference_song)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450–550 (backend ~350–450, frontend ~100) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Backend PR (this repo) → Frontend PR (POSCuentasCorrientes, separate repo) |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium
```

Configured budget is 800 (openspec/config.yaml). Split is cross-repo (mandatory), each PR well under 400.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Sanitizer + validators + prompt guards + error translation + both workers | PR 1 (this repo) | `pytest tests/test_tag_sanitizer.py tests/test_voice_prompt.py tests/test_lyrics_generate.py tests/test_projects_router.py tests/test_projects_orchestrator.py tests/test_worker_reference.py -q` | `uvicorn app.main:app` → POST /api/projects "Bachata Rosa - Juan Luis Guerra" stores "Bachata Rosa"; "Los Palmeras" → 422 | Revert call sites + validator; drop `tag_sanitizer` import; translation isolated in providers.py |
| 2 | Client mirror + hint fix | PR 2 (POS repo) | `ng test` — create-project + reference-song specs | Staging form: hint shows song-only; payload carries sanitized song | Revert component + delete `reference-song.ts` |

## Phase 1: Foundation — sanitizer module

- [x] 1.1 Create `app/tag_sanitizer.py`: pure `sanitize_reference_song(value)` stripping `"Song - Artist"` / `"Song de Artist"` / `"Song (Artist)"` case-insensitive + trimmed; blocklist substring-match; returns `None` when no usable token; `ARTIST_BLOCKLIST` (seed: los palmeras, la mona jiménez, juan luis guerra); `ARTIST_REJECTION_MESSAGE` constant (RQ-TAG-01/02/03)
- [x] 1.2 RED: `tests/test_tag_sanitizer.py` — parametrized table: strip patterns, unchanged song, blocklist exact/case-insensitive/embedded, artist-only-after-strip, `""`/`None` → `None`, idempotency (RQ-TAG-01/02/03)

## Phase 2: Input validation — Pydantic

- [x] 2.1 RED: model tests — create/patch strip-on-store, 422 artist-only with Spanish message, `""`/absent passes, `GenerateRequest` untouched (RQ-PRJ-01/02, RQ-RS-05)
- [x] 2.2 Modify `app/models.py`: `_validate_reference_song` field_validator on `SongProjectCreate` + `SongProjectUpdate` (reuse `_validate_voice` pattern); update all three `reference_song` docstrings to song-only examples (RQ-PRJ-01/02, RQ-REF-01)

## Phase 3: Generation-time guard

- [x] 3.1 Modify `app/voice/__init__.py` `build_prompt`: sanitize before appending style line; skip when sanitized `None` (RQ-VOI-05, RQ-TAG-04)
- [x] 3.2 Modify `app/lyrics/prompts.py` `build_user_prompt`: sanitize before `Referencia musical:` block; skip when `None` (RQ-LYR-04/06)

## Phase 4: Error translation — SunoProvider

- [x] 4.1 Modify `app/music/providers.py`: `_translate_suno_error(msg)` matching artist-name / tags-contain-artist (IGNORECASE) → `ARTIST_REJECTION_MESSAGE`; apply at both `_invoke` raise sites (HTTP≠200 + biz-code) (RQ-SUNO-01)
- [x] 4.2 Tests: `_translate_suno_error` unit tests (match → Spanish; other → preserved) + respx Suno 400 → job `error` is Spanish, non-retryable (RQ-SUNO-01, RQ-JOB-02/06)

## Phase 5: Worker consistency

- [x] 5.1 Modify `app/jobs/worker.py` `job_worker`: sanitize `ref_song` before `lyrics_generate` + `build_prompt`; keep `ref_desc or ref_song`; metadata persists originals (RQ-RS-02/03/06, RQ-JOB-08)
- [x] 5.2 Modify `app/projects/__init__.py` `project_worker`: sanitize metadata `reference_song` before lyrics + prompt (RQ-RS-06)
- [x] 5.3 Test: both workers pass sanitized "Bachata Rosa", no artist token in prompts, metadata keeps originals (RQ-RS-06, RQ-JOB-08)

## Phase 6: Existing test fixtures

- [x] 6.1 Update `tests/test_voice_prompt.py` + `test_lyrics_generate.py`: assert song-presence + artist-absence (not literal template suffix; design open question) (RQ-VOI-05, RQ-LYR-04/06)
- [x] 6.2 Update `tests/test_projects_router.py` + `test_projects_orchestrator.py`: strip-on-create/patch, 422 rejection, empty accepted (RQ-PRJ-01/02)
- [x] 6.3 Update `tests/test_worker_reference.py`: sanitized expectation for "Coldplay - Yellow" → "Yellow" (RQ-RS-06)

## Phase 7: Frontend (cross-repo — POSCuentasCorrientes)

- [x] 7.1 Create `src/app/canciones-personalizadas/reference-song.ts`: `sanitizeReferenceSong` mirror (strip-only); apply at payload build (~lines 790/874) (RQ-REF-01)
- [x] 7.2 Update hint text in `create/create-project.component.ts` (~line 105) to song-only examples (RQ-REF-01)
- [x] 7.3 Update component specs: hint text, mirror util, friendly-error rendering (RQ-REF-01)
