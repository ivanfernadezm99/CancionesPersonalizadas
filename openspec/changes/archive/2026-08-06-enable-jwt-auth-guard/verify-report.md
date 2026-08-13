# Verify Report: Enable JWT Auth Guard

## Status: PASS

## Summary

Verified the `enable-jwt-auth-guard` change (CancionesPersonalizadas backend) against
spec RQ-JWT-01..04 and their acceptance scenarios. The HS256 shared-secret verification,
ASP.NET long claim-URI mapping onto `request.state`, default-enforced auth, and payment
webhook exemption are all implemented and covered by passing tests.

## Test Runs

| Suite | Command | Result |
|-------|---------|--------|
| Auth guard + middleware | `python3 -m pytest tests/test_auth/test_jwt_auth_guard.py tests/test_auth/ -v` | **27 passed** |
| Full suite | `python3 -m pytest -q` | **342 passed, 5 failed** (all 5 pre-existing, unrelated to JWT) |

The 5 failures are pre-existing and unrelated: `test_full_flow`,
`test_final_requires_payment`, `test_generate_full_pipeline_completes` fail on
unmocked Suno `api.sunoapi.org/api/v1/generate` (RESPX), and
`test_generate_returns_lyrics_result` / `test_generate_returns_none_on_error` fail on
`GeminiProvider._get_model` attribute mock. None touch the auth guard; the
`_permissive_auth_default` fixture keeps non-auth suites green.

## Spec Traceability

| Requirement | Implementation evidence | Test evidence | Result |
|-------------|-------------------------|---------------|--------|
| RQ-JWT-01 — Verify HS256 tokens with shared secret (issuer/audience/exp) | `app/auth/middleware.py:61-68` `jwt.decode(..., settings.JWT_SHARED_SECRET, algorithms=[settings.JWT_ALGORITHM], verify_exp=True, issuer/audience)` | `test_valid_hs256_token_allows_request` (+ expired/malformed/wrong-secret in `test_auth_middleware.py`) | PASS |
| RQ-JWT-02 — Map claims to request.state (nameidentifier→user_id, role→role_id, BusinessId→business_id) | `app/auth/middleware.py:133-135` maps `NAMEID_URI`, `ROLE_URI`, `BUSINESS_CLAIM` | `test_valid_hs256_token_allows_request` asserts user_id `user-abc-123`, role_id `1`, business_id `biz-001` | PASS |
| RQ-JWT-03 — Enforce auth by default (`JWT_AUTH_ENFORCED=True`) | `app/config.py:69` `JWT_AUTH_ENFORCED: bool = True` | `test_missing_token_blocked_when_enforced` (401 `unauthorized`) | PASS |
| RQ-JWT-04 — Exempt payment webhook from auth | `app/auth/middleware.py:24` `/api/webhooks/payment-confirmed` in `PUBLIC_ROUTES` exact match | `test_webhook_exempt_from_auth` (no Bearer, valid secret → reaches handler → 404 `project_not_found`); `test_webhook_invalid_secret_returns_401` | PASS |

## Code-Level Checks

- `PUBLIC_ROUTES` includes exact string `/api/webhooks/payment-confirmed` (`middleware.py:24`); `_is_public_route` uses exact match + `/docs`/`/openapi` prefix. PASS
- `app/config.py`: `JWT_AUTH_ENFORCED=True` (line 69), `JWT_ALGORITHM="HS256"` (line 67), `JWT_SHARED_SECRET: str = ""` Field (line 68). PASS
- `_permissive_auth_default` autouse fixture in `tests/conftest.py:26-31` sets `JWT_AUTH_ENFORCED=False` for non-auth suites so enforcement doesn't break business tests; auth tests re-enable it. PASS
- `mypy app/auth/` → `Success: no issues found in 4 source files`. PASS

## Findings

- CRITICAL: []
- WARNING: []
  - The task brief referenced the claim-mapping lines as `middleware.py:149-151`, but the
    file is 148 lines and the mapping lives at `middleware.py:133-135`. Documentation-only
    discrepancy; the mapping is present and correct.
- SUGGESTION: []

## Verdict: PASS