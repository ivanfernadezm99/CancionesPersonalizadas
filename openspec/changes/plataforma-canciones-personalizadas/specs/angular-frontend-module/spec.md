# Angular Frontend Module Specification (POSCuentasCorrientes)

## Purpose

Define the Angular feature module for Canciones Personalizadas in the POSCuentasCorrientes app. This spec defines WHAT the module must provide — the implementation lives in the `POSCuentasCorrientes` repository at `~/Descargas/POSCuentasCorrientes/`.

## Requirements

### RQ-ANG-01: Feature Module Structure

The system MUST provide a lazy-loaded feature module `CancionesPersonalizadasModule` under `src/app/canciones-personalizadas/` with its own routing, components, and services.

#### Scenario: Module lazy-loads on navigation

- GIVEN an authenticated user
- WHEN navigating to `/canciones/landing`
- THEN the module MUST be lazy-loaded
- AND the landing page MUST render within 2s

### RQ-ANG-02: Routes

The module MUST define these routes with lazy loading:

| Route | Component | Purpose |
|-------|-----------|---------|
| `/canciones/landing` | LandingComponent | Welcome page, CTA to create |
| `/canciones/create` | CreateProjectComponent | Form: recipient, genre, mood, voice, fragments |
| `/canciones/preview/:id` | PreviewComponent | Listen to 30s preview, accept/retry |
| `/canciones/checkout/:id` | CheckoutComponent | Show MP payment button, status polling |
| `/canciones/download/:id` | DownloadComponent | Download or stream full song after payment |

#### Scenario: Route navigation works

- GIVEN the module is loaded
- WHEN navigating to each route
- THEN the corresponding component MUST render
- AND `/:id` params MUST resolve to valid project/job IDs

#### Scenario: Unknown route under /canciones/

- GIVEN a navigation to `/canciones/unknown`
- WHEN the router resolves
- THEN a 404 page or redirect to `/canciones/landing` MUST occur

### RQ-ANG-03: Service Integration

The module MUST provide `CancionesService` (HTTP to CancionesPersonalizadas API) and `PaymentService` (MP checkout via POSBackend). Both MUST reuse the app's existing JWT auth token for authenticated requests.

#### Scenario: CancionesService calls protected API

- GIVEN an authenticated user with a valid JWT
- WHEN `CancionesService.getProjects()` is called
- THEN the HTTP request MUST include `Authorization: Bearer {token}`
- AND the JWT MUST be the one from core auth module

#### Scenario: PaymentService creates preference

- GIVEN an authenticated user with a project ready for checkout
- WHEN `PaymentService.createPreference(projectId)` is called
- THEN the request MUST go to POSBackend's checkout endpoint
- AND the response MUST include `init_point` for MP redirect

### RQ-ANG-04: UI Design

The module MUST follow the POSCuentasCorrientes design system: cards, border-radius, blue primary color (`#1976D2`), consistent spacing and typography.

#### Scenario: Components render with correct styles

- GIVEN any component in the module
- WHEN rendered in the browser
- THEN CSS classes MUST match the app design system
- AND color palette MUST use the app primary/secondary colors

### RQ-ANG-05: Reuse Core Auth

The module MUST reuse the existing JWT auth infrastructure from `core/auth` module. No separate login or token management is needed.

#### Scenario: JWT from core auth used for API calls

- GIVEN a user logged into POSCuentasCorrientes
- WHEN the Canciones module makes API calls
- THEN the interceptor from core/auth MUST attach the JWT
- AND 401 responses MUST trigger the core auth logout flow

### RQ-ANG-06: Payment Status Polling

The `CheckoutComponent` MUST poll project status after redirecting to Mercado Pago to detect when the project transitions to `paid`.

#### Scenario: Polling detects payment

- GIVEN user is redirected back from MP after payment
- WHEN the component polls `GET /api/projects/{id}` every 3s
- THEN when status becomes `paid`, the component MUST navigate to `/canciones/download/{id}`
- AND polling MUST stop

#### Scenario: Polling timeout

- GIVEN the project does not become `paid` after 5 minutes
- WHEN the polling interval expires
- THEN the component MUST show a "Payment still processing" message
- AND offer a manual refresh button
- AND polling MUST stop

## Open Questions

1. Should the Canciones module be inside `features/` or `modules/` in POSCuentasCorrientes?
2. Does POSCuentasCorrientes already have a shared MercadoPagoService or does it need to be created?
3. What is the base URL for CancionesPersonalizadas API from the Angular app (same domain? proxy? subdomain?)?

## Acceptance Criteria

- [ ] Module lazy-loads at `/canciones/*`
- [ ] All 5 routes render their components
- [ ] JWT from core auth is attached to all API calls
- [ ] CancionesService calls CancionesPersonalizadas API
- [ ] PaymentService calls POSBackend checkout endpoint
- [ ] Payment status polling works with timeout
- [ ] UI follows the app's design system
