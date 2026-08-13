# Design: Fix preview rendering under zoneless change detection

## Technical Approach

The app runs `provideZonelessChangeDetection()` (`app.config.ts:12`), so template re-render only happens when the framework is notified. `preview.component.ts`, `download.component.ts`, and `create-project.component.ts` mutate render state (`project`, `streamUrl`, `loading`, `error`, `submitting`) inside `.subscribe()` next/error callbacks without notifying the view, leaving the template stale (e.g. infinite "Generando preview"). The fix mirrors the proven in-repo pattern in `social-media/analytics/analytics-dashboard.component.ts:80,90-91`: inject `ChangeDetectorRef` and call `detectChanges()` after every synchronous state mutation inside subscription handlers. Implements RQ-PRJ-09 scenarios (existing-complete renders player; queued shows spinner then player; error reflects view; defensive coverage across preview/download/create).

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Detection mechanism | `ChangeDetectorRef.detectChanges()` | `markForCheck()` / signals migration | `detectChanges()` is the proven repo pattern (analytics-dashboard) and forces synchronous re-render of this detached-async component; `markForCheck()` only marks, relying on an upcoming CD that zoneless may not run. Signals are explicitly out of scope (deferred follow-up) — minimal diff. |
| DI style | `inject(ChangeDetectorRef)` via field | constructor injection | The 3 components already use `inject()` exclusively; keeps file style consistent with the codebase (only analytics uses constructor DI). |
| Polling integration | CDR only in the `next`/`error` that actually mutates state | CDR inside every poll tick | `preview.pollJobStatus` resolves a Promise; the only mutations happen in `generatePreview.next/error` and `loadProject.next/error`, so a single `detectChanges()` there covers the spinner→player swap. Avoids per-tick double detection. |
| Scope | Fix confirmed anti-patterns in all 3 components | Fix preview only | RQ-PRJ-09 defensive scenario requires the same correctness in download/create; confirmed both mutate in-subscribe. |

## Data Flow

```
PreviewComponent
  loadProject(id) ─ subscribe.next ─ mutates project/streamUrl/loading ─ cdr.detectChanges()
       │ error ─ mutates loading/error ─ cdr.detectChanges()
       └ no-complete-preview ─ generatePreview() ─ createPreview().next ─ switchMap pollJobStatus
            └ poll resolves Promise ─ generatePreview.next ─ mutates streamUrl/loading ─ cdr.detectChanges()
                 │ error ─ mutates loading/error ─ cdr.detectChanges()
```

`download.pollFinalJob` and `create.onSubmit/addFragmentsSequentially` mutate state directly in their own next/error/catch → each gets `cdr.detectChanges()` after mutation.

## File Changes

Working directory for apply/verify: `/home/servidor/Descargas/POSCuentasCorrientes`.

| File | Action | Description |
|------|--------|-------------|
| `src/app/canciones-personalizadas/preview/preview.component.ts` | Modify | Add `inject(ChangeDetectorRef)`; call `cdr.detectChanges()` in `loadProject.next`+`error` and `generatePreview.next`+`error`. |
| `src/app/canciones-personalizadas/download/download.component.ts` | Modify | Add `inject(ChangeDetectorRef)`; `cdr.detectChanges()` in `loadProject.next`+`error`, `generateFinal.error`, `pollFinalJob.next` (complete/failed) and its timeout branch. |
| `src/app/canciones-personalizadas/create/create-project.component.ts` | Modify | Add `inject(ChangeDetectorRef)`; `cdr.detectChanges()` in `onSubmit.next`+`error` and `addFragmentsSequentially.catch`. |
| `src/app/canciones-personalizadas/preview/preview.component.spec.ts` | Modify | Add async re-render tests (fakeAsync) asserting DOM reflects state without manual `detectChanges`. |
| `src/app/canciones-personalizadas/download/download.component.spec.ts` | Modify | Add async CDR-triggered re-render test. |
| `src/app/canciones-personalizadas/create/create-project.component.spec.ts` | Modify | Add test asserting `submitting`/error re-render after async submit. |

## Interfaces / Contracts

No public API changes. `models.ts`, `canciones.service.ts`, `app.config.ts`, routes unchanged. Only new import per component:

```ts
import { ChangeDetectorRef } from '@angular/core';
// ...
private cdr = inject(ChangeDetectorRef);
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (preview) | Existing-complete project renders `<audio>` + hides spinner after async load; queued → poll → swap to player; error path shows error state, no stale spinner | `fakeAsync`/`tick` with delayed observables; assert DOM after subscription resolves **without** an explicit `fixture.detectChanges()` (proves CDR drove re-render). |
| Unit (download) | Completed final job renders player/download; failed job shows error | Same async-render pattern. |
| Unit (create) | Submit toggles `submitting` and error renders | Assert button label/error appears after async `createProject` resolves. |
| Regression | All existing specs still green; `cdr.detectChanges` spied when needed | Run full module suite. |

## Migration / Rollout

No migration required. Pure frontend behavior fix; single PR against `POSCuentasCorrientes`. Rollback = `git revert` of that commit.

## Open Questions

- None blocking. (Test harness `jest-preset-angular` + jsdom supports fakeAsync; existing specs use manual `detectChanges` — new tests must deliberately omit it to exercise the fix.)
