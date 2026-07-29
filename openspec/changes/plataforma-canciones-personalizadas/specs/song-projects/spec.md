# Delta for Song Projects

## ADDED Requirements

### RQ-PRJ-07: Create Checkout Preference

The system MUST expose `POST /api/projects/{id}/checkout` that creates a Mercado Pago payment preference via POSBackend and returns `preference_id` and `init_point`.

#### Scenario: Checkout created for valid project

- GIVEN a project with status `preview_ready` and at least one generated preview
- WHEN POST /api/projects/{id}/checkout is called with auth
- THEN the response MUST be 200 with `preference_id` and `init_point`
- AND the project status MUST change to `payment_pending`

#### Scenario: Checkout on already-paid project

- GIVEN a project with status `paid`
- WHEN POST /api/projects/{id}/checkout is called
- THEN the response MUST be 409 with `{"detail": "Project already paid"}`

#### Scenario: Checkout on draft with no preview

- GIVEN a project with status `draft` and no previews
- WHEN POST /api/projects/{id}/checkout is called
- THEN the response MUST be 422 with `{"detail": "Generate a preview first"}`

### RQ-PRJ-08: Mark Project as Paid (Webhook)

The system MUST expose `POST /api/projects/{id}/payment-confirmed` (or be called by POSBackend webhook) to update project status from `payment_pending` to `paid`.

#### Scenario: Payment confirmed transitions project

- GIVEN a project with status `payment_pending`
- WHEN the webhook calls the payment-confirmed endpoint
- THEN project status MUST be `paid`
- AND `paid_at` timestamp MUST be recorded

#### Scenario: Confirming already-paid project

- GIVEN a project with status `paid`
- WHEN the webhook calls the endpoint
- THEN the endpoint MUST return 200 (idempotent)
- AND `paid_at` MUST NOT be overwritten

## MODIFIED Requirements

### RQ-PRJ-01: Create Project

The system MUST expose `POST /api/projects` accepting `recipient`, `relationship`, `genre`, `mood`, `voice`, and optional `reference_song`. Returns 201 with `project_id`. Valid statuses: `draft`, `preview_ready`, `payment_pending`, `paid`, `completed`.
(Previously: valid statuses: `draft`, `generating`, `completed`)

#### Scenario: Happy path creation

- GIVEN valid `recipient`, `genre`, and `reference_song`
- WHEN POST /api/projects is called
- THEN response MUST be 201 with a UUID `project_id`
- AND status MUST be `draft`

#### Scenario: Missing required recipient

- GIVEN a request without `recipient`
- WHEN POST /api/projects is called
- THEN response MUST be 422

### RQ-PRJ-04: Generate Final Song

`POST /api/projects/{id}/final`. The system MUST check project status is `paid` before initiating final generation. If status is not `paid`, MUST return 402 (Payment Required).
(Previously: no payment check — any project could generate final song)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| Paid project generates | project status = `paid` | POST /final | 202 + job_id |
| Unpaid project rejected | project status = `preview_ready` or `draft` | POST /final | 402 Payment Required |
| No fragments | project without fragments | POST /final | 422 |

## REMOVED Requirements

None.

## RENAMED Requirements

None.
