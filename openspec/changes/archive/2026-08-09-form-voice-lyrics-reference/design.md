# Design: Form Voice Variety, Lyrics Idea + Autodraft, Reference Song Delivery

## Technical Approach

Two additive slices on the iterative-project API, plus a reference-song verify step.
**Slice 1**: extend `VOICE_REGISTRY` to 7 entries, add a JWT-protected `GET /api/voices`
single source of truth, fail-fast Pydantic voice validation at the request boundary, and
make the frontend voice select data-driven (drop `duo`/`children`). **Slice 2**: persist an
optional `idea` field and add `POST /api/projects/{id}/lyrics-draft` that reuses the existing
`lyrics_generate` cascade. Reference-song needs no new code — only baseline-commit, push, and
verify on staging (Suno-gated, see D6).

The `idea` seed and the lyrics-draft share one plumbing change: thread `idea` through
`lyrics_generate` → `build_user_prompt` (RQ-LYR-07, RQ-DRAFT-02). No provider cascade is
duplicated.

## Architecture Decisions

| # | Decision | Options | Choice | Rationale |
|---|----------|---------|--------|-----------|
| D1 | Voice entries | — | 7 per RQ-VOI-01 table (add `es-latino-male`, `es-espana-male`, `es-espana-female`, `es-latina-female`, `es-espana-child`) | Spec-locked; keep `male`/`female` for backward compat; `gender` accepts `"child"` (free `str` field). **Keep existing labels `Voz Femenina`/`Voz Masculina`** — tests assert exact strings |
| D2 | `/voices` route location | new `app/voice/router.py` vs projects router | **New `app/voice/router.py`** (`prefix="/api"`) | Spec path is top-level `/api/voices`; projects router prefix is `/api/projects` |
| D3 | `/voices` auth | public vs JWT-protected | **JWT-protected** (NOT in `PUBLIC_ROUTES`) | Accurate premise: `JWTAuthMiddleware` blocks every `/api/*` path (only `PUBLIC_ROUTES` are exempt); the create form is UNGUARDED (`authGuard` only on `checkout/:id`,`download/:id`) but a logged-out user cannot persist any project either (all `/api/projects/*` also 401). So `/voices` is JWT-protected like its sibling project routes; frontend fallback (D4) covers 401 |
| D4 | `/voices` 401 fallback | curated mirror list vs empty select | **Curated fallback mirroring the 7-entry registry, fallback-only** | Satisfies RQ-VOICE-01 (not "its own options"): the select is fed by `getVoices()`; on 401/failure it falls back to a literal mirror of the 7 registry `{id,label}` pairs, commented `// fallback-only — must mirror VOICE_REGISTRY`, and a test asserts the fallback id set equals the registry id set (no `duo`/`children`). Keeps form usable on degraded auth |
| D5 | Voice validation | validator vs enum vs worker | **`@field_validator` on `GenerateRequest.voice`, `SongProjectCreate.voice`, `SongProjectUpdate.voice`** | Existing `ValidationError` handler → 422; validator **must `return v if v is not None`** (pydantic v2 runs validators on `None` too, else every PATCH without `voice` 422s); lazily imports `get_voice` (avoids circular import models↔registry) |
| D6 | Reference-song verify | scope to suno vs document | **Provider-gated: MP3 `reference_audio_url` persists only when `MUSIC_PROVIDER=="suno"`** (`app/projects/router.py:301-303`; default `openclaw` at `app/config.py:46`) | RQ-REF-01's "stored `reference_audio_url` retrievable" scenario passes only in Suno mode; verify plan must set `MUSIC_PROVIDER=suno` or mark that scenario provider-gated. Reference-song fields (`reference_song`/`reference_description` + payload) are provider-independent and verify on staging regardless |
| D7 | `idea` merge | separate `idea` param vs concat into `story` at caller | **Add `idea: str \| None` param to `lyrics_generate` + `build_user_prompt`; add `idea: str \| None` to `GenerateRequest`** | Satisfies RQ-LYR-07 as distinct seed; fragments stay `story`; matches existing kwargs style. Draft reads `project.get("idea")` (store uses `SELECT *`) |
| D8 | Draft endpoint placement | new router vs projects router | **Projects router** `POST /{project_id}/lyrics-draft` | Operates on a project (404 pattern already there); reuses `store` + `lyrics_generate` |
| D9 | Draft output validation | post-process helper vs raw result | **`LyricsResult` response_model + normalization helper `app/projects/draft.py`** | `LyricsResult` enforces verse/line list min lengths but NOT total≥10 nor non-empty strings; helper strips each line and raises `LyricsGenerationError` (→503) if total lines < 10 — satisfies RQ-DRAFT-03 without new schema |
| D10 | `idea` migration | new migration vs idempotent ALTER | **Idempotent `ALTER TABLE projects ADD COLUMN idea TEXT`** in `init_schema` (mirrors `reference_description`) | No data migration; nullable column |
| D11 | Baseline commits | one combined vs separate | **Two separate baseline commits (one per in-flight concern): (a) reference-song-style, (b) auth rewrite** | Both touch overlapping backend files (`models.py`, `projects/router.py`, `projects/store.py`); separate commits give apply clean per-slice diffs. Asymmetry: backend `reference-song-style` is archived (`openspec/changes/archive/2026-08-06-reference-song-style/`) while frontend's `openspec/changes/reference-song-style/` is an untracked active change dir — baseline the backend from its archive state, frontend from its working tree |

## Data Flow

```
Slice 1:
GET /api/voices ── app/voice/router.py ── get_available_voices() ── VOICE_REGISTRY (7)
Frontend select ── getVoices() ──(401/fail)→ curated mirror fallback ── model.voice
POST /projects {voice} ── field_validator get_voice() ── 422 | pass

Slice 2 — lyrics-draft exact mapping (NO occasion column; hard-coded):
POST /projects/{id}/lyrics-draft
   ├─ store.get_project(id) → 404 if missing
   ├─ story = get_accumulated_story(id) ; idea = project.get("idea")
   └─ lyrics_generate(recipient=project["recipient"],
        relationship=project["relationship"], occasion="personalizada",
        genre=project["genre"], mood=project["mood"], story=story,
        idea=idea, reference_song=project.get("reference_song"),
        reference_description=project.get("reference_description"))
        └─ build_user_prompt(+idea) ── cascade_providers ── LyricsResult
             └─ draft.normalize_draft(result)  (strip + total>=10 else →503)
             └─ all providers fail → LyricsGenerationError → 503

Normal path (preview/final): create_preview_job/final_job add idea=project.get("idea")
  to GenerateRequest; project_worker passes idea=params.idea to lyrics_generate.
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/voice/registry.py` | Modify | Add 5 entries (D1); keep `Voz Femenina`/`Voz Masculina` labels |
| `app/voice/router.py` | Create | `GET /voices` → `list[VoiceInfo{id,label,gender}]` |
| `app/main.py` | Modify | `include_router(voice_router)` |
| `app/models.py` | Modify | `VoiceInfo`; `idea` on `GenerateRequest`/`SongProjectCreate/Update/Response`; `_validate_voice` validators (skip `None`, D5) |
| `app/projects/store.py` | Modify | `idea` ALTER in `init_schema`; INSERT + `val is not None` update loop; `SELECT *` already returns `idea` |
| `app/projects/router.py` | Modify | `POST /{id}/lyrics-draft` (D8/D9); `_project_to_response` adds `idea` |
| `app/projects/draft.py` | Create | `normalize_draft(result)` — strip lines, raise `LyricsGenerationError` if total < 10 (RQ-DRAFT-03) |
| `app/projects/__init__.py` | Modify | Pass `idea=project.get("idea")` into `GenerateRequest` (preview+final); `project_worker` threads `params.idea` |
| `app/lyrics/__init__.py` | Modify | `generate(..., idea=None)` → `build_user_prompt` |
| `app/lyrics/prompts.py` | Modify | `build_user_prompt(..., idea=None)` → "Idea principal" section |
| `tests/test_voice_registry.py` | **Modify** | Update `len(VOICE_REGISTRY) == 7`; add per-voice assertions (labels `Voz Femenina`/`Voz Masculina` casing); assert no `duo`/`children` |
| `tests/test_voice_router.py`, `test_lyrics_draft.py`, `test_idea.py`, `test_draft_normalize.py` | Create | Slice-specific tests (TDD) |
| Frontend `canciones.service.ts` | Modify | `getVoices()`, `lyricsDraft(id)`, `idea?` in payloads |
| Frontend `models.ts` | Modify | `VoiceInfo`, `LyricsDraftResponse`, `idea?` |
| Frontend `create-project.component.ts` + template | Modify | data-driven voice select (drop `duo`/`children` options, D4 mirror); idea textarea + "Autogenerar letra" + loading; draft→fragments |

## Interfaces / Contracts

```python
class VoiceInfo(BaseModel):
    id: str; label: str; gender: str

@router.get("/voices", response_model=list[VoiceInfo])
# POST /projects/{id}/lyrics-draft → response_model=LyricsResult; 503 on LyricsGenerationError
# GenerateRequest.idea: str | None = None
```

Frontend `LyricsDraftResponse`: `{verses:[{number,lines[]}], chorus:{lines[]}, bridge?:{lines[]}, title_suggestion, language}`.
Draft→fragments: each verse → `"Estrofa {n}\n"+lines`; chorus → `"Estribillo\n"+lines`; bridge → `"Puente\n"+lines`.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit (pytest) | `/voices` returns 7 exact entries; validation 422 on `duo`/`children`/unknown (lists valid IDs); `es-latino-male` accepted; PATCH without `voice` does NOT 422 (D5); `build_user_prompt` includes/omits idea; idea persists null/update; `normalize_draft` rejects <10 total, strips empties; registry count==7 | `test_voice_*.py`, `test_idea.py`, `test_draft_normalize.py`, extend `test_worker` |
| Integration | lyrics-draft happy path (mock `lyrics_generate`), 404, 503 on all-provider fail and on <10-line draft | `test_lyrics_draft.py` (respx/httpx) |
| Frontend (jest, zoneless) | voices fetched & rendered from API, mirror fallback on 401, no `duo`/`children`; autodraft fills fragments, 503 shows error without clearing, loading disables double-submit | `create-project.component.spec.ts`, `canciones.service.spec.ts` |

## Migration / Rollout

Idempotent `idea` column (no data migration). **Two baseline commits** (reference-song-style, then auth rewrite) in both repos before apply. Feature-branch per slice: **Slice 1** (voice + `/voices` + reference-song verify) → **Slice 2** (idea + lyrics-draft); chained PRs, each under budget. Rollback: revert slice PR; `male`/`female` retained so old projects stay valid; `idea` nullable and draft endpoint additive. `PATCH {"idea": null}` is a no-op (existing `val is not None` loop) — **clearing `idea` via PATCH is out of scope** (spec requires null only on create/absence; new value sets via PATCH).

## Open Questions

- [ ] Confirm baseline-committing the backend **auth rewrite** is safe to land as-is (out of scope; apply must not include it in slice diffs).
- [ ] Confirm `es-espana-child` voice actually usable in Lyria (spec mandates it; `gender="child"` is a registry-only value).
