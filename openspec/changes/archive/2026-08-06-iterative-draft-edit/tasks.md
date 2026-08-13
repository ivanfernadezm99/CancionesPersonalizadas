# Tasks: Iterative Draft Edit (Replace Fragments)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 (backend ~60, frontend ~90) |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR per repo (backend 1, frontend 1) |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend replace endpoint | PR 1 (backend) | store + model + router + pytest |
| 2 | Frontend edit workflow | PR 2 (frontend) | service + route + component edit mode + Rehacer + jest |

Both units are per-repo and can merge independently (frontend tests use mocks, no backend dependency at test time).

## Phase 1: Backend TDD (Red)

- [x] 1.1 Create `tests/test_projects/test_replace_fragments.py` — RED test: PUT happy path replaces fragments `["viejo"]` → `["nuevo","otro"]`, asserts 200 then GET returns exactly those 2 in sort_order; empty list returns 200 with `[]` (RQ-DIT-01)
- [x] 1.2 Add RED test: `status: paid` → 409 Conflict and fragments unchanged; `status: draft` → 200 (RQ-DIT-02)

## Phase 2: Backend Implementation (Green)

- [x] 2.1 `app/models.py` — add `ReplaceFragmentsRequest` Pydantic model with `fragments: list[str]`
- [x] 2.2 `app/projects/store.py` — add `COMPLETED_STATUSES = frozenset({"paid","completed"})` and `replace_fragments(project_id, fragments, *, db_path)` returning `(found, gated, updated_project)`; DELETE-all + INSERT loop (sort_order from 1) in one `async with connection` txn; status gate inside
- [x] 2.3 `app/projects/router.py` — add `PUT /projects/{project_id}/fragments`; `found=False` → 404, `gated` → 409, else 200 via `_project_to_response` (D1/D2/D5: no auth, follow existing pattern)

## Phase 3: Backend Verify

- [x] 3.1 Run pytest on `tests/test_projects/` + full suite — all green, no regressions in create/append/backward-compat

## Phase 4: Frontend TDD (Red)

- [x] 4.1 `canciones.service.spec.ts` — RED test: `replaceFragments(id, fragments)` calls `http.put<SongProjectResponse>('/projects/{id}/fragments', {fragments})`
- [x] 4.2 `create/create-project.component.spec.ts` — RED test: `edit/:id` route param detected → edit mode fetches project via `getProject` and populates model + fragments, preserves `reference_audio_url`, existing fragments kept until submit (RQ-DIT-03/04)
- [x] 4.3 `preview/preview.component.spec.ts` — RED test: "Rehacer" binding targets `/canciones/edit/{project.id}`, not `/canciones/create` (RQ-DIT-05)

## Phase 5: Frontend Implementation (Green)

- [x] 5.1 `canciones.service.ts` — add `replaceFragments(id: string, fragments: string[]): Observable<SongProjectResponse>` using `this.http.put(...)`
- [x] 5.2 `canciones.routes.ts` — add `{ path: 'edit/:id', loadComponent: CreateProjectComponent }`
- [x] 5.3 `create/create-project.component.ts` — inject `ActivatedRoute`; `ngOnInit` reads `:id`, fetches + populates model/fragments/`reference_audio_url`; `onSubmit` branch: edit → `replaceFragments` + `updateProject` → navigate `preview/:id`; keep `referenceAudioFile=null` (display-only, no re-upload)

## Phase 6: Frontend Verify

- [x] 6.1 Run Jest for canciones specs — green
- [x] 6.2 Run `build:prod` (tsc) — no type errors
