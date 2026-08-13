# Proposal: Iterative Draft Edit (Replace Fragments)

## Intent

Allow the "Rehacer" (Redo) button on preview to EDIT an existing project — replacing its fragments instead of creating a new one and duplicating content. Users iterate on a draft without accumulating duplicate fragments or garbled lyrics.

## Scope

### In Scope
- Backend: `PUT /projects/{id}/fragments` endpoint (DELETE-all + INSERT-set in one transaction) + store fn `replace_fragments` + pytest tests
- Frontend: `edit/:id` route → `CreateProjectComponent` in edit mode; `getProject(id)` prefill (model + fragments + reference_audio_url); onSubmit branch to new endpoint + `updateProject`
- Wire "Rehacer" button to navigate to `/canciones/edit/{id}`

### Out of Scope
- `POST /api/generate` (legacy) — untouched
- Checkout / download / payment flow
- `POST /api/projects` create flow
- Uploading a reference audio in edit mode (preserve-only display)

## Capabilities

### New Capabilities
None — no new capability introduced.

### Modified Capabilities
- `song-projects`: adds edit workflow requirements (RQ-DIT-01..05) to the existing project lifecycle capability.

## Approach
- Backend: reuse `store.py:get_project`/`add_fragment`; new `replace_fragments(project_id, fragments)` running `DELETE FROM fragments WHERE project_id=?` + INSERT loop inside `async with connection` (single SQLite transaction).
- Frontend: inject `ActivatedRoute` into `CreateProjectComponent`, read `:id`, fetch + populate on init, branch `onSubmit` (create vs edit).
- Tests: backend 2 (replace happy-path + status-gate 409), frontend 2 (edit-mode route + Rehacer navigation).

## Requirements

- **RQ-DIT-01**: `PUT /projects/{id}/fragments` accepts `fragments: string[]` → DELETE-all + INSERT-set in one transaction.
- **RQ-DIT-02**: Backend returns 409 if project status ∈ {paid, completed} (delivered songs are not editable).
- **RQ-DIT-03**: Frontend `CreateProjectComponent` detects `:id` route param → edit mode.
- **RQ-DIT-04**: In edit mode, `getProject(id)` populates `model` + `fragments[]` + preserves `reference_audio_url`.
- **RQ-DIT-05**: "Rehacer" in preview navigates to `/canciones/edit/{project.id}`, not `/canciones/create`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/api/projects.py` | Modified | Add `PUT /projects/{id}/fragments` route + status gate |
| `backend/app/store.py` | Modified | Add `replace_fragments` store fn |
| `backend/tests/` | Modified | 2 pytest tests |
| `frontend/src/app/canciones-personalizadas/create-project.component.ts` | Modified | Edit-mode support + submit branch |
| `frontend/src/app/canciones-personalizadas/.../preview.component.ts` | Modified | Rehacer → `/canciones/edit/{id}` |
| `frontend/src/app/canciones-personalizadas/.../routing` | Modified | Add `edit/:id` route |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SQLite transactionality with aiosqlite | Med | Use `async with connection`; test atomic replace |
| Status gate 409 needs paid/completed fixture | Med | Dedicated fixture in pytest |
| Edit mode clears old fragments on fetch | Med | Preserve existing fragments until successful submit |

## Rollback Plan

Revert the frontend routes + button wiring and remove `PUT /projects/{id}/fragments` route + `replace_fragments` store fn. Existing create/append flow (`POST`/`PATCH`) stays intact as fallback.

## Dependencies
- `reference-song-style` change (models.ts, service.ts, create/preview components with `reference_song` + audio upload).

## Success Criteria
- [ ] `PUT /projects/{id}/fragments` atomically replaces all fragments (pytest green).
- [ ] 409 returned for paid/completed projects.
- [ ] `edit/:id` renders `CreateProjectComponent` pre-filled (model, fragments, reference audio preserved).
- [ ] "Rehacer" navigates to edit route and re-submits without duplicating fragments.

## Alternatives
- Append-only: rejected — duplicates fragments and garbles lyrics.
