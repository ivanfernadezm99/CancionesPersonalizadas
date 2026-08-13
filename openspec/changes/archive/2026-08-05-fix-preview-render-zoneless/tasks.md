# Tasks: Fix preview rendering under zoneless change detection

> Working directory for apply/verify: `/home/servidor/Descargas/POSCuentasCorrientes`. All paths below are relative to it.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150–250 (3 components + 3 specs) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full fix (3 comps + 3 specs) | PR 1 | Single PR to main; well under budget |

## Phase 1: Core fix — PreviewComponent

- [x] 1.1 `src/app/canciones-personalizadas/preview/preview.component.ts` — add `ChangeDetectorRef` to `@angular/core` import and field `private cdr = inject(ChangeDetectorRef);`
- [x] 1.2 Same file — in `loadProject.next`, call `this.cdr.detectChanges()` after setting `streamUrl`+`loading=false` (completed-preview branch) and after `generatePreview()` branch; in `loadProject.error` after `loading=false`
- [x] 1.3 Same file — in `generatePreview.next` (after `streamUrl`+`loading=false`) and `generatePreview.error` (after `loading=false`), call `this.cdr.detectChanges()`

## Phase 2: Defensive fix — DownloadComponent

- [x] 2.1 `src/app/canciones-personalizadas/download/download.component.ts` — add `ChangeDetectorRef` import and `private cdr = inject(ChangeDetectorRef);`
- [x] 2.2 Same file — `cdr.detectChanges()` in `loadProject.next` (completed-final branch) and `loadProject.error`
- [x] 2.3 Same file — `cdr.detectChanges()` in `pollFinalJob.next` on `complete` and on `failed`, and in its 120s timeout branch (after `loading=false`). Do NOT add it in `generateFinal.next` (only calls `pollFinalJob`, mutates nothing — avoid double-detection)

## Phase 3: Defensive fix — CreateProjectComponent

- [x] 3.1 `src/app/canciones-personalizadas/create/create-project.component.ts` — add `ChangeDetectorRef` import and `private cdr = inject(ChangeDetectorRef);`
- [x] 3.2 Same file — `cdr.detectChanges()` in `onSubmit.next` (after `submitting=false`) and `onSubmit.error`; in `addFragmentsSequentially.catch` after setting `error`. Low-value defensive patch (navigates immediately) — no heavy test investment

## Phase 4: Tests (async re-render)

- [x] 4.1 `preview/preview.component.spec.ts` — use `fakeAsync` with **delayed** observables (`timer`/`defer`, not synchronous `of()`); assert DOM shows `<audio>`/hides spinner after load/poll **without** calling `fixture.detectChanges()` after `tick()`; `flush()`/`tick(60000)` the polling timeout to clear timers
- [x] 4.2 `download/download.component.spec.ts` — `fakeAsync` re-render test: completed final job renders player after async resolve; flush `tick(120000)` to clear the poll timeout
- [x] 4.3 `create/create-project.component.spec.ts` — assert `submitting`→button label and error re-render after async `createProject` resolves (light coverage only)

## Phase 5: Verification

- [x] 5.1 Run module suite: `npx jest src/app/canciones-personalizadas --passWithNoTests`
- [x] 5.2 Full regression: `npm test` and `npm run build:staging` (no new zoneless CD warnings)

## Notes

- Pattern to mirror: `src/app/social-media/analytics/analytics-dashboard.component.ts:80,90-91`.
- Scope guard: no backend changes, no signals migration, no `app.config.ts`/`models.ts`/service changes.
