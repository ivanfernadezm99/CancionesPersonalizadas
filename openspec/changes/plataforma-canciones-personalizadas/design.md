# Design: Plataforma Canciones Personalizadas

## Technical Approach

Monetization layer over the existing song generation engine. Three codebases: POSBackend (.NET) handles auth + payments, CancionesPersonalizadas (FastAPI) handles song projects + gated delivery, POSCuentasCorrientes (Angular 21) provides UX. This design covers what changes IN THIS REPO and the contracts with the other two.

## Architecture Decisions

### Decision: JWT Validation via JWKS

**Choice**: `python-jose[cryptography]` with on-demand JWKS fetch + TTL cache (3600s) + eager refresh on validation failure.
**Alternatives**: Shared HMAC secret (no rotation support), OAuth2 proxy/gateway (extra infra).
**Rationale**: JWKS lets POSBackend rotate keys without CP redeploy. Eager refresh on failure handles rotation transparently.

### Decision: Payment Webhook via POSBackend proxy

**Choice**: POSBackend receives MP IPN → persists tx → calls CP's `/api/projects/{id}/payment-confirmed`. CP never talks to MP directly.
**Alternatives**: CP calls POSBackend polling API; CP integrates MP SDK directly.
**Rationale**: Keeps payment SDK and credentials in POSBackend (existing code). CP only needs a shared secret to verify the webhook call.

### Decision: Project status new column vs CHECK constraint change

**Choice**: Alter the existing `CHECK(status IN (...))` to add new states — no schema versioning needed.
**Alternatives**: New table, status enum table.
**Rationale**: SQLite ALTER TABLE supports dropping/replacing CHECK via table recreation in migration. Minimal diff.

### Decision: Preview = job-level flag, not separate endpoint

**Choice**: `?preview=true` query param on `/api/stream/{job_id}`, truncating to 30s server-side.
**Alternatives**: Separate `/api/preview/{job_id}` endpoint.
**Rationale**: Simpler routing, no duplication. pydub slicing is trivially cheap.

## Data Flow

```
Angular (POSCuentasCorrientes)         POSBackend (.NET)          CancionesPersonalizadas (FastAPI)
        │                                    │                             │
        │── POST /api/projects ──────────────────────────────────────────▶│  Create project (draft)
        │── PATCH /api/projects/{id} ───── add fragments ────────────────▶│
        │── POST / .../preview ──────────────────────────────────────────▶│  Generate preview
        │── GET  /api/stream/{job_id}?preview=true ◀──────────────────────│  30s clip
        │                                    │                             │
        │── POST /api/checkout ────────────▶│  Create MP preference       │
        │◀── {preference_id, init_point} ───│                             │
        │── (redirect to MP)                │                             │
        │                                    │◀── MP IPN webhook          │
        │                                    │── ProcessWebhookAsync()    │
        │                                    │── POST /payment-confirmed─▶│  status → paid
        │── GET /api/projects/{id} (poll) ────────────────────────────────▶│  status = paid
        │── POST / .../final ────────────────────────────────────────────▶│  Generate final
        │── GET  /api/stream/{job_id} ◀───────────────────────────────────▶  Full song
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/auth/__init__.py` | Create | JWT middleware, JWKS fetcher, claims extractor |
| `app/config.py` | Modify | Add `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `PAYMENT_WEBHOOK_SECRET` |
| `app/main.py` | Modify | Wire auth middleware, add health endpoint, register payment routes |
| `app/projects/payment.py` | Create | Checkout endpoint, payment-confirmed webhook handler |
| `app/projects/store.py` | Modify | Expand project status CHECK constraint, add `paid_at` column |
| `app/projects/__init__.py` | Modify | `create_final_job` checks `status == "paid"` |
| `app/projects/router.py` | Modify | Add checkout + payment-confirmed routes |
| `app/stream/router.py` | Modify | Payment gate: 402 on full stream if not paid; 30s truncation on `?preview=true` |
| `app/models.py` | Modify | Add `CheckoutResponse`, `PaymentConfirmRequest` models |
| `Dockerfile` | Create | Multi-stage: python:3.11-slim, pip install, uvicorn |
| `docker-compose.yml` | Create | `api` service, env file, volumes, healthcheck |
| `.dockerignore` | Create | Exclude `__pycache__`, `.venv`, `.git`, `output/` |
| `.env.docker` | Create | Docker-friendly defaults (`host.docker.internal` for JWKS) |

## Interfaces / Contracts

### POSBackend → CP (payment webhook)

```
POST /api/projects/{id}/payment-confirmed
Headers:
  Authorization: Bearer <shared-secret>
Body: { "transaction_id": "mp-123", "status": "approved" }
Response 200: { "status": "paid" }
Response 409: { "detail": "Project already paid" }  (idempotent — return 200)
```

### CP → POSBackend (checkout delegation)

```
POST /api/checkout  (on POSBackend, called by Angular)
Headers: Authorization: Bearer <user-jwt>
Body: { "project_id": "...", "amount": 9.99, "currency": "ARS", "description": "Canción personalizada para ..." }
Response 200: { "preference_id": "mp-...", "init_point": "https://mercadopago.com/..." }
```

### Angular → CP

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/api/projects` | POST | JWT | 201 `{id, status}` |
| `/api/projects/{id}` | GET | JWT | `SongProjectResponse` |
| `/api/projects/{id}` | PATCH | JWT | `SongProjectResponse` |
| `/api/projects/{id}/preview` | POST | JWT | 202 `JobCreateResponse` |
| `/api/projects/{id}/final` | POST | JWT | 202 (402 if unpaid) |
| `/api/projects/{id}/checkout` | POST | JWT | 200 `{preference_id, init_point}` (409/422) |
| `/api/projects/{id}/reference-audio` | POST | JWT | `AudioReferenceResponse` |
| `/api/stream/{job_id}` | GET | JWT | audio/mpeg (402 if unpaid full) |
| `/api/status/{job_id}` | GET | JWT | `JobStatusResponse` |
| `/api/auth/health` | GET | None | 200 `{status: "ok"}` |
| `/` | GET | None | 200 API info |

### Claims Mapping (.NET → Python)

| .NET Claim | CP Key | Source |
|------------|--------|--------|
| `sub` | `user_id` | JWT `sub` |
| `role` | `role_id` | JWT `role` |
| `business_id` | `business_id` | JWT `business_id` |
| `exp` | — | Expiry validation |
| `iss` | — | Must match `JWT_ISSUER` |
| `aud` | — | Must match `JWT_AUDIENCE` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Auth middleware (valid/expired/malformed tokens, JWKS mock) | respx mock for JWKS, parametrized scenarios |
| Unit | Project status transitions, paid gate in `/final` | Test store directly with status checks |
| Unit | Stream logic: preview=30s truncation, 402 on unpaid full | Mock `get_job` + project store |
| Integration | Checkout endpoint calls POSBackend (httpx mock) | respx mock `POST /api/checkout` |
| Integration | Webhook endpoint with valid/invalid shared secret | Test client with `Authorization` header |
| Integration | Full flow: create → fragments → preview → mock checkout → mock webhook → final → stream | Asyncio integration test |

## Migration / Rollout

1. **POSBackend first**: Enable MP DI, expose JWKS endpoint, deploy to Railway
2. **DB migration**: Run `init_schema` with expanded CHECK constraint (idempotent ALTER)
3. **Deploy CP**: With auth middleware in "permissive" mode (validate but don't reject) initially, then flip to enforcing after Angular connects
4. **Angular module**: Deploy last, after both backends are live

## Open Questions

- [ ] JWKS URL: `JWKS_URL` env var on CP pointing to `https://posbackend/api/.well-known/jwks` — need exact POSBackend endpoint path
- [ ] Webhook secret: hardcode as env var `PAYMENT_WEBHOOK_SECRET`, shared manually between POSBackend and CP
- [ ] Angular routing: CP API base URL — same origin proxy, subdomain, or absolute URL?
