# Google Login for Personalized Songs — Specification

## Purpose

Define cross-application Google authentication and ownership for personalized-song projects while preserving anonymous creation.

## ADDED Requirements

### Requirement: Cross-application Google authentication

The system MUST allow POSFrontReform to authenticate a Google user and hand off a valid minimal JWT to POSCuentasCorrientes, which MUST establish the session before entering protected canciones workflows. The JWT MUST contain a stable `user_id` and MUST NOT require BranchOffice claims.

#### Scenario: Successful canciones login handoff
- GIVEN a user completes Google login in staging
- WHEN POSFrontReform redirects to the canciones entry point with the established token parameters
- THEN POSCuentasCorrientes validates and stores the JWT, and the user reaches canciones authenticated

#### Scenario: Invalid or expired handoff
- GIVEN the redirect contains an invalid, expired, or unverifiable JWT
- WHEN POSCuentasCorrientes processes the redirect
- THEN it MUST reject the session and route the user to login with a recoverable error

### Requirement: Anonymous and protected frontend access

Song creation and preview MUST remain public. The `mis-canciones`, checkout, and download routes MUST require authentication and MUST redirect unauthenticated users to Google login, preserving the intended destination.

#### Scenario: Anonymous creation remains available
- GIVEN no authenticated session exists
- WHEN the user opens creation and preview
- THEN the forms and preview MUST be usable without login

#### Scenario: Protected route access
- GIVEN no authenticated session exists
- WHEN the user opens `mis-canciones`, checkout, or download
- THEN the application MUST redirect to login and return to the requested workflow after success

### Requirement: JWT-owned project retrieval

The canciones API MUST expose `GET /api/projects/mine` as an authenticated endpoint. It MUST return only projects whose `user_id` equals the validated JWT `user_id`, and MUST return 401 when authentication is absent or invalid.

#### Scenario: List owned projects
- GIVEN a valid JWT with `user_id = U1`
- WHEN the client requests `/api/projects/mine`
- THEN the response MUST contain only projects owned by U1

#### Scenario: Ownership isolation
- GIVEN projects owned by U1 and U2
- WHEN a valid U1 token requests `/api/projects/mine`
- THEN no U2 project or ownership-sensitive data may be returned

### Requirement: Checkout linking and email fallback

Checkout MUST accept the authenticated JWT user identity and link the project to that `user_id` idempotently. Projects created before authentication MAY be recovered by verified email lookup; email MUST NOT override an existing JWT ownership link.

#### Scenario: Anonymous project linked at checkout
- GIVEN an anonymous project with the purchaser email and an authenticated JWT for that email
- WHEN checkout or payment confirmation succeeds
- THEN the project MUST be linked to the JWT `user_id` without duplicate links

#### Scenario: Legacy email recovery
- GIVEN a pre-authentication project with a matching verified email and no `user_id`
- WHEN the authenticated user requests their projects
- THEN the project MAY be included and MUST be linkable to that JWT user

#### Scenario: Email mismatch
- GIVEN an authenticated JWT and a project email that does not match the authenticated identity
- WHEN the user attempts checkout or linking
- THEN the API MUST reject the ownership operation with a non-success response

### Requirement: Project data ownership model

The project model MUST preserve nullable `user_id` for anonymous projects and existing email data. Authenticated reads, checkout, payment linking, and downloads MUST use JWT ownership as authoritative; legacy email lookup MUST remain fallback-only.

#### Scenario: Existing anonymous data remains valid
- GIVEN a project created before this change
- WHEN the updated API reads it
- THEN it MUST remain available without migration or deletion, subject to the fallback rules

#### Scenario: Authenticated download authorization
- GIVEN a paid project owned by U1
- WHEN U2 requests its download using a valid token
- THEN the API MUST return 403 or an equivalent authorization failure and MUST NOT disclose the file

### Requirement: Frontend identity-aware checkout and listing

POSCuentasCorrientes canciones components MUST derive the authenticated `user_id` from the session JWT, use it for checkout/linking, and display `/api/projects/mine` in “mis-canciones”. The UI MUST present actionable login and API error states.

#### Scenario: Authenticated checkout
- GIVEN a logged-in user with an anonymous project
- WHEN checkout is submitted
- THEN the request MUST use the session identity and show the payment flow only after successful ownership validation

#### Scenario: API failure state
- GIVEN `/api/projects/mine` or checkout returns 401, 403, or 5xx
- WHEN the component receives the response
- THEN it MUST show an actionable error and MUST NOT present unauthorized project data

## Auth Flow

1. User creates and previews a song anonymously.
2. At checkout or protected viewing, the module redirects to POSFrontReform login.
3. POSFrontReform completes Google OAuth using the staging client ID.
4. POSFrontReform redirects back through the established token handoff.
5. POSCuentasCorrientes validates/stores the minimal JWT and returns to the intended canciones route.
6. CancionesPersonalizadas validates the shared-secret JWT, uses `user_id` for ownership, and performs idempotent linking; email is fallback only.

## API Changes

- Add authenticated `GET /api/projects/mine`.
- Modify checkout, payment-linking, project reads, and downloads to enforce JWT ownership.
- Preserve anonymous project creation and nullable `user_id`.
