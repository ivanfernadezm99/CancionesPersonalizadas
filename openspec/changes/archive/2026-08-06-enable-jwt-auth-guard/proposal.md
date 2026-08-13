# Proposal: Enable JWT Auth Guard (HS256)

## Intent

The auth middleware currently verifies tokens via JWKS + RS256 with short claim
names (`sub`, `role`, `business_id`), but POSBackend issues HS256 tokens with a
shared secret and long ASP.NET claim URIs. Auth is also disabled by default
(`JWT_AUTH_ENFORCED=False`). This change migrates the middleware to HS256 shared
secret, enforces auth by default, exempts the payment webhook, and syncs claim
mapping to the real POSBackend JWT format so protected endpoints actually work.

## Scope

### In Scope
- Migrate `app/auth/middleware.py` verification from JWKS/RS256 → HS256 with `JWT_SHARED_SECRET`
- Sync claim mapping: `sub`→nameidentifier URI, `role`→role URI, `business_id`→`BusinessId`
- Set `JWT_AUTH_ENFORCED=True` as default
- Exempt `POST /api/webhooks/payment-confirmed` from auth (webhook has its own secret)

### Out of Scope
- MP webhook dispatch in POSBackend (follow-up: `add-mp-webhook-handler`)
- Migrating to RS256/JWKS later
- Removing the old JWKS fetcher code

## Capabilities

### New Capabilities
- `auth`: JWT middleware auth — HS256 token verification, claim mapping, role gate, public/webhook route exemption

### Modified Capabilities
None

## Approach

Replace JWKS+RS256 verification with HS256 `jwt.decode(token, secret, HS256)`.
Map claims via full ASP.NET URIs. Default `JWT_AUTH_ENFORCED=True`. Add
`JWT_SHARED_SECRET` to settings and a webhook path to the public-route exemption.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/auth/middleware.py` | Modified | HS256 verify, claim mapping, webhook exemption |
| `app/auth/__init__.py` | Modified | Keep/fix dependencies exported by middleware |
| `app/config.py` | Modified | Add `JWT_SHARED_SECRET`, default enforced True |
| `app/main.py` | Modified | None (webhook already mounted); exemption in middleware |
| `tests/` | New | Token verification, role gate, webhook exemption tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Wrong claim URI breaks role/business mapping | Med | Unit tests with mock token per POSBackend spec (#3107) |
| Enforcing auth locks out frontend | Low | Frontend interceptor already sends Bearer (verified #3106) |
| Webhook 401s after enforcement | Med | Exempt webhook path; keep its own `X-Webhook-Secret` check |

## Rollback Plan

Revert `JWT_AUTH_ENFORCED` to `False` via env (no code change) to restore
permissive mode. Code revert = `git revert` of the middleware/config change.

## Dependencies

- POSBackend JWT: issuer=audience=`http://localhost`, HS256, secret=`Jwt:Secret`, role URI `.../identity/claims/role`, business claim `BusinessId`

## Success Criteria

- [ ] HS256 token with valid secret → 200; wrong secret → 401
- [ ] role + business_id correctly set on `request.state`
- [ ] webhook `POST /api/webhooks/payment-confirmed` works without Bearer
- [ ] Full test suite passes with `JWT_AUTH_ENFORCED=True`
