# Apply Progress: Iterative Draft Edit (Replace Fragments)

## Status: ALL DONE (14/14 tasks complete)

> Reconciliation note: `sdd-apply` marked every task `[x]` in `tasks.md` but did not persist a separate `apply-progress.md` during the phase. This file is generated at archive time for traceability, per the verify-report SUGGESTION. Completion is proven by the fully-checked `tasks.md`, the backend apply result (#3099, 2/2 tests), the frontend apply result (#3100, 79/79 jest + tsc clean), and the PASS verify-report (#3103). This is an exceptional mechanical reconciliation — no unchecked implementation tasks remain.

## Phases Applied

### Phase 1-3: Backend
- 1.1, 1.2 RED tests created in `tests/test_projects/test_replace_fragments.py` ✅
- 2.1 `app/models.py` → `ReplaceFragmentsRequest` ✅
- 2.2 `app/projects/store.py` → `COMPLETED_STATUSES` + `replace_fragments` (explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK, single txn) ✅
- 2.3 `app/projects/router.py` → `PUT /projects/{id}/fragments` (404/409/200) ✅
- 3.1 pytest suite green ✅

### Phase 4-6: Frontend
- 4.1-4.3 RED specs (service, create edit-mode, preview Rehacer) ✅
- 5.1 `canciones.service.ts` → `replaceFragments` ✅
- 5.2 `canciones.routes.ts` → `edit/:id` ✅
- 5.3 `create-project.component.ts` edit mode + `submitEdit` ✅
- 6.1 jest canciones green (79 passed) ✅
- 6.2 `build:prod` (tsc) clean ✅

## Files Changed
- Backend: `app/models.py`, `app/projects/store.py`, `app/projects/router.py`, `tests/test_projects/test_replace_fragments.py`
- Frontend: `canciones.service.ts`, `canciones.routes.ts`, `create-project.component.ts`, `preview.component.ts`, 3 spec files