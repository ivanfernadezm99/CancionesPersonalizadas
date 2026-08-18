# Design: Google Login for Personalized Songs

## Technical Approach

Reuse POSBackend's Google login and shared HS256 JWT. POSFrontReform stores the returned JWT and redirects to the existing POSCuentasCorrientes token-sync entry point; the latter captures and removes `token` from the URL before routing into canciones. Canciones keeps creation/preview anonymous, but authenticated operations use `request.state.user_id` exclusively. Email remains a compatibility fallback only for legacy projects.

## Architecture Decisions

| Decision | Choice | Alternatives / rationale |
|---|---|---|
| Identity | JWT `user_id` is authoritative; email is fallback | A new identity provider would duplicate POSBackend and break existing sessions. |
| Handoff | Existing `TokenSyncService` query-token handoff | A bespoke callback adds protocol and security surface; current service already captures, persists, and cleans the URL. |
| Route policy | Public landing/create/edit/preview; guarded checkout/download/mis-canciones | Login before creation harms conversion; ownership-sensitive actions require a session. |
| Compatibility | Nullable `projects.user_id`, additive linking | Migration/deletion would risk existing purchases; legacy email recovery remains available. |

## Architecture Diagram

```text
Google OAuth
    │ credential
    ▼
POSFrontReform ── POST Auth/LoginWithGoogle ──▶ POSBackend
    │                                              │ auto-create user + JWT(user_id)
    └── redirect /canciones/landing?token=JWT ─────┘
                         ▼
             POSCuentasCorrientes TokenSyncService
             stores JWT, cleans URL, restores returnUrl
                         │ Authorization: Bearer JWT
                         ▼
             CancionesPersonalizadas FastAPI + SQLite
             validate JWT → user_id → project ownership/linking
```

## Auth Flow and Data Flow

1. The user creates a project and preview anonymously. `POST /api/projects` may store `user_id = NULL`.
2. The user enters checkout or opens a protected route. The canciones route guard stores the URL and sends them to POSFrontReform Google login.
3. Google returns a credential; `login-google.component.ts` calls `AuthService.loginWithGoogle`.
4. POSBackend creates/loads the user and returns a JWT containing stable `user_id` (no branch claims required). The login success handler redirects to `accountCurrentAppUrl + 'canciones/landing?token=' + encodeURIComponent(jwt)` with the intended route in `returnUrl`.
5. `TokenSyncService` stores the token in localStorage, removes query parameters via `history.replaceState`, and restores the return route. The browser sends the JWT automatically through the existing HTTP interceptor.
6. FastAPI middleware validates signature/expiry and exposes `request.state.user_id`. Checkout verifies project email against JWT email when both exist, then sets `user_id` only if null (idempotent; never overwrites another owner). `/mine` queries `WHERE user_id = ?`.

## API Design

`GET /api/projects/mine` (Bearer JWT required) → `200 SongProjectResponse[]`, newest first. Missing, invalid, expired, or claim-less JWT → `401`.

`POST /api/projects/{id}/checkout` (JWT required for protected checkout) → existing `CheckoutResponse` after ownership validation/linking. Email mismatch or an existing different owner → `403`; unknown project → `404`; payment gateway errors retain existing `503` mapping.

Existing project/download endpoints must authorize the JWT owner before returning sensitive project/audio data: owner → normal response; different owner → `403`; absent/expired token on protected routes → `401`. Anonymous `POST /api/projects` and preview remain public.

## Frontend Architecture

| File | Action | Design |
|---|---|---|
| `POSFrontReform/src/environments/environment.stg.ts` | Modify | Replace placeholder `clientId` with staging credential or build-time environment value. |
| `POSFrontReform/src/app/pages/auth/components/login-google/login-google.component.ts` | Modify | Redirect successful login to canciones with encoded JWT and preserved destination. |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/canciones.routes.ts` | Modify | Apply existing `authGuard` to `checkout/:id`, `download/:id`, and `mis-canciones`; leave landing/create/edit/preview public. |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/canciones.service.ts` | Modify | Add `getMyProjects()` for `/projects/mine`; preserve email lookup only as recovery UI/API path. |
| `.../checkout/checkout.component.ts`, `payment.service.ts` | Modify | Remove client-supplied ownership identity; send authenticated request, retain email only for verified legacy recovery, and map 401/403 to login/actionable errors. |
| `.../mis-canciones/mis-canciones.component.ts` | Modify | Load `getMyProjects()` on init; remove email search as the primary flow and show empty/error states. |

## Backend File Changes

| File | Action | Design |
|---|---|---|
| `app/auth/dependencies.py` | Modify | Add reusable required-user dependency that rejects absent/invalid `user_id`. |
| `app/projects/router.py` | Modify | Add `/mine` before `/{project_id}`, enforce owner checks on sensitive reads/downloads, and pass request identity to checkout. |
| `app/projects/payment.py` | Modify | Extract JWT identity/email, validate ownership, and link atomically/idempotently before creating preference. |
| `app/projects/store.py` | Modify | Add user-scoped retrieval/link helper and index on nullable `user_id`; preserve legacy email lookup semantics. |
| `app/models.py` | Modify | Define response/request contracts if checkout or ownership errors need typed fields. |

## Testing Strategy

| Layer | Coverage |
|---|---|
| Unit | JWT dependency, claim extraction, owner/mismatch rules, idempotent linking, store isolation. |
| Integration | `/mine` 200/401/isolation; checkout owner/mismatch/legacy fallback; protected project/download access. |
| Frontend | Guard matrix, token handoff URL cleanup, Google redirect, checkout request, `/mine` loading/errors. |
| E2E | Staging smoke: Google → canciones → checkout → payment → download; anonymous create/preview regression. |

## Threat Matrix

Applicable: redirect token leakage (clean URL immediately; use HTTPS and encoded token), expired/invalid JWT (401 and recoverable login), cross-user project access (403 with no body/file), email mismatch (403), and malformed handoff (reject before session establishment). Shell, subprocess, VCS/PR automation, and executable-file classification: N/A.

## Migration / Rollout

No destructive migration required. Deploy backend authorization first, then POSCuentasCorrientes, then POSFrontReform with the real staging client ID. Roll back frontend guards/handoff independently; nullable ownership data remains valid.

## Open Questions

- [ ] Confirm whether staging Google Client ID is injected at build time or committed in `environment.stg.ts`.
- [ ] Confirm the exact login route/returnUrl contract used by POSFrontReform and POSCuentasCorrientes.
