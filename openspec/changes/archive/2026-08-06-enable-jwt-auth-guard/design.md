# Design: Enable JWT Auth Guard (HS256)

## Technical Approach

Replace JWKS/RS256 token verification in `app/auth/middleware.py` with symmetric
HS256 verification using a shared secret (`JWT_SHARED_SECRET`), map claims via the
real POSBackend ASP.NET URIs, default `JWT_AUTH_ENFORCED=True`, and exempt the
payment webhook from auth (it keeps its own secret check). Maps to RQ-JWT-01..04.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Token algorithm | HS256 shared secret | Keep RS256/JWKS | POSBackend #3107 issues HS256 with `Jwt:Secret`; JWKS needs an HTTP endpoint that adds latency/failure |
| Claim source | ASP.NET long URIs | Short `sub`/`role`/`business_id` | POSBackend issues long URIs (`.../identity/claims/role`, `BusinessId`); short names never populate state |
| Enforcement default | `JWT_AUTH_ENFORCED=True` | Keep `False` | Frontend already sends Bearer (verified #3106); enforcement is the point of the change |
| Webhook auth | Exempt from middleware | Rely on middleware | Webhook uses its own `X-Webhook-Secret`; middleware would reject it as 401 |

## Data Flow

    Request → JWTAuthMiddleware.dispatch
      ├─ path in PUBLIC_ROUTES or webhook  → call_next (no auth)
      ├─ no Bearer header                  → 401 (enforced)
      └─ verify HS256 via jwt.decode(secret)
            ├─ fail (expired/bad sig/issuer) → 401
            ├─ role not allowed              → 403
            └─ ok → set request.state.{user_id, role_id, business_id} → call_next

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/config.py` | Modify | Add `JWT_SHARED_SECRET: str = ""`; default `JWT_AUTH_ENFORCED: bool = True` |
| `app/auth/middleware.py` | Modify | Drop JWKS fetcher use; HS256 verify with `settings.JWT_SHARED_SECRET`; map URI claims; exempt webhook path in `_is_public_route` |
| `app/auth/__init__.py` | Modify | Keep exports (`JWKSFetcher`, `get_jwks_fetcher`) to avoid import breakage; middleware no longer imports it |
| `app/main.py` | Modify | None required for webhook (path exempt in middleware); optionally confirm webhook router mounted |

## Interfaces / Contracts

Claim constants:
```python
NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
BUSINESS_CLAIM = "BusinessId"
```
`request.state.user_id: str`, `role_id: int`, `business_id: str`.

Verify call:
```python
claims = jwt.decode(token, settings.JWT_SHARED_SECRET,
                    algorithms=["HS256"],
                    issuer=settings.JWT_ISSUER or None,
                    audience=settings.JWT_AUDIENCE or None)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_verify_token` HS256 | `jose.jwt.encode` mock token; valid → OK, wrong secret → BAD_SIGNATURE |
| Unit | claim mapping | token with nameidentifier/role/BusinessId → state populated; missing BusinessId → `""` |
| Unit | `_is_public_route` | webhook path returns True; `/api/projects` returns False |
| Integration | enforcement + role gate + webhook | TestClient: no token→401, forbidden role→403, webhook no-Bearer→handler, bad webhook secret→401 |

## Migration / Rollout

No DB migration. Deploy code, then set `JWT_SHARED_SECRET` env to POSBackend's
`Jwt:Secret` value. Rollback: set `JWT_AUTH_ENFORCED=False` env to restore
permissive mode without code revert.

## Open Questions

- [ ] Confirm exact `JWT_ISSUER`/`JWT_AUDIENCE` values to use (`http://localhost` per #3107) — verify at apply time.
