# Tasks: Enable JWT Auth Guard (HS256)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~300 (code + tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Migrate to HS256 + enforce + exempt webhook (TDD) | PR 1 (single) | Backend only; frontend unaffected |

TDD: RED test → GREEN fix per task.

## Phase 1: Config (RED)

- [x] 1.1 Write test asserting `JWT_SHARED_SECRET` setting exists and `JWT_AUTH_ENFORCED` defaults `True` (RED — fails until config change)
- [x] 1.2 Add `JWT_SHARED_SECRET: str = ""` and set `JWT_AUTH_ENFORCED: bool = True` in `app/config.py` (GREEN)

## Phase 2: Middleware migration (RED/GREEN)

- [x] 2.1 Write test: `_verify_token` with valid HS256 secret → `AuthResult.OK` (RED — JWKS path fails)
- [x] 2.2 Write test: `_verify_token` with wrong secret → `AuthResult.BAD_SIGNATURE` (RED)
- [x] 2.3 Rewrite `_verify_token` in `app/auth/middleware.py` to HS256 via `settings.JWT_SHARED_SECRET` (GREEN)
- [x] 2.4 Write claim-mapping test: nameidentifier/role/BusinessId URIs → `request.state` (RED)
- [x] 2.5 Add URI constants (`NAMEID_URI`, `ROLE_URI`, `BUSINESS_CLAIM`) + map claims in middleware (GREEN)
- [x] 2.6 Write `_is_public_route` test: webhook path True, `/api/projects` False (RED)
- [x] 2.7 Add webhook path to `PUBLIC_ROUTES` in middleware (GREEN)
- [x] 2.8 Verify `app/auth/__init__.py` still exports `JWKSFetcher`/`get_jwks_fetcher`; update imports if middleware drops them

## Phase 3: Integration verification

- [x] 3.1 TestClient: protected `/api/projects` with no token → 401 (GREEN under enforced default)
- [x] 3.2 TestClient: valid token with forbidden role → 403
- [x] 3.3 TestClient: `POST /api/webhooks/payment-confirmed` no Bearer, valid secret → reaches handler
- [x] 3.4 TestClient: webhook no Bearer, invalid secret → 401 `invalid_webhook_secret`
- [x] 3.5 Run full suite: `pytest` green; `ruff check .` / `ruff format .` clean; `mypy` strict pass

## Phase 4: Cleanup / Docs

- [x] 4.1 Update `.env.example` with `JWT_SHARED_SECRET`
- [x] 4.2 Soft-blocked on `settings.JWT_SHARED_SECRET` empty → hard-fail at startup or reject 401 (confirm desired behavior at apply)
