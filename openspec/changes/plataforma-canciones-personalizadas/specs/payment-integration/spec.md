# Payment Integration Specification (POSBackend)

## Purpose

Define the payment gateway integration in POSBackend (.NET) to enable Mercado Pago checkout for song purchases. This spec defines WHAT must be built — the implementation lives in the `PosBackend` repository at `~/Descargas/PosBackend/`.

## Requirements

### RQ-PAY-01: DI Registration

The system MUST register `IMercadoPagoService` in the DI container. The `// TODO` or commented-out registration in `Program.cs` MUST be enabled and verified.

#### Scenario: Service registered on startup

- GIVEN `Program.cs` with the DI registration uncommented
- WHEN the application starts
- THEN `IMercadoPagoService` MUST resolve without throwing
- AND the service MUST be configured with credentials from `appsettings.json`

#### Scenario: Missing MP credentials fails gracefully

- GIVEN `appsettings.json` without Mercado Pago credentials
- WHEN the application starts
- THEN DI registration MUST NOT throw on startup
- AND any call to `CreatePreferenceAsync` MUST return a clear configuration error

### RQ-PAY-02: Payment Gateway Resolver

The system MUST implement `IPaymentGatewayResolver` using the Factory pattern to select the active payment gateway. The resolver MUST return a gateway instance based on configuration or the `PaymentGatewayConfigs` table.

#### Scenario: Resolver returns Mercado Pago

- GIVEN `ActiveGateway = "mercadopago"` in config
- WHEN `IPaymentGatewayResolver.GetGatewayAsync()` is called
- THEN the returned gateway MUST implement `IPaymentGateway`
- AND `PaymentGatewayType` MUST be `MercadoPago`

#### Scenario: Resolver returns null for unknown gateway

- GIVEN `ActiveGateway = "unknown-gateway"` in config
- WHEN `GetGatewayAsync()` is called
- THEN the result MUST be a failure result with a clear error message

### RQ-PAY-03: Payment Gateway Application

The system MUST implement `TestGatewayConnectionAsync` in `PaymentGatewayApplication` to verify gateway connectivity. The method MUST return success/failure with a diagnostic message.

#### Scenario: Gateway connection succeeds

- GIVEN valid Mercado Pago credentials
- WHEN `TestGatewayConnectionAsync()` is called
- THEN the result MUST indicate success
- AND a timestamped connection log entry MUST be persisted

#### Scenario: Gateway connection fails

- GIVEN invalid or revoked Mercado Pago credentials
- WHEN `TestGatewayConnectionAsync()` is called
- THEN the result MUST indicate failure
- AND the error detail MUST include the API error message

### RQ-PAY-04: Webhook Processing

The system MUST implement `ProcessWebhookAsync` to handle Mercado Pago IPN notifications and update `Donation` / `Subscription` status in the database.

#### Scenario: Payment approved webhook

- GIVEN an IPN notification with `topic=payment` and `status=approved`
- WHEN `ProcessWebhookAsync` is called
- THEN the corresponding Donation record MUST be updated to `status=completed`
- AND the payment `external_reference` MUST match the project_id

#### Scenario: Payment rejected webhook

- GIVEN an IPN notification with `status=rejected`
- WHEN `ProcessWebhookAsync` is called
- THEN the Donation status MUST be updated to `failed`
- AND the error reason MUST be stored

#### Scenario: Duplicate webhook (idempotency)

- GIVEN an IPN notification with an already-processed `payment_id`
- WHEN `ProcessWebhookAsync` is called again
- THEN the handler MUST NOT create a duplicate record
- AND MUST return success (idempotent)

### RQ-PAY-05: Subscription Billing

The system MUST connect `SubscriptionApplication` recurring billing to the payment gateway resolver so that scheduled payments use the configured active gateway.

#### Scenario: Recurring charge uses active gateway

- GIVEN a subscription due for billing
- WHEN `SubscriptionApplication.ProcessRecurringCharge()` executes
- THEN it MUST call the resolver's gateway
- AND the payment MUST use Mercado Pago SDK

### RQ-PAY-06: Configuration Source

The gateway configuration (API keys, webhook secret, active gateway) MUST come from `appsettings.json` OR the `PaymentGatewayConfigs` database table. The system MUST define which takes precedence.

#### Scenario: Config read from appsettings

- GIVEN `appsettings.json` with `PaymentGateway:ActiveGateway=mercadopago`
- WHEN the resolver initializes
- THEN `ActiveGateway` MUST be `mercadopago`

#### Scenario: Database config overrides appsettings

- GIVEN a row in `PaymentGatewayConfigs` with `Key=ActiveGateway, Value=paypal`
- WHEN the resolver initializes with DB-overrides-appsettings policy
- THEN the active gateway MUST be `paypal`

## Open Questions

1. Does appsettings.json take precedence over DB or vice versa?
2. Is `PaymentGatewayConfigs` table already migrated or does it need a new migration?
3. Should `TestGatewayConnectionAsync` be called on startup or exposed as an admin endpoint?
4. What is the exact IPN webhook URL format that MP should call?

## Acceptance Criteria

- [ ] `IMercadoPagoService` resolves from DI without error
- [ ] `IPaymentGatewayResolver` returns MercadoPago when configured
- [ ] `TestGatewayConnectionAsync` succeeds with valid credentials
- [ ] IPN webhooks update payment status in DB
- [ ] Duplicate webhooks are idempotent
- [ ] Subscription recurring billing goes through the resolver
