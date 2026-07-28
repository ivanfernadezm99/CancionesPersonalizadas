## Exploration: Proyectos Iterativos (Iterative Song Projects)

### Current State

The current system is a **single-shot** generation pipeline:

```
POST /api/generate → job queued → lyrics_generated → music_generated → processing → complete
```

**Architecture snapshot:**

| Component | File | Role |
|-----------|------|------|
| Endpoints | `app/main.py` | `POST /api/generate`, `GET /api/status/{id}`, `GET /api/stream/{id}` |
| Request model | `app/models.py` | `GenerateRequest` — recipient, relationship, occasion, genre, mood, story (optional), voice |
| Job store | `app/jobs/store.py` | SQLite `jobs` + `job_transitions` tables in `jobs.db` |
| Worker | `app/jobs/worker.py` | Orchestrates lyrics→music→extend→complete |
| Lyrics | `app/lyrics/` | Multi-provider cascade (OpenAI → Gemini → OpenRouter) |
| Voice prompt | `app/voice/__init__.py` | `build_prompt(voice_id, genre, mood)` → Lyria 3 prompt string |
| Music gen | `app/music/openclaw.py` | `OpenClawClient.invoke()` → hardcodes `"model": "google/lyria-3"` |
| Duration ext | `app/music/durext.py` | `extend_duration()` → crossfade-loop to 150s target |
| State machine | `app/jobs/state.py` | 5 states: queued → lyrics_generating → music_generating → processing → complete/failed |

**Key finding:** The `app/projects/` module exists but is **only partially wired**:
- `app/projects/store.py` — FULLY IMPLEMENTED: schema (projects, story_fragments, project_jobs tables), CRUD, `get_accumulated_story()`, `link_project_job()`
- `app/models.py` — ALL project models already defined: `SongProjectCreate`, `SongProjectUpdate`, `StoryFragmentAdd`, `SongProjectResponse`, etc.
- `app/projects/__init__.py` — **EMPTY** (only a docstring)
- `app/main.py` — **NO** project endpoints registered
- `app/voice/__init__.py` — **NO** reference_song support in `build_prompt()`

So roughly **50% of the data layer is already built** — what's missing is the API layer, wiring, and model parameterization.

---

### Affected Areas

| File | Why affected |
|------|-------------|
| `app/main.py` | Need new endpoints: `POST /api/projects`, `PATCH /api/projects/{id}`, `POST /api/projects/{id}/preview`, `POST /api/projects/{id}/final`, `GET /api/projects/{id}` |
| `app/projects/__init__.py` | Must expose CRUD + generation orchestration for projects |
| `app/music/openclaw.py` | `invoke()` hardcodes model name — must accept `model` parameter |
| `app/voice/__init__.py` | `build_prompt()` must accept `reference_song` to enrich Lyria 3 prompt |
| `app/lyrics/prompts.py` | `build_user_prompt()` may need `reference_song` for style-aware lyrics |
| `app/jobs/worker.py` | Must be callable from project flow OR a new project worker is needed |
| `app/jobs/state.py` | Current 5-state machine works for single-shot; may need new statuses for preview vs final |
| `app/models.py` | Already has all models — only minor adjustments possible |
| `app/projects/store.py` | Already complete — only minor adjustments if needed |
| `app/config.py` | May need to add `PREVIEW_TARGET_SECONDS` / `FINAL_TARGET_SECONDS` config |

---

### OpenClaw Model Availability (confirmed live)

```
Provider: google (default lyria-3-clip-preview)
Models:
  - lyria-3-clip-preview  → mp3 only (~30s preview)
  - lyria-3-pro-preview   → mp3/wav (full song, 2+ min)
```

**⚠️ Note:** Current code uses `"model": "google/lyria-3"` which does NOT match any available model name. This may:
- Work via OpenClaw normalization/alias
- Or be silently falling back to `lyria-3-clip-preview` (the default)

This needs to be corrected regardless of the projects feature.

---

### Approaches

#### 1. Reuse existing jobs table + add project tables (same DB)

**Description:** Keep the existing `jobs` table for individual generation jobs. The existing `projects`, `story_fragments`, and `project_jobs` tables (already in `app/projects/store.py`) link projects to their child jobs. Preview and final generations each create a job row in `jobs`, linked via `project_jobs`.

**Data flow:**
```
Project (projects table)
  ├── story_fragments (accumulated over time via PATCH)
  ├── preview_job → jobs table (model: lyria-3-clip-preview, no duration ext)
  └── final_job → jobs table (model: lyria-3-pro-preview + duration extension)
```

- Pros: Already 50% implemented; reuses existing state machine, cleanup, streaming; no migration needed; FK integrity enforced
- Cons: Project endpoints still need to be built; project_worker needed alongside job_worker
- Effort: **Medium**

#### 2. Separate projects DB

**Description:** Create a separate `projects.db` with its own schema, independent of the jobs system. Projects track their own state, and generation jobs are referenced but not tightly coupled.

- Pros: Cleaner separation of concerns; projects table doesn't depend on jobs schema
- Cons: More code (separate connections, cleanup, state tracking); already had a partially implemented shared-DB approach; extra complexity for no clear benefit
- Effort: **Medium-High**

#### 3. Standalone worker flow for projects (no jobs table reuse)

**Description:** Each project preview/final call creates its own self-contained async task that bypasses the jobs table entirely. Projects store only metadata and output paths.

- Pros: Simplest initial implementation
- Cons: No status tracking; no replay/history; no cleanup integration; diverges from existing architecture; loses job polling/streaming capability
- Effort: **Low-Medium** (but high risk)

---

### Recommendation

**Approach 1 — Reuse existing jobs table + project tables (same DB).**

Rationale:
1. The projects store is **already fully implemented** (`app/projects/store.py` has full CRUD, schema, FK links to jobs)
2. The Pydantic models are **already defined** (`app/models.py` lines 87-151)
3. Reusing the jobs table means existing `GET /api/status/{id}`, `GET /api/stream/{id}`, cleanup scheduler, and state machine all work FOR FREE
4. OpenClaw model switching is trivial — just parameterize `invoke(lyrics, prompt, model="...")`
5. Reference song is just an additional field in the voice prompt

**What remains to build:**

| Component | Status | Effort |
|-----------|--------|--------|
| `app/projects/__init__.py` — orchestration layer | ❌ Missing | 1 day |
| `app/main.py` — project endpoints (5-6 routes) | ❌ Missing | 1 day |
| `app/music/openclaw.py` — model parameter | ⚠️ Hardcoded | 1-2 hrs |
| `app/voice/__init__.py` — reference_song in prompt | ❌ Missing | 2-3 hrs |
| `app/lyrics/prompts.py` — reference_song in lyrics prompt | ❌ Missing | 2-3 hrs |
| `app/jobs/worker.py` — project-aware worker | ❌ Missing | 1 day |
| `app/voice/registry.py` — enhance with reference | ⚠️ Needs wiring | 1-2 hrs |
| Tests | ❌ Missing | 1 day |

**Total estimated effort: ~4-5 days** (50% of which is already done in data layer)

---

### Old `/api/generate` Endpoint

**Recommendation: KEEP it.** Don't deprecate.

- The single-shot flow is useful for quick testing, debugging, and a simpler API
- The projects flow is additive — it doesn't replace one-shot generation
- Reuse the same worker internals; just add a new entry point
- Mark it as "legacy" in docs if desired, but don't remove

---

### Risks

1. **Model name mismatch**: Current code uses `google/lyria-3` which doesn't match any available model (`lyria-3-clip-preview`, `lyria-3-pro-preview`). Must fix before or during this change.

2. **`lyria-3-pro-preview` not tested**: The exploration confirmed it exists, but no one has generated a full song with it. It may have different latency, output quality, or limitations.

3. **Duration extension quality**: The existing `extend_duration()` uses crossfade looping. For previews (30s), no extension needed. For finals, the `lyria-3-pro-preview` output length is unknown — may already produce 2+ min, or may need significant extension.

4. **Accumulated story length**: Multiple PATCH calls could build a very long story fragment. Need to ensure the concatenation doesn't exceed the LLM context window or the total 2000-char limit in the prompt.

5. **Reference song prompt engineering**: Passing a reference song name to Lyria 3 via prompt may or may not influence the output effectively. This is prompt-engineering territory — may need experimentation.

6. **Existing tests**: All existing tests for jobs, worker, lyrics, etc. must continue passing. The project changes are additive.

---

### Ready for Proposal

**Yes.** The codebase is well-understood, the data layer is 50% complete, and the technical path is clear. The orchestrator should tell the user:

> The exploration is complete. The projects data layer (models, DB schema, store) is already 50% implemented — what's missing are the API endpoints, the orchestration layer in `app/projects/`, wiring `reference_song` into prompts, and parameterizing the OpenClaw model field. Estimated effort: **4-5 days**. The old single-shot endpoint should be kept alongside the new project flow. The model name `google/lyria-3` currently used may be wrong (available models are `lyria-3-clip-preview` and `lyria-3-pro-preview`) — this should be fixed regardless.
