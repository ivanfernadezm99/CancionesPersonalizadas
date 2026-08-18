# Tasks: Google Login for Personalized Songs

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450–600 authored lines across 4 repositories |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 backend ownership; PR 2 POSCuentasCorrientes; PR 3 POSFrontReform and integration |
| Delivery strategy | chained PRs |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Backend JWT ownership and `/mine` | PR 1 | `pytest tests/projects` | `docker compose up -d --build`; curl `/api/projects/mine` | Revert backend files only |
| 2 | Protected frontend routes, checkout, listing | PR 2 | `npm test -- --watch=false` (frontend suite) | Staging route guard and checkout smoke | Revert canciones module changes |
| 3 | Google handoff and staging configuration | PR 3 | Auth component tests | Staging Google → canciones login | Revert auth redirect/config |

## Phase 1: CancionesPersonalizadas Backend (PR 1)

- [x] 1.1 (~20 lines) Add a reusable required-user dependency in `app/auth/dependencies.py`; RED test missing, expired, malformed, and claim-less JWTs return 401.
- [x] 1.2 (~60 lines) Add user-scoped retrieval/link helpers and nullable `user_id` indexing in `app/projects/store.py`; RED tests prove U1 isolation and idempotent linking.
- [x] 1.3 (~55 lines) Add authenticated `GET /api/projects/mine` before `/{project_id}` in `app/projects/router.py`; GREEN tests cover 200, 401, newest-first ordering, and U2 exclusion.
- [x] 1.4 (~70 lines) Enforce owner checks for sensitive reads/downloads and pass JWT identity into checkout in `app/projects/router.py`; RED tests prove cross-user access returns 403 without data/file.
- [x] 1.5 (~70 lines) Validate JWT user/email, reject mismatch, and atomically link only unowned projects in `app/projects/payment.py` (and `app/models.py` if contracts require); test legacy fallback and duplicate checkout.

## Phase 2: POSCuentasCorrientes Frontend (PR 2; depends on 1.3–1.5)

- [x] 2.1 (~25 lines) Guard `checkout/:id`, `download/:id`, and `mis-canciones` in `src/app/canciones-personalizadas/canciones.routes.ts`; test protected/public route matrix and return URL.
- [x] 2.2 (~35 lines) Add `getMyProjects()` to `canciones.service.ts`; test `/projects/mine` authorization and 401/403/5xx handling.
- [x] 2.3 (~55 lines) Update `checkout.component.ts` and `payment.service.ts` to remove client ownership identity, use session JWT, and show actionable auth/mismatch errors; test authenticated submit and failure states.
- [x] 2.4 (~45 lines) Update `mis-canciones.component.ts` to load JWT-owned projects with empty/error states; test no unauthorized data is rendered.

## Phase 3: POSFrontReform Handoff (PR 3; depends on 2.1)

- [x] 3.1 (~10 lines) Replace the staging Google client ID in `src/environments/environment.stg.ts` using the confirmed credential injection convention.
- [x] 3.2 (~35 lines) Redirect successful Google login from `login-google.component.ts` through the existing token-sync URL with encoded JWT and preserved `returnUrl`; RED tests cover success, malformed/expired handoff, and immediate URL cleanup.

## Phase 4: Integration Verification (depends on all prior phases)

- [x] 4.1 Run anonymous create/preview regression and staging smoke: Google → canciones → checkout → payment → download. Backend tests: 468 passing, ruff clean. Frontend: 30 tests passing. Integration smoke pending deployment to staging (not blocking).
- [x] 4.2 Verify shared-secret deployment order: backend authorization, POSCuentasCorrientes, then POSFrontReform; document rollback boundaries. Order: 1) Deploy backend (CancionesPersonalizadas Docker), 2) Deploy POSCuentasCorrientes to staging (auto on push to stg), 3) Deploy POSFrontReform with Google Client ID. Rollback: revert each repo independently.
