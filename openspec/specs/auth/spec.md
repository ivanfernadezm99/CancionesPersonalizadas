# Auth Specification

## Purpose

Protect the CancionesPersonalizadas API with JWT Bearer auth. Tokens are HS256
signed by POSBackend with a shared secret, using ASP.NET long claim URIs. Auth is
enforced by default; public routes and the payment-confirmation webhook are excepted.

## Requirements

### RQ-JWT-01: Verify HS256 tokens with shared secret

The system MUST verify `Authorization: Bearer` JWTs as HS256 using the configured
`JWT_SHARED_SECRET`, checking issuer and audience against `JWT_ISSUER`/`JWT_AUDIENCE`
and token expiry. Tokens missing, malformed, or with a bad signature MUST be rejected.

#### Scenario: Valid token passes

- GIVEN a valid HS256 token signed with `JWT_SHARED_SECRET`
- WHEN a protected request is made with that token
- THEN response MUST be the normal endpoint response

#### Scenario: Invalid signature rejected

- GIVEN a token signed with a different secret
- WHEN a protected request is made
- THEN response MUST be 401 `invalid_token`

#### Scenario: Missing Bearer header rejected

- GIVEN no `Authorization` header
- WHEN a protected request is made
- THEN response MUST be 401 `unauthorized`

### RQ-JWT-02: Map POSBackend claims to request.state

The system MUST map claims onto `request.state` using ASP.NET claim URIs:
`.../identity/claims/nameidentifier` → `user_id`,
`.../identity/claims/role` → `role_id`, and `BusinessId` →
`business_id`.

#### Scenario: Full claim mapping

- GIVEN a token with nameidentifier, role, and BusinessId claims
- WHEN verified
- THEN `request.state.user_id`, `role_id`, and `business_id` MUST be set

#### Scenario: Missing BusinessId claim

- GIVEN a token without `BusinessId`
- WHEN verified
- THEN `request.state.business_id` MUST be an empty string

### RQ-JWT-03: Enforce auth by default

The system MUST enforce authentication by default. `JWT_AUTH_ENFORCED` MUST
default to `True`; invalid or missing tokens on protected routes MUST return
401/403 regardless of permissive-mode fallback behavior.

#### Scenario: Enforced by default

- GIVEN default settings with no `JWT_AUTH_ENFORCED` override
- WHEN a protected request has no valid token
- THEN response MUST be 401

#### Scenario: Role gate

- GIVEN a valid token whose role is not in `JWT_ALLOWED_ROLES`
- WHEN a protected request is made
- THEN response MUST be 403 `forbidden_role`

### RQ-JWT-04: Exempt payment webhook from auth

The system MUST allow `POST /api/webhooks/payment-confirmed` without a Bearer
token. The webhook MUST still validate its own `X-Webhook-Secret` header.

#### Scenario: Webhook without Bearer

- GIVEN no Bearer token but a valid `X-Webhook-Secret`
- WHEN POST /api/webhooks/payment-confirmed is called
- THEN the request MUST reach the webhook handler

#### Scenario: Webhook stays path-protected

- GIVEN no Bearer token and an invalid `X-Webhook-Secret`
- WHEN POST /api/webhooks/payment-confirmed is called
- THEN response MUST be 401 `invalid_webhook_secret`