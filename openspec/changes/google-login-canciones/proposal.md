# Proposal: Google Login for Personalized Songs

## Intent

Allow customers to create songs anonymously, authenticate with Google at checkout or when viewing their songs, and reliably see/download every project they own. JWT `user_id` becomes the authoritative ownership link while email lookup remains a recovery path for projects created before authentication.

## Scope

### In Scope
- Enable the staging Google login and provide a clear handoff from POSFrontReform to the canciones module.
- Protect authenticated canciones workflows while preserving anonymous creation and preview.
- Link checkout and paid projects to the authenticated JWT user and expose “my projects” retrieval.
- Retain email-based lookup as fallback for pre-authenticated projects.

### Out of Scope
- Replacing POSBackend authentication or introducing a separate identity provider.
- Requiring login before song creation.
- Migrating or deleting existing projects, or removing email lookup.

## Capabilities

### New Capabilities
- `google-song-auth`: Cross-application Google JWT handoff and authenticated canciones access.
- `owned-song-projects`: JWT-based project linking and retrieval with legacy email fallback.

### Modified Capabilities
- `auth`: Protect canciones routes and derive ownership from authenticated JWT claims.
- `song-projects`: Support anonymous creation followed by authenticated linking and retrieval.

## Approach

Use the existing POSFrontReform Google authentication and POSCuentasCorrientes `TokenSyncService` to transfer the JWT through the existing redirect mechanism. Guard `mis-canciones`, checkout, and download routes; keep create and preview public. The frontend uses JWT `user_id` for normal reads and checkout, while the backend validates the token, links projects idempotently, and serves `/api/projects/mine`; email lookup remains fallback-only. Redirects must avoid exposing tokens beyond the established handoff boundary.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `POSFrontReform` auth/config | Modified | Staging client ID and canciones entry point after login. |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/` | Modified | Guards, JWT-aware checkout, “my songs”, and post-payment linking. |
| `CancionesPersonalizadas/app/api/` | Modified | JWT ownership in checkout and authenticated `/projects/mine`. |
| `CancionesPersonalizadas` project model/routes | Modified | Preserve `user_id` and email fallback behavior. |

## Dependencies

- Working Google OAuth credentials for staging.
- Shared JWT signing secret and compatible claims across POSBackend, POSFrontReform, POSCuentasCorrientes, and canciones backend.
- Existing TokenSyncService and authGuard behavior.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Token redirect leakage or expiry | Med | Reuse existing handoff, validate JWT, and minimize token lifetime/exposure. |
| Anonymous projects remain unlinked | Med | Idempotent linking at checkout/payment and email fallback. |
| Route changes break anonymous creation | Low | Explicitly guard only authenticated workflows and test both paths. |

## Rollback Plan

Revert the four-repository changes, restore the prior route access and email-based flows, and disable the canciones login entry point. Existing projects remain intact because linking is additive.

## Success Criteria

- [ ] A staging Google-authenticated customer reaches canciones with a valid JWT.
- [ ] Anonymous creation and preview still work without login.
- [ ] Authenticated customers can list, checkout, pay, and download their projects.
- [ ] `/api/projects/mine` returns only projects owned by the JWT `user_id`.
- [ ] Pre-auth projects remain discoverable through email fallback.
