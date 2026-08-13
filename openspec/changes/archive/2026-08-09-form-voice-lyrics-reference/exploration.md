# Exploration: form-voice-lyrics-reference

## Executive Summary

Three user-requested features for the personalized-song form. Exploration across **both** repos
(backend `CancionesPersonalizadas` + frontend module inside `POSCuentasCorrientes`) reveals:

1. **Voice variety** — REAL gap. Backend voice registry only has `male`/`female`
   (`app/voice/registry.py`). Frontend form hard-codes 4 `<option>` values but sends **raw
   strings** (`male|female|duo|children`); backend validation is a free-text Pydantic field, so
   `duo`/`children` are accepted at the API but **crash at job time** (`build_prompt` raises
   `ValueError` → job fails). Desired voices (español hombre latino, español hombre españa, mujer
   española) do not exist anywhere. No `/voices` endpoint — options are hard-coded in two places
   that drift.
2. **Lyrics auto-generation + "idea" textarea** — REAL gap. No auto-generate button, no
   "idea"/comment field anywhere. Fragments are the only lyric input; the backend already
   accumulates fragments into `story` and runs lyrics generation in the worker, so the plumbing
   exists to add an "idea" input.
3. **Reference song field** — MOSTLY DONE. Backend fully supports `reference_song` +
   `reference_description` (archived change `reference-song-style`), and the frontend **already
   exposes** a free-text `reference_song` input + MP3 audio upload (in-flight, uncommitted, same
   change). The "copy voice/rhythm" semantics already flow to both lyrics and voice prompts.

Key risk: planning on top of uncommitted work in both repos (auth rewrite in backend,
reference-song-style in frontend).

---

## Current State

### Backend (`CancionesPersonalizadas`)

- **Voice model**: `app/voice/registry.py` defines `VOICE_REGISTRY` with exactly two entries:
  `female` ("Voz Femenina") and `male` ("Voz Masculina"). `app/voice/__init__.py` exposes
  `get_available_voices()` and `build_prompt()`. `build_prompt` raises `ValueError` for unknown
  voice IDs. Startup validation in `app/main.py` → `validate_registry()`.
- **Voice validation**: NONE at the API boundary. `GenerateRequest.voice` and
  `SongProjectCreate.voice` / `SongProjectUpdate.voice` are free `str` fields. Invalid voice is
  only caught inside the worker via `build_prompt` → job `failed`. **No `/voices` endpoint exists**
  (frontend hard-codes its own list).
- **Lyrics flow**: `app/lyrics/prompts.py::build_user_prompt` takes `recipient/relationship/
  occasion/genre/mood/story/reference_song/reference_description`. `story` is the free-text idea
  seed (max 2000). `app/lyrics/providers.py` runs the multi-provider LLM call. `app/jobs/worker.py`
  and `app/projects/__init__.py::project_worker` call `lyrics_generate(...)` with `story=params.story`.
- **Reference song**: fully wired. `GenerateRequest`, `SongProjectCreate`, `SongProjectUpdate` all
  have `reference_song` + `reference_description`. Stored in `projects` table, passed through
  `create_preview_job`/`create_final_job` via metadata, and consumed by `project_worker`
  (both lyrics and `build_prompt`). Tests: `tests/test_worker_reference.py`.

### Frontend module (`POSCuentasCorrientes/src/app/canciones-personalizadas/`)

- **Voice selector**: `create/create-project.component.ts` template hard-codes 4 options:
  `male` (Voz masculina), `female` (Voz femenina), `duo` (Dúo), `children` (Voz infantil). Sent as
  raw string in `CreateProjectRequest.voice`. `duo`/`children` are NOT in the backend registry → will
  fail at job time.
- **Fragments**: collected in `fragments[]` array of `{id, text}`, added one-by-one (PATCH on create)
  or replaced (PUT `/fragments` on edit). No auto-generate, no idea/comment textarea.
- **Reference song**: ALREADY present — `reference_song` free-text input (lines 67-80) + MP3 upload
  (lines 82-104). `models.ts` has `reference_song`/`reference_description`/`reference_audio_url`.
  Service has `uploadReferenceAudio`, `replaceFragments`. Preview displays `reference_song` and
  `reference_description`.
- **Routes**: `canciones.routes.ts` has `create`, `edit/:id`, `preview/:id`, `checkout/:id`,
  `download/:id`, `landing`.

---

## Affected Areas

### Backend
- `app/voice/registry.py` — add new voice entries (español hombre latino, español hombre españa,
  mujer española, etc.); source of truth for labels + prompt descriptors.
- `app/models.py` — (voice variety) could add an enum/validator; (idea) add `idea` field to
  `GenerateRequest`, `SongProjectCreate`, `SongProjectUpdate`, `SongProjectResponse`.
- `app/projects/store.py` — persist `idea` in `projects` table + schema/migration.
- `app/projects/router.py` — optionally expose `GET /api/voices`; thread `idea`.
- `app/projects/__init__.py` — pass `idea` into `GenerateRequest` when creating preview/final.
- `app/jobs/worker.py` + `app/lyrics/prompts.py` — (auto-generate) add a dedicated lyrics-only
  endpoint and/or merge `idea` into `story`.
- `app/main.py` — wire new endpoints; keep `validate_registry`.

### Frontend (`canciones-personalizadas/`)
- `models.ts` — add `idea?: string`; possibly type `voice` as union / add voices list type.
- `create/create-project.component.ts` + template — replace hard-coded voice `<option>`s with
  data-driven list (ideally fetched from backend); add "idea" textarea + "Auto-generar letra"
  button; render generated lyrics into fragments/editor.
- `canciones.service.ts` — add `getVoices()` and a lyrics auto-generate call.
- `create/create-project.component.spec.ts` — extend for new fields/actions (existing patterns use
  `jest.Mock` service spies + zoneless `provideZonelessChangeDetection`).

---

## Approaches

### A. Voice variety
1. **Extend backend registry + add `/voices` endpoint; frontend fetches it** — single source of
   truth, no drift. Requires a new endpoint, frontend service method, and swapping hard-coded options.
2. **Extend registry + keep hard-coded frontend options in sync manually** — minimal backend change,
   but two lists continue to drift; the existing `duo`/`children` mismatch proves this fails.

Recommended: A1. Add `es-latino-male`, `es-espana-male`, `es-espana-female` (and keep `male`,
`female`), expose `GET /api/voices` returning `{id, label}`, frontend renders options from it.

### B. Lyrics auto-generation + idea
1. **Add `idea` field to project + a lyrics-only auto-generate endpoint** — user types idea, clicks
   "auto-generar", backend returns draft lyrics (verses/chorus) that populate the fragments editor
   for review before preview. Clean separation; reuses `lyrics_generate`.
2. **Auto-generate only at preview time** (merge `idea` into `story`) — smallest change, but no
   editable draft lyrics step; user can't see/correct lyrics before committing.

Recommended: B1 — matches "generator produces the likely song" + editable review. Store `idea` on
the project, add `POST /api/projects/{id}/lyrics-draft` (or reuse `/generate`) returning structured
lyrics; frontend button fills fragments.

### C. Reference song
- Already implemented end-to-end. Remaining work: none for the "name field" itself. Optional polish:
  verify `duo`/`children` removal while touching voice (they don't exist in the registry).

---

## Recommendation

First slice: **(1) voice variety** (registry entries + `/voices` endpoint + frontend data-driven
select, remove `duo`/`children`) + **(3) confirm reference-song already shipped** (no new code, only
test/verify). **Second slice: (2) lyrics auto-generate + idea** (backend `idea` field + lyrics-draft
endpoint, frontend textarea + button + draft → fragments). Keep reference-song as "done" and just
guard against drift with uncommitted work.

## Risks

- **Uncommitted backend work** (`git status`): modified `app/auth/*` (middleware/router/dependencies),
  `app/jobs/worker.py`, `app/models.py`, `app/projects/router.py`, `app/projects/store.py`, specs,
  `tests/*`. Worker/models/projects changes are the reference-song-style change in flight. Auth
  rewrite is separate. **Do not build on an unknown commit** — plan deltas against current working
  tree.
- **Uncommitted frontend work**: whole `canciones-personalizadas/` module has reference-song-style in
  flight (create/service/models/preview/routes + spec folder). The voice `duo`/`children` mismatch is
  a pre-existing latent bug — decide whether this change fixes it (recommended) or leaves it.
- **Voice options are duplicated & can drift** — backend registry vs. frontend hard-coded list.
- **`duo`/`children` currently break jobs** if selected (invalid at `build_prompt`).
- Lyrics draft endpoint exposes LLM cost/latency; needs its own error handling (providers already
  cascade + 503 on all-fail).

## Ready for Proposal
Yes — scope clearly separable. Voice variety + reference-song verify = slice 1; lyrics
auto-generate + idea = slice 2. The orchestrator should tell the user that reference-song is already
shipped (frontend field exists) and that `duo`/`children` voice options are currently broken on the
backend.
