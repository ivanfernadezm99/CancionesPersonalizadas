# User Authentication Specification

## Purpose

Provide JWT-based authentication middleware for CancionesPersonalizadas that validates tokens issued by POSBackend (.NET), extracts user identity/role/business claims, and protects song-generation endpoints while allowing public health/connectivity checks.

## Requirements

### RQ-AUTH-01: JWKS Token Validation

The system MUST validate JWT access tokens using the POSBackend JWKS endpoint. Tokens MUST be verified for signature, expiry (`exp`), issuer (`iss`), and audience (`aud`).

#### Scenario: Valid token accepted

- GIVEN a valid JWT signed by POSBackend's private key, with `exp` > now, `iss` matching expected issuer, and `aud` matching expected audience
- WHEN a protected endpoint receives `Authorization: Bearer {token}`
- THEN the request MUST proceed to the handler
- AND `request.state.user_id`, `request.state.role_id`, `request.state.business_id` MUST be populated

#### Scenario: Expired token rejected

- GIVEN an expired JWT
- WHEN a protected endpoint is called with that token
- THEN the response MUST be 401 with `{"detail": "Token expired"}`
- AND `WWW-Authenticate: Bearer` header MUST be present

#### Scenario: Malformed token rejected

- GIVEN a random string as token
- WHEN a protected endpoint is called
- THEN the response MUST be 401 with `{"detail": "Invalid token"}`

#### Scenario: Wrong-signature token rejected

- GIVEN a JWT signed with a different key
- WHEN a protected endpoint is called
- THEN the response MUST be 401

#### Scenario: Missing authorization header

- GIVEN no `Authorization` header
- WHEN a protected endpoint is called
- THEN the response MUST be 401

### RQ-AUTH-02: JWKS Key Rotation Support

The system MUST fetch and cache JWKS keys from `JWKS_URL` on startup and refresh them periodically (every 3600s or on validation failure).

#### Scenario: Key refreshed after rotation

- GIVEN POSBackend rotates its signing key
- WHEN a token signed with the new key is presented
- THEN validation MUST succeed after the next JWKS refresh
- AND the old key MUST be evicted from the cache

#### Scenario: JWKS endpoint unreachable on startup

- GIVEN JWKS_URL is unreachable at startup
- WHEN the first request arrives
- THEN the system MUST return 503 with `{"detail": "Auth service unavailable"}`
- AND MUST retry JWKS fetch on subsequent requests

### RQ-AUTH-03: Protected vs Public Routes

The system MUST protect all endpoints under `/api/projects/*`, `/api/generate`, and `/api/stream/*`. The system MUST allow unauthenticated access to `GET /` and `POST /api/auth/health`.

#### Scenario: Health endpoint accessible without auth

- GIVEN no Authorization header
- WHEN POST /api/auth/health is called
- THEN response MUST be 200 with `{"status": "ok"}`
- AND no auth middleware error MUST occur

#### Scenario: Protected project endpoint requires auth

- GIVEN no Authorization header
- WHEN GET /api/projects is called
- THEN response MUST be 401

### RQ-AUTH-04: Role-Based Access

The system MUST extract `role_id` from the JWT claims. The system MAY reject requests based on insufficient role.

#### Scenario: Valid token with insufficient role

- GIVEN a valid JWT with `role_id` that lacks project access
- WHEN a protected endpoint is called
- THEN response MUST be 403 with `{"detail": "Insufficient permissions"}`

## Dependencies

- **External**: POSBackend JWKS endpoint (`.well-known/openid-configuration` → `jwks_uri`)
- **Library**: `python-jose[cryptography]` or equivalent for JWKS validation
- **Config**: `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE` in `config.py`

## Acceptance Criteria

- [ ] Valid POSBackend JWT passes auth on protected routes
- [ ] Expired/malformed/wrong-key tokens return 401
- [ ] JWKS auto-refresh works after key rotation
- [ ] Health endpoint returns 200 without auth
- [ ] Missing auth header returns 401
- [ ] All user claims (`user_id`, `role_id`, `business_id`) are extractable
