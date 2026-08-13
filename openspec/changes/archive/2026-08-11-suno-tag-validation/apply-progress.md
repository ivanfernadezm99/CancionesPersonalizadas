# Apply Progress — suno-tag-validation

**Status**: ALL 17/17 tasks complete.

- Batch 1 (PR1 backend, this repo): Phases 1-6, tasks 1.1-6.3 → 14 tasks
- Batch 2 (PR2 frontend, POSCuentasCorrientes): Phase 7, tasks 7.1-7.3 → 3 tasks

## TDD Cycle Evidence (PR1 — Backend)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1/1.2 | `tests/test_tag_sanitizer.py` | Unit | N/A (new) | ModuleNotFoundError | 20 cases green | 6 strip + 5 artist + 3 empty + 3 idempotent | blocklist-aware side-pick |
| 2.1/2.2 | `tests/test_models.py` | Unit | N/A (new) | 4 failed | 8/8 green | create + patch + empty + GenerateRequest | song-only docstrings |
| 3.1/3.2 | `tests/test_voice_prompt.py`, `tests/test_lyrics_generate.py` | Unit | 63/63 | 5 failed | GREEN | artist-only scenarios added | exact template kept |
| 4.1/4.2 | `tests/test_music/test_providers.py` | Unit + respx | 38/38 | ImportError | 46/46 green | 4 translate + 4 Suno-400 cases | E501-wrapped raises |
| 5.1/5.2 | `tests/test_worker_reference.py`, `tests/test_projects_orchestrator.py` | Integration | 63/63 | 3 failed | GREEN | artist-only worker case | sanitized vars |
| 6.1/6.2/6.3 | router/orchestrator/voice/lyrics/worker | Integration | 25/25 | 2 expected-fail | 29/29 green | +4 router cases | fixture rename |

## TDD Cycle Evidence (PR2 — Frontend)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 7.2 | `create-project.component.spec.ts` | Component | 31/31 | 2 fail (old hint) | all pass | 2 cases (examples + de-format) | Clean |
| 7.1 | `create-project.component.spec.ts` | Unit + Integration | 33/33 | 7 stub + 3 integration fail | all 45 pass | 10 sanitizer + 3 integration | Clean |

## Test Summary

- **Backend** (`python3 -m pytest -q`): 434 passed, 5 failed — the 5 are pre-existing and verified identical on git-stash baseline (unrelated to this change: RESPX suno/mp-gateway mocks + `no such table` + GeminiProvider `_get_model`).
- **Frontend** (`npx jest --testPathPatterns='canciones-personalizadas'`): 45 tests (33 original + 2 hint + 7 sanitizer + 3 integration), all passing across 7 suites.

## Files Changed

### Backend (CancionesPersonalizadas)
- `app/tag_sanitizer.py` — new: `sanitize_reference_song`, `ARTIST_BLOCKLIST`, `ARTIST_REJECTION_MESSAGE`
- `app/models.py` — `_validate_reference_song` on `SongProjectCreate`/`SongProjectUpdate`; song-only docstrings
- `app/voice/__init__.py` — `build_prompt` sanitizes before style line
- `app/lyrics/prompts.py` — `build_user_prompt` sanitizes before `Referencia musical:`
- `app/music/providers.py` — `_translate_suno_error` at both `_invoke` raise sites
- `app/jobs/worker.py` — `job_worker` sanitizes `ref_song`; metadata keeps originals
- `app/projects/__init__.py` — `project_worker` sanitizes metadata `reference_song`
- Tests: new `tests/test_tag_sanitizer.py`, `tests/test_models.py`; updated `test_voice_prompt.py`, `test_lyrics_generate.py`, `test_projects_router.py`, `test_projects_orchestrator.py`, `test_worker_reference.py`, `test_music/test_providers.py`

### Frontend (POSCuentasCorrientes)
- `src/app/canciones-personalizadas/reference-song.ts` — new: `sanitizeReferenceSong` mirror (strip + minimal 3-artist blocklist for side-picking)
- `src/app/canciones-personalizadas/create/create-project.component.ts` — hint text song-only; sanitize at payload build
- `src/app/canciones-personalizadas/create/create-project.component.spec.ts` — +12 tests (2 hint, 10 sanitizer, 3 integration)

## Notes

- Frontend mirror includes a minimal blocklist (3 seed artists from backend) so dash-side-picking is accurate (`"Bachata Rosa - Juan Luis Guerra"` keeps `"Bachata Rosa"`).
- Dash keeps last side, `de` keeps first side, blocklist resolves disambiguation.
- The sanitizer is idempotent and applied at both input validation and generation time (defense in depth).
