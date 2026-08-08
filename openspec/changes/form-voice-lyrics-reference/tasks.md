# Tasks: Form Voice Variety, Lyrics Autodraft, Reference Song Delivery

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~180, S2 ~260, total ~440 |
| 800-line budget risk | **Low** |
| Chained PRs recommended | **Yes** (per design, slice 1 → slice 2 in each repo) |
| Suggested split | PR 1 (baselines + slice 1) → PR 2 (slice 2) per repo |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

Per-slice deltas (back/front): S1 ~90/~90, S2 ~120/~140 — each well under budget. Chaining keeps baseline commits (reference-song-style, auth rewrite) out of feature diffs.

### Suggested Work Units (commit-ready)

| Unit | Slice | Summary | Files | Test-first |
|------|-------|---------|-------|-----------|
| B1 | baseline | reference-song-style baseline commit (backend from archive, frontend from working tree) | both repos | — |
| B2 | baseline | auth rewrite baseline commit (backend only) | backend `app/auth/*` | existing tests |
| S1U1 | 1 | 7-entry registry + tests | `app/voice/registry.py`, `tests/test_voice_registry.py` | RED→GREEN |
| S1U2 | 1 | `GET /api/voices` router + main wiring | `app/voice/router.py`, `app/main.py`, `tests/test_voice_router.py` | RED |
| S1U3 | 1 | fail-fast voice validators (skip None) | `app/models.py`, `tests/test_voice_router.py` | RED |
| S1U4 | 1 | legacy duo/children read-time normalization | `app/projects/__init__.py`, `tests/test_worker.py` | RED |
| S1U5 | 1 | data-driven voice select + mirror fallback | frontend `models.ts`, `canciones.service.ts`, `create-project.component.ts` | RED (jest) |
| S1U6 | 1 | reference-song verify/deploy (Suno-gated) | both repos (deploy) | manual staging |
| S2U1 | 2 | `idea` ALTER + store create/update | `app/projects/store.py`, `tests/test_idea.py` | RED |
| S2U2 | 2 | thread idea through generate + prompt | `app/lyrics/__init__.py`, `app/lyrics/prompts.py`, `tests/test_lyrics_generate.py` | RED |
| S2U3 | 2 | normalize_draft (strip, >=10, lang es) | `app/projects/draft.py`, `tests/test_draft_normalize.py` | RED |
| S2U4 | 2 | lyrics-draft endpoint (404/503) | `app/projects/router.py`, `tests/test_lyrics_draft.py` | RED |
| S2U5 | 2 | preview/final thread idea | `app/projects/__init__.py`, `app/jobs/worker.py`, `tests/test_worker.py` | RED |
| S2U6 | 2 | idea textarea + autogenerar + draft→fragments | frontend `create-project.component.ts`, `canciones.service.ts`, `models.ts` | RED (jest) |

## Baseline Prerequisites (CONDITIONAL — may already be committed)

- [x] B1 — Commit `reference-song-style` in both repos: backend from `openspec/changes/archive/2026-08-06-reference-song-style/` state, frontend from working tree. *Skip if already landed.*
- [x] B2 — Commit backend `auth rewrite` separately. *Skip if already landed; must stay out of slice diffs.*

## Phase 1: Voice Registry + /voices (Slice 1)

- [x] T1 (RED, backend) — `tests/test_voice_registry.py`: assert `len(VOICE_REGISTRY) == 7`, no `duo`/`children`, labels `Voz Femenina`/`Voz Masculina` exact casing.
- [x] T2 (GREEN, backend) — `app/voice/registry.py`: add `es-latino-male`, `es-espana-male`, `es-espana-female`, `es-latina-female`, `es-espana-child` (`prompt_es` per D1/RQ-VOI-02). `python3 -m pytest tests/test_voice_registry.py`.
- [x] T3 (RED, backend) — `tests/test_voice_router.py`: GET `/api/voices` returns 7 exact `{id,label,gender}`; `es-latino-male` present.
- [x] T4 (GREEN, backend) — create `app/voice/router.py` (`prefix="/api"`, JWT-protected, `get_available_voices()`), register in `app/main.py`. `python3 -m pytest tests/test_voice_router.py`.
- [x] T5 (RED, backend) — `tests/test_voice_router.py`: 422 on `duo`/`children`/unknown; `es-latino-male` accepted; PATCH without `voice` does NOT 422.
- [x] T6 (GREEN, backend) — `app/models.py`: `_validate_voice` `@field_validator` on `GenerateRequest`/`SongProjectCreate`/`SongProjectUpdate`; `return v if v is not None`; lazy `get_voice`. `python3 -m pytest tests/test_voice_router.py`.
- [x] T7 (RED, backend) — `tests/test_worker.py`: rebuild `GenerateRequest` from stored `voice="duo"` maps to valid voice (no ValidationError→500).
- [x] T8 (GREEN, backend) — `app/projects/__init__.py`: normalize legacy `duo`→`female`, `children`→`es-espana-child` at read time in `create_preview_job`/`create_final_job`. `python3 -m pytest tests/test_worker.py`.
- [x] T9 (RED, frontend) — implemented in POSCuentasCorrientes repo (branch `stg`): voice select tests (getVoices, no duo/children, mirror fallback on 401).
- [x] T10 (GREEN, frontend) — implemented in POSCuentasCorrientes repo: `VoiceInfo`/`idea` in models.ts, `getVoices()` + fallback mirror in canciones.service.ts, data-driven voice select in create-project.component.ts.
- [ ] T11 (verify/deploy, both) — **pending staging; needs MUSIC_PROVIDER=suno + MP3 upload on staging (deploy task, not backend apply)**

## Phase 2: Idea Field + Lyrics Autodraft (Slice 2)

- [x] T12 (RED, backend) — `tests/test_idea.py`: create with/without `idea` persists; PATCH updates `idea`; `GET` returns it; `idea` null by default.
- [x] T13 (GREEN, backend) — `app/projects/store.py`: idempotent `ALTER TABLE projects ADD COLUMN idea TEXT` in `init_schema` (both conn paths); `idea` in INSERT + `val is not None` update loop; `app/models.py` add `idea: str | None` to create/update/response; `_project_to_response` adds `idea`. `python3 -m pytest tests/test_idea.py`.
- [x] T14 (RED, backend) — `tests/test_lyrics_generate.py`: `build_user_prompt` includes `Idea principal` when idea set, omits when None; `generate(idea=...)` passes through.
- [x] T15 (GREEN, backend) — `app/lyrics/prompts.py` `build_user_prompt(..., idea=None)` + "Idea principal" section; `app/lyrics/__init__.py` `generate(..., idea=None)`. `python3 -m pytest tests/test_lyrics_generate.py`.
- [x] T16 (RED, backend) — `tests/test_draft_normalize.py`: strips empty lines; total <10 → `LyricsGenerationError`; `language=="es"` pinned.
- [x] T17 (GREEN, backend) — create `app/projects/draft.py`: `normalize_draft(result)` (strip, total>=10 else `LyricsGenerationError`, force `language="es"`). `python3 -m pytest tests/test_draft_normalize.py`.
- [x] T18 (RED, backend) — `tests/test_lyrics_draft.py`: happy path (mock `lyrics_generate`, occasion="personalizada", story+idea); 404 unknown id; 503 all-providers-fail; 503 <10-line draft.
- [x] T19 (GREEN, backend) — `app/projects/router.py`: `POST /{id}/lyrics-draft` — `store.get_project`→404; build `story`+`idea`; call `lyrics_generate(...)` with `occasion="personalizada"`; route-level `try/except LyricsGenerationError`→503 `"all LLM providers unavailable"`; `normalize_draft`. `python3 -m pytest tests/test_lyrics_draft.py`.
- [x] T20 (RED, backend) — `tests/test_worker.py`: preview/final `GenerateRequest` includes `idea=project.get("idea")`.
- [x] T21 (GREEN, backend) — `app/projects/__init__.py` add `idea=project.get("idea")` to `create_preview_job`/`create_final_job` GenerateRequest + metadata; `app/jobs/worker.py` thread `params.idea` → `lyrics_generate`. `python3 -m pytest tests/test_worker.py`.
- [x] T22 (RED, frontend) — implemented in POSCuentasCorrientes repo: autodraft fills fragments via replaceFragments; 503 keeps fragments, stops loading, no double-submit.
- [x] T23 (GREEN, frontend) — implemented in POSCuentasCorrientes repo: `LyricsDraftResponse` in models.ts, `lyricsDraft()` in canciones.service.ts, idea textarea + "Autogenerar letra" + draft→fragments mapping in create-project.component.ts.

## Phase 3: Verification

- [x] T24 — Full backend: `python3 -m pytest` (377 passed, 5 pre-existing infra failures); `ruff check .` (95, net -2 vs 97 baseline); `black . --check` (new files formatted); `mypy .` (16, net -1 vs 17 baseline).
- [x] T25 — Full frontend: **implemented in POSCuentasCorrientes repo** — module jest green (88 passed, 7 suites), tsc clean. Production build BLOCKED by pre-existing `preview.component.ts:70` null-safety error (baseline reference-song-style commit `2895148`, not part of this change).
- [ ] T26 — Staging verify: **pending deploy; `/api/voices`, 422, idea autodraft, reference-song on staging**

## Gate Findings Resolved

1. **Legacy duo/children** → T7/T8 normalize at read time (map `duo`→`female`, `children`→`es-espana-child`) so `create_preview_job`/`create_final_job` rebuilds never 500.
2. **LyricsGenerationError→503** → T18/T19 route-level mapping (no global handler); test asserts 503 on all-provider-fail and <10-line draft.
3. **language="es"** → T16/T17 `normalize_draft` pins `language="es"`; RQ-DRAFT-03 asserted.
