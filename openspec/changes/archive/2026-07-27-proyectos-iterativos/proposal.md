# Proposal: Iterative Song Projects

## Intent

Users need to iterate on song ideas before committing. Current single-shot flow has no way to accumulate story fragments, preview melody, or reference a known song for style.

## Scope

**In:** Project CRUD (create, update fragments, fetch), 30s preview (`lyria-3-clip-preview`), final 2+ min (`lyria-3-pro-preview` + extension), reference song in prompts, model param in OpenClaw, reuse existing jobs infrastructure, keep `POST /api/generate`.

**Out:** Listing/search, deletion, audio analysis, concurrent previews, web UI.

## Capabilities

**New:** `song-projects` — lifecycle: CRUD, preview, finalize, fetch.

**Modified:** `job-orchestration` (optional project_id FK), `music-generation` (accepts model param + reference_song), `lyrics-generation` (reference_song in prompt), `voice-configuration` (build_prompt accepts reference_song).

## API Contract

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/projects` | Create project |
| PATCH | `/api/projects/{id}` | Add story fragment |
| POST | `/api/projects/{id}/preview` | 30s clip → job_id |
| POST | `/api/projects/{id}/final` | Full song → job_id |
| GET | `/api/projects/{id}` | Project + jobs |

## Approach

50% done (`app/projects/store.py` + models). Remaining: orchestration layer, 5 routes, model param in OpenClaw, reference_song in voice + lyrics prompts, project-aware worker dispatch. Preview/final create child job rows → existing worker picks them up with correct model. Status/stream work for free.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Model name mismatch | High | Fix to `lyria-3-clip-preview` / `lyria-3-pro-preview` |
| `lyria-3-pro-preview` untested | Medium | Test before release; fallback to preview + extension |
| Story exceeds prompt limits | Medium | Truncate at 2000 chars |
| Reference song ignored by Lyria 3 | Medium | Best-effort; document as experimental |

## Rollback Plan

Routes are additive — revert by removing from `app/main.py`. Model param is backward-compatible. No schema migration. `POST /api/generate` untouched.

## Dependencies

`app/projects/store.py` (complete), OpenClaw models (`lyria-3-clip-preview`, `lyria-3-pro-preview`).

## Success Criteria

- [ ] `POST /api/projects` → 201 with project ID
- [ ] `PATCH` accumulates fragments
- [ ] `/preview` → job_id with clip model
- [ ] `/final` → job_id with pro model
- [ ] Existing `POST /api/generate` unchanged
- [ ] All existing tests pass
- [ ] Reference song in prompts when provided
