# Apply Progress: Enable JWT Auth Guard (HS256)

## Status
COMPLETE — all tasks T1-T8 done, strict TDD. Backend only (CancionesPersonalizadas).

## Completed
- [x] Config (`app/config.py`): JWT_ALGORITHM="HS256", JWT_SHARED_SECRET="" (env), JWT_ISSUER="http://localhost", JWT_AUDIENCE="http://localhost", JWT_AUTH_ENFORCED=True, JWT_ALLOWED_ROLES=frozenset({1,2,3,4,5}). Kept deprecated JWT_JWKS_URL.
- [x] `app/auth/__init__.py`: JWKSFetcher -> HS256KeyProvider; get_jwks_fetcher() -> get_key_provider(). Kept JWKSFetcher/get_jwks_fetcher/_jwks_fetcher aliases for import compat (app/auth/router.py + tests/test_projects/test_payment.py).
- [x] `app/auth/middleware.py`: _verify_token via jwt.decode(settings.JWT_SHARED_SECRET, algorithms=["HS256"], issuer, audience, verify_exp=True). Claims from ASP.NET URIs: NAMEID_URI/ROLE_URI/BUSINESS_CLAIM. Added /api/webhooks/payment-confirmed to PUBLIC_ROUTES (exact string match). Removed JWKS fetch + kid logic.
- [x] Tests `tests/test_auth/test_jwt_auth_guard.py` (4 new): valid HS256+state, missing token 401, webhook exempt 404-project_not_found, role enforcement 403.
- [x] Migrated `tests/test_auth/test_auth_middleware.py` from JWKS/RS256 to HS256 (was passing, in-scope). 27 tests pass.
- [x] `.env.example`: added JWT_SHARED_SECRET/ISSUER/AUDIENCE/ENFORCED/ALLOWED_ROLES + PAYMENT_WEBHOOK_SECRET.
- [x] tasks.md: all 17 checkboxes marked.

## Tests
- tests/test_auth/test_jwt_auth_guard.py: 4 passed.
- tests/test_auth/: 27 passed.
- Full suite: 342 passed, 5 failed — same 5 pre-existing failures (test_full_flow x2, test_integration x1, test_lyrics_providers x2). 0 new failures.
- ruff check/format app/auth/ clean. mypy app/auth/ strict pass.

## Blast-radius handling
JWT_AUTH_ENFORCED default flipped False->True. Added autouse fixture `_permissive_auth_default` in tests/conftest.py setting JWT_AUTH_ENFORCED=False so non-auth business tests (integration/full_flow/stream/projects) stay green; auth guard tests override to True.

## Decision 4.2 (soft-blocked)
Chose runtime 401 rejection for empty JWT_SHARED_SECRET (permissive fallback), NOT hard-fail at startup. Less disruptive; prod sets env.
