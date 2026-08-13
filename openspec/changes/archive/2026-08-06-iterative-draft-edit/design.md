# Design: Iterative Draft Edit (Replace Fragments)

## Technical Approach

Extend the existing `song-projects` lifecycle with an **edit workflow**: a new
idempotent `PUT /projects/{id}/fragments` endpoint that atomically replaces a
draft's story fragments (DELETE-all + INSERT-set in one SQLite transaction), plus
a frontend edit mode that reuses `CreateProjectComponent` and re-routes "Rehacer".

Backend reuses the existing `store.py` transaction pattern (`async with` /
explicit `conn.commit()` inside a `_get_conn` session) and the existing
`_project_to_response` serializer. Frontend reuses `CreateProjectComponent`
(create mode stays byte-for-byte; edit mode adds a route-param branch).

## Architecture Decisions

| # | Decision | Options | Rationale |
|---|----------|---------|-----------|
| D1 | `PUT` (not PATCH) for fragment replace | PATCH (append) vs PUT (full replace) | PATCH already means "append one fragment" (RQ-PRJ-02). PUT signals full-set replacement; idempotent, matches delete+insert semantics. |
| D2 | Status gate in store fn, not router | Router-level vs store-level | Store owns the truth (reads status + writes in same txn); keeps router thin. Router maps store sentinel to 409. |
| D3 | Atomic txn in one `_get_conn` session | Separate DELETE+INSERT conns | Single `async with` conn + one `commit()` → all-or-nothing. If INSERT loop fails, nothing is deleted. |
| D4 | Empty fragments → valid (200, empty array) | Reject empty as 400 | Spec RQ-DIT-01 "replace with empty list" MUST return 200. Model allows `list[str]` min 0. |
| D5 | No auth on new endpoint | Mirror `get_current_user` | **Codebase reality**: `router.py` has NO auth dependency on any endpoint (incl. create/update). Follow existing pattern; flag for future hardening (see Open Questions). |

## Data Flow

```
CreateProjectComponent (edit mode, /canciones/edit/:id)
   │ ngOnInit: route.paramMap :id
   ▼
CancionesService.getProject(id) ──GET /projects/{id}──► store.get_project
   │  populate model + fragments[] + preserve reference_audio_url
   ▼
onSubmit (editingId set)
   │  CancionesService.replaceFragments(id, texts)
   ▼
PUT /api/projects/{id}/fragments
   │  router: store.replace_fragments(id, body.fragments)
   ▼
store.replace_fragments: read status → gate → DELETE-all → INSERT loop → commit
   ▼
200 SongProjectResponse (via _project_to_response)   |   409 Conflict | 404
   ▼
router.navigate(['/canciones/preview', id])
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/projects/store.py` | Modify | Add `replace_fragments(project_id, fragments, *, db_path)` + `COMPLETED_STATUSES = frozenset({"paid","completed"})`. Returns `(found, gated, updated_project)` tuple. |
| `app/projects/router.py` | Modify | Add `PUT /{project_id}/fragments`; maps `found=False`→404, `gated=True`→409, else 200 via `_project_to_response`. |
| `app/models.py` | Modify | Add `ReplaceFragmentsRequest(BaseModel)` with `fragments: list[str]`. |
| `tests/projects/test_replace_fragments.py` | Create | Backend TDD: happy-path replace + status-gate 409. |
| `.../canciones.routes.ts` | Modify | Add `{ path: 'edit/:id', loadComponent: CreateProjectComponent }`. |
| `.../create/create-project.component.ts` | Modify | Inject `ActivatedRoute`; edit-mode init + submit branch; preserve `referenceAudioFile=null`. |
| `.../create/create-project.component.spec.ts` | Modify | TDD: edit-mode route populate test. |
| `.../preview/preview.component.ts` | Modify | `routerLink="/canciones/edit/{{project.id}}"` (line 89). |
| `.../preview/preview.component.spec.ts` | Modify | TDD: Rehacer targets edit route, not create. |
| `.../canciones.service.ts` | Modify | Add `replaceFragments(id, fragments: string[])` → `http.put<SongProjectResponse>(.../fragments, {fragments})`. |
| `.../canciones.service.spec.ts` | Modify | Add method test. |

## Interfaces / Contracts

```python
# app/models.py
class ReplaceFragmentsRequest(BaseModel):
    fragments: list[str]  # empty allowed → clears all fragments

# app/projects/store.py
COMPLETED_STATUSES = frozenset({"paid", "completed"})

async def replace_fragments(project_id, fragments, *, db_path) -> tuple[bool, bool, dict | None]:
    # returns (found, gated, updated_project_dict) — gated only meaningful if found
```

```ts
// canciones.service.ts
replaceFragments(id: string, fragments: string[]): Observable<SongProjectResponse> {
  return this.http.put<SongProjectResponse>(
    `${this.baseUrl}/projects/${id}/fragments`, { fragments });
}
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Backend unit | `replace_fragments` atomic replace | pytest, in-memory/tmp SQLite; assert count+order, empty-list clears |
| Backend integration | PUT endpoint happy + 409 | `httpx` against app; `paid` fixture → 409, fragments unchanged |
| Frontend unit | edit-mode route populate | `TestBed` stub `ActivatedRoute` + `CancionesService`; assert model+fragments filled |
| Frontend unit | Rehacer binding | template assert `routerLink="/canciones/edit/{{project.id}}"` |
| Regression | full suite | `pytest` + `jest canciones` |

## Migration / Rollout

No data migration — additive endpoint + additive route. Rollback: revert route +
button wiring, remove `PUT` route + `replace_fragments`. Create/append flow
(`POST`/`PATCH`) stays as fallback.

## Open Questions

- [ ] **Auth gap (BLOCKS hardening, not this change)**: `router.py` has no auth on any project endpoint. This change follows the existing no-auth pattern. Confirm whether to add `get_current_user` here or as a separate hardening change.
- [ ] Frontend edit-mode reference audio: `reference_audio_url` preserved from `getProject`, but `referenceAudioFile` is display-only (no re-upload). Confirm the existing `preview` player shows the preserved audio via `project.reference_audio_url`.
