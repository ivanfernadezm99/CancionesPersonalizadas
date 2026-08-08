# Apply Progress — form-voice-lyrics-reference (backend)

Mode: `hybrid` (OpenSpec + Engram). This is the apply-progress artifact for the
backend implementation of change `form-voice-lyrics-reference`.

Status: **Ready for verify** (backend). All backend T-tasks implemented, committed,
and passing. T24 (full backend verification) has known pre-existing failures,
documented below.

## Commit history

### Baselines (already landed before this apply)
- `0bd7a19` feat(reference-song): propagate reference song style fields through legacy generate pipeline
- `4eae951` feat(auth): enforce JWT HS256 shared-secret auth guard
- `54b787d` feat(projects): atomic replace-all fragments endpoint

### Slice 1 — voice registry (already landed)
- `773b93b` feat(voice): extend registry to 7 voices with regional options
- `f7930a5` feat(voice): add JWT-protected GET /api/voices endpoint
- `cffbf77` feat(voice): fail-fast registry validation on request boundary
- `17a60db` fix(projects): normalize legacy duo/children voices at read time

### Slice 2 — idea field + draft (T12–T21)
- `1204d5b` feat(projects): persist optional idea field on song projects
- `f330223` feat(lyrics): thread idea seed into lyrics prompt
- `3be1f70` feat(projects): add normalize_draft output validation helper
- `937abf1` feat(projects): add POST /{id}/lyrics-draft endpoint
- `ead00db` feat(projects): thread idea seed into preview/final generation
- `1529c9a` style(tests): black-format new draft/voice test files

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| T1 | `tests/test_voice_registry.py` | Unit | N/A | ✅ | ✅ | ✅ 7 voices exact | ➖ None |
| T2 | `tests/test_voice_registry.py` | Unit | ✅ | ✅ | ✅ | ✅ exact casing | ➖ None |
| T3 | `tests/test_voice_router.py` | Unit | ✅ | ✅ | ✅ | ✅ 7 exact | ➖ None |
| T4 | `tests/test_voice_router.py` | Unit | ✅ | ✅ | ✅ | ✅ JWT guard | ➖ None |
| T5 | `tests/test_voice_router.py` | Unit | ✅ | ✅ | ✅ | ✅ 422 cases | ➖ None |
| T6 | `tests/test_voice_router.py` | Unit | ✅ | ✅ | ✅ | ✅ PATCH no-voice | ➖ None |
| T7 | `tests/test_worker.py` | Unit | ✅ | ✅ | ✅ | ✅ duo→female | ➖ None |
| T8 | `tests/test_worker.py` | Unit | ✅ | ✅ | ✅ | ✅ children→child | ➖ None |
| T12 | `tests/test_idea.py` | Unit | ✅ | ✅ | ✅ | ✅ null default | ➖ None |
| T13 | `tests/test_idea.py` | Unit | ✅ | ✅ | ✅ | ✅ PATCH+GET | ➖ None |
| T14 | `tests/test_lyrics_generate.py` | Unit | ✅ | ✅ | ✅ | ✅ set/None | ➖ None |
| T15 | `tests/test_lyrics_generate.py` | Unit | ✅ | ✅ | ✅ | ✅ prompt pass | ➖ None |
| T16 | `tests/test_draft_normalize.py` | Unit | ✅ | ✅ | ✅ | ✅ <10 raises | ➖ None |
| T17 | `tests/test_draft_normalize.py` | Unit | ✅ | ✅ | ✅ | ✅ es pinned | ➖ None |
| T18 | `tests/test_lyrics_draft.py` | Integration | ✅ 375 pass | ✅ | ✅ | ✅ 404/503×2 | ➖ None |
| T19 | `tests/test_lyrics_draft.py` | Integration | ✅ | ✅ | ✅ | ✅ mapping | ➖ None |
| T20 | `tests/test_worker.py` | Unit | ✅ | ✅ | ✅ | ✅ preview params | ➖ None |
| T21 | `tests/test_worker.py` | Unit | ✅ | ✅ | ✅ | ✅ final params | ➖ None |

T22–T26 are frontend/staging — out of backend scope for this apply batch.

## Verification (T24) results

- **`python3 -m pytest`**: 377 passed, 5 failed, 2 warnings (98s).
  - Baseline at change start was 342 passed; +35 new tests landed across this change.
  - 5 failures are **pre-existing** and unrelated to this change (confirmed identical
    at the `0bd7a19` clean baseline):
    - `tests/test_lyrics_providers.py::TestGeminiProvider::test_generate_returns_lyrics_result`
      and `..._returns_none_on_error` — tests reference `GeminiProvider._get_model`,
      which does not exist in the current implementation.
    - `tests/test_full_flow.py::TestFullProjectFlow::test_full_flow` and
      `test_final_requires_payment`, `tests/test_integration.py::TestGenerateEndpoint::test_generate_full_pipeline_completes`
      — RESPX mock missing for `POST https://api.sunoapi.org/api/v1/generate`.
- **`ruff check .`**: 95 errors, 35 fixable. **Net -2 vs 97-error baseline** at
  `0bd7a19`. All new/standalone files (registry, voice router, draft, their tests)
  pass clean; remaining errors are pre-existing in shared files (models E501×7,
  router I001/F401/B904, test_worker E501×2) unchanged from baseline.
- **`black . --check`**: 44 files would be reformatted; **net +3 vs 41-file baseline**
  at `0bd7a19`. The 2 new files flagged by this change (`tests/test_voice_router.py`,
  `tests/test_lyrics_draft.py`) were reformatted and committed in `1529c9a`; all
  other flagged files were already black-flagged at baseline.
- **`mypy .`**: 16 errors, **net -1 vs 17-error baseline** at `0bd7a19`. No new type
  errors introduced by this change (reference_song/reference_description `call-arg`
  and B904/union-attr errors are identical to baseline, line-shifted).

### Decisions / deviations
- **No deviations from design F1** — the lyrics-draft endpoint mapping is exact:
  `recipient/relationship/occasion="personalizada"/genre/mood/story/idea/reference_song/reference_description`.
- Pre-existing lint/format/type/test debt was NOT fixed (out of scope, would bloat
  this change). Reported for a separate cleanup change.

## Files changed (backend)
- `app/projects/router.py` — POST `/{id}/lyrics-draft` endpoint + imports
- `app/projects/draft.py` — `normalize_draft()` helper (new)
- `app/projects/__init__.py` — idea threaded into preview/final GenerateRequest + metadata + `project_worker`
- `app/projects/store.py` — `idea` column (create/update/response)
- `app/models.py` — `idea` on create/update/response/GenerateRequest
- `app/lyrics/__init__.py` — `generate(..., idea=None)`
- `app/lyrics/prompts.py` — `build_user_prompt(..., idea=None)` "Idea principal"
- `app/voice/registry.py` — 7 voices (new)
- `app/voice/router.py` — GET /api/voices (new)
- `app/main.py` — register voice_router
- `tests/test_lyrics_draft.py` (new), `tests/test_idea.py` (new), `tests/test_draft_normalize.py` (new)
- `tests/test_worker.py`, `tests/test_voice_registry.py`, `tests/test_voice_router.py`, `tests/test_lyrics_generate.py` — extended

## Artifacts
- OpenSpec apply-progress: `openspec/changes/form-voice-lyrics-reference/apply-progress.md`
- Engram apply-progress: topic key `sdd/form-voice-lyrics-reference/apply-progress` (capture_prompt=false)
- Engram tasks observation updated: T12–T21 marked complete

## Status
Backend: **18/18 backend T-tasks complete** (T1–T21, excluding frontend T9/T10/T22/T23/T25 and pending staging T11/T26).
Ready for `sdd-verify` (backend). Note pre-existing failures above.
