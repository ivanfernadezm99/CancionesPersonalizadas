# Proposal: Fix preview rendering under zoneless change detection

## Intent

Fix active bug where the preview page (`#/canciones/preview/:id`) shows "Generando preview... Esto puede tomar unos segundos" indefinitely even when the backend returns 2 previews with `status: complete`. Root cause: the app uses `provideZonelessChangeDetection()` (`src/app/app.config.ts:12`), and `preview.component.ts` mutates `this.project`, `this.loading`, `this.streamUrl` inside `.subscribe()` (lines 256-275, polling 286-305) without `ChangeDetectorRef`, signals, or `detectChanges()`. Under zoneless CD these mutations do not trigger re-render, so the template keeps seeing `project === null` and `loading === true` even though `next()` ran with correct data. This blocks users from previewing generated songs.

## Scope

### In Scope
- Inject `ChangeDetectorRef` into `preview.component.ts`; call `detectChanges()` (or `markForCheck()`) in `next`/`error` handlers of `loadProject` and the polling interval (the known-good pattern already exists at `social-media/analytics/analytics-dashboard.component.ts:90-91`).
- Audit and defensively fix the same subscribe-without-CDR anti-pattern in `download/download.component.ts` and `create/create-project.component.ts` if present.
- Add/extend unit tests asserting the template re-renders after async subscription completes.

### Out of Scope
- NOT migrating to Angular signals (deferred follow-up change).
- No backend/API changes; service (`canciones.service.ts`) and `models.ts` are confirmed correct (snake_case aligned: `job_id`, `job_type`, `status`, `created_at`); interceptors verified non-interfering.
- No styling/UX redesign of the preview player.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `song-projects`: requirement that the preview UI MUST reactively render completed job results (show sample player) once the job transitions to `complete`, including under zoneless change detection; polling/spinner must reflect subscription state.

## Approach

Inject `ChangeDetectorRef` via constructor; after each synchronous mutation inside `.subscribe()` next/error callbacks (both initial load and polling), invoke `this.cdr.detectChanges()`. Mirror the proven `analytics-dashboard.component.ts` pattern. Where polling closes over component state, ensure the CDR reference is captured in a way that survives the interval closure. Defensive pass on download/create components applies the same fix for any in-subscribe field mutations.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `POSCuentasCorrientes/src/app/canciones-personalizadas/preview/preview.component.ts` | Modified | Add CDR + `detectChanges()` in subscribe handlers |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/download/download.component.ts` | Modified | Defensive CDR fix if anti-pattern present |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/create/create-project.component.ts` | Modified | Defensive CDR fix if anti-pattern present |
| `POSCuentasCorrientes/.../preview.component.spec.ts` (+specs) | New/Modified | Tests for async re-render |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Double-detection / performance impact on polling ticks | Low | Prefer `detectChanges()` only on state-changing branches; validate tick count |
| Over-applying fix to components not actually affected | Med | Audit first; only touch components with confirmed in-subscribe mutations |
| Polling interval closure loses CDR binding | Low | Capture `this`/CDR reference outside interval callback |

## Rollback Plan

Revert the single component-level commit (files: `preview.component.ts`, download/create components, specs). Since no backend or routing changes exist, rollback is a clean `git revert` of the frontend PR; the API contract is untouched.

## Dependencies

- Frontend repo `~/Descargas/POSCuentasCorrientes` (Angular 21, zoneless CD).
- Local backend Docker on `localhost:8001`; frontend `localhost:4200` (hash routing) for manual verification.

## Success Criteria

- [ ] Navigating to `#/canciones/preview/9af8de3c-d2a0-42e8-9070-a252f9c61b8a` shows the sample player (no regeneration needed) instead of the infinite "Generando preview" state.
- [ ] A new project that queues a preview shows the spinner, then the player once the job transitions to `complete`.
- [ ] `ng build` + existing/new unit tests pass; no new zoneless CD warnings.
