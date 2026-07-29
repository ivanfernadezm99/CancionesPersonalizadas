# Proposal: Plataforma Canciones Personalizadas

## Intent

End-to-end monetization platform for AI-generated songs across 3 codebases. Users create song projects, preview clips, pay via Mercado Pago, and receive full songs. CancionesPersonalizadas (FastAPI) generates songs, POSBackend (.NET) handles auth + payments, POSCuentasCorrientes (Angular) provides the UX.

## Scope

### In Scope
- Dockerize CancionesPersonalizadas (Dockerfile + docker-compose for local dev)
- JWT auth middleware in CancionesPersonalizadas (validate tokens signed by POSBackend)
- Enable Mercado Pago in POSBackend: uncomment DI wiring, fix webhook persistence, add gateway resolver/factory
- Create "Canciones Personalizadas" feature module in POSCuentasCorrientes (Angular)
- Payment-gated final song delivery: preview free, full song after MP confirmation
- POSBackend payment webhooks persist to database

### Out of Scope
- PayPal / Stripe gateways (already coded but disabled — deferred)
- Voice cloning (v2)
- User registration / profile (reuses POS auth)
- Admin dashboard or song metrics
- Mobile apps (web-only v1)
- Recurring billing / subscription plans

## Capabilities

### New Capabilities
- `user-auth`: JWT validation middleware — verify POSBackend-issued tokens, extract user identity, reject expired/malformed tokens
- `docker-deployment`: Dockerfile + docker-compose for CancionesPersonalizadas with env-configurable settings
- `payment-integration`: Payment flow API in POSBackend — create MP preference, handle IPN webhook, verify payment status, persist transactions

### Modified Capabilities
- `song-projects`: Add payment-required check before final song generation; project status includes `payment_pending` state
- `audio-streaming`: Gate full audio download behind payment verification; free preview limited to 30s clip for unpaid projects

## Approach

```
┌──────────────────────┐     ┌──────────────────┐     ┌─────────────────────────┐
│  POSCuentas          │────▶│  POSBackend      │────▶│  CancionesPerson.      │
│  Corrientes          │     │  (.NET 8)        │     │  (FastAPI / Docker)     │
│  (Angular 21)        │◀────│  Auth + Payments │◀────│  Song Generation        │
│  Railway             │     │  Railway         │     │  Local / Railway        │
└──────────────────────┘     └──────────────────┘     └─────────────────────────┘
       │                             │                         │
       │ 1. Login                    │                         │
       │ 2. Create project ◀───────────────────────────────────┤
       │ 3. Add story fragments ──────────────────────────────▶│
       │ 4. Preview (free) ◀───────────────────────────────────┤
       │ 5. Pay via MP ───────────▶│                         │
       │ 6. Payment webhook ◀──────│                         │
       │ 7. Get full song ◀────────────────────────────────────┤
       │ 8. Download                │                         │
```

**Auth flow**: Frontend sends JWT (from POSBackend login) to both backends. CancionesPersonalizadas validates via JWKS endpoint or shared public key — no proxy/gateway needed.

**Payment flow**: Frontend creates MP preference via POSBackend → user pays on MP checkout → POSBackend IPN webhook persists payment → CancionesPersonalizadas checks payment status before serving full song.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `CancionesPersonalizadas/` | New | Dockerfile, docker-compose.yml, .dockerignore |
| `CancionesPersonalizadas/app/main.py` | Modified | Add JWT middleware to all protected routes |
| `CancionesPersonalizadas/app/auth/` | New | JWT validation module (token decode, key fetch) |
| `CancionesPersonalizadas/app/config.py` | Modified | Auth settings (JWKS_URL, AUDIENCE) |
| `CancionesPersonalizadas/app/projects/` | Modified | Payment status check before final generation |
| `PosBackend/src/PaymentGateway/` | Modified | Enable DI, fix stubs, add resolver/factory pattern |
| `PosBackend/src/Controllers/PaymentWebhookController.cs` | Modified | IPN persistence logic (replace // TODO) |
| `POSCuentasCorrientes/src/app/canciones-personalizadas/` | New | Feature module with project editor, preview player, payment UI |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|-------------|
| Mercado Pago SDK version mismatch or API changes | Med | Test with sandbox first; pin SDK version |
| JWKS key rotation desync between backends | Low | Use JWKS endpoint (auto-refresh) instead of static key |
| Railway deployment conflicts during staged rollout | Med | Dockerize local first; deploy POSBackend changes separately |
| Angular module conflicts with existing POS routing | Low | Lazy-loaded feature module with isolated routes |
| Webhook delivery failures (MP → POSBackend) | Low | Idempotency key + retry queue in POSBackend |

## Rollback Plan

- **CancionesPersonalizadas**: `docker compose down` + `git revert` auth changes
- **POSBackend**: Re-disable MP DI wiring, revert webhook changes, re-deploy
- **POSCuentasCorrientes**: Remove feature module + route, re-deploy to Railway

## Dependencies

- Mercado Pago SDK for .NET (already in POSBackend, version pin needed)
- POSBackend JWKS endpoint or public key (exposed via new endpoint)
- Docker + Docker Compose on local dev machines
- Railway access for POSBackend + POSCuentasCorrientes deployment

## Success Criteria

- [ ] `docker compose up` starts all CancionesPersonalizadas services (API, DB)
- [ ] Unauthenticated requests to CancionesPersonalizadas return 401
- [ ] Authenticated user creates project, adds fragments, generates preview
- [ ] User completes MP payment via POSBackend (sandbox)
- [ ] POSBackend webhook creates payment record in DB with correct status
- [ ] Full song downloads only after payment confirmed
- [ ] Angular module renders project editor, preview player, and payment UI
