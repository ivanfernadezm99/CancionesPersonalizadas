# Tasks: Plataforma Canciones Personalizadas

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Estimated changed lines: ~1200–1500 across 3 repos (POSBackend ~250, CP ~550, Angular ~400).
Stacked PRs per repo: POSBackend 1 PR, CP 3 stacked PRs, Angular 1 PR.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | POSBackend: Enable MP DI, resolver, webhooks | PR 1 | Base = main (independent) |
| 2 | CP: Docker + auth + permissive mode | PR 2 | Base = feature/tracker branch |
| 3 | CP: Checkout, payment webhook, project states | PR 3 | Base = PR 2 branch |
| 4 | CP: Audio streaming gating (preview/402) | PR 4 | Base = PR 3 branch |
| 5 | Angular: Module + routes + components + services | PR 5 | Base = main; depends on PR 1 |

## Phase 1: POSBackend Payment Enablement

- [x] 1.1 `Program.cs` — Uncomment `IMercadoPagoService` DI registration (RQ-PAY-01)
- [x] 1.2 Create `IPaymentGatewayResolver` + factory pattern impl (RQ-PAY-02)
- [x] 1.3 Implement `PaymentGatewayApplication.TestGatewayConnectionAsync()` (RQ-PAY-03)
- [x] 1.4 Implement `PaymentWebhookController.ProcessWebhookAsync()` with idempotency (RQ-PAY-04)
- [x] 1.5 Connect `SubscriptionApplication` to resolver for recurring billing (RQ-PAY-05)
- [x] 1.6 Tests: DI resolves, resolver returns correct gateway, webhook approve/reject/idempotent

## Phase 2: CP Docker + Auth Foundation

- [x] 2.1 `Dockerfile` — Multi-stage, python:3.11-slim, uvicorn on :8000 (RQ-DKR-01)
- [x] 2.2 `docker-compose.yml`, `.env.docker`, `.dockerignore` (RQ-DKR-02/03/05)
- [x] 2.3 `GET /api/auth/health` public endpoint (RQ-DKR-04)
- [x] 2.4 `app/auth/__init__.py` — JWKS fetcher with TTL 3600s cache + eager refresh on failure (RQ-AUTH-01/02)
- [x] 2.5 JWT middleware: decode, validate sig/exp/iss/aud, inject `user_id`/`role_id`/`business_id` into `request.state` (RQ-AUTH-01/03)
- [x] 2.6 `JWT_AUTH_ENFORCED: bool` in config — permissive mode logs but does not reject (gate item 2)
- [x] 2.7 `app/config.py` — Add `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `PAYMENT_WEBHOOK_SECRET` (gate item 4)
- [x] 2.8 `app/main.py` — Wire middleware: protect `/api/*`, allow health+`/` (RQ-AUTH-03)
- [x] 2.9 Role enforcement: reject insufficient `role_id` with 403 (gate item 1 + RQ-AUTH-04)
- [x] 2.10 Tests: respx-mocked JWKS, valid/expired/malformed tokens, 503 on JWKS down, role 403, permissive passthrough

## Phase 3: CP Checkout + Payment Webhook + Project States

- [x] 3.1 `projects/store.py` — Alter CHECK constraint: `draft,preview_ready,payment_pending,paid,completed`; add `paid_at` column (RQ-PRJ-01)
- [x] 3.2 `app/projects/payment.py` — `POST /api/projects/{id}/checkout` proxy to POSBackend (RQ-PRJ-07)
- [x] 3.3 `POST /api/webhooks/payment-confirmed` — webhook handler with shared-secret auth (RQ-PRJ-08)
- [x] 3.4 Gate `POST /api/projects/{id}/final` — 402 if status != `paid` (RQ-PRJ-04)
- [x] 3.5 `app/models.py` — Add `CheckoutResponse`, `PaymentConfirmRequest`
- [x] 3.6 `projects/router.py` — Register checkout + payment-confirmed routes
- [x] 3.7 Tests: checkout with respx mock, webhook valid/invalid secret, final 402, status transitions

## Phase 4: CP Audio Streaming Gating

- [x] 4.1 `stream/router.py` — 402 on full stream if project not paid (RQ-STR-05)
- [x] 4.2 `?preview=true` support — truncate to 30s, `X-Freemium-Preview: true` header (RQ-STR-05)
- [x] 4.3 `X-Paid-Content: true` header on paid full streams (RQ-STR-03)
- [x] 4.4 Tests: preview truncation, 402 on unpaid, headers correct

## Phase 5: Angular Frontend Module (POSCuentasCorrientes)

- [x] 5.1 Generate `CancionesPersonalizadasModule` + lazy routes (RQ-ANG-01)
- [x] 5.2 `CancionesService` — HTTP to CP API with JWT interceptor (RQ-ANG-03)
- [x] 5.3 `PaymentService` — checkout via POSBackend (RQ-ANG-03)
- [x] 5.4 `LandingComponent` — welcome + CTA (RQ-ANG-02)
- [x] 5.5 `CreateProjectComponent` — form: recipient, genre, mood, voice, fragments (RQ-ANG-02)
- [x] 5.6 `PreviewComponent` — 30s player + accept/retry (RQ-ANG-02)
- [x] 5.7 `CheckoutComponent` — MP button + polling 3s/5min timeout (RQ-ANG-06)
- [x] 5.8 `DownloadComponent` — full song download/stream (RQ-ANG-02)
- [x] 5.9 Configure CP API base URL + CORS if needed (gate item 3)
- [x] 5.10 Tests: component render, service calls, polling, navigation

## Phase 6: Integration + Verification

- [x] 6.1 Full-flow integration: create → fragments → preview → checkout → webhook → final → stream
- [x] 6.2 Docker build + compose up + health endpoint verification
- [x] 6.3 Cross-repo contract checks: JWKS format, webhook secret, checkout response shape
- [x] 6.4 Update verification doc per spec scenarios
