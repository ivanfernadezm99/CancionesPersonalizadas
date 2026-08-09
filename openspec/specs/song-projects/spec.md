# Song Projects Specification

## Purpose

Provide an iterative song creation workflow where users build story fragments over time, generate 30s previews, and produce final 2+ min songs. Projects accumulate context incrementally with a reference song for style guidance.

## Requirements

### RQ-PRJ-01: Create Project

The system MUST expose `POST /api/projects` accepting `recipient`, `relationship`, `genre`, `mood`, `voice`, and optional `reference_song`. Returns 201 with `project_id`.

#### Scenario: Happy path creation

- GIVEN valid `recipient`, `genre`, and `reference_song`
- WHEN POST /api/projects is called
- THEN response MUST be 201 with a UUID `project_id`
- AND status MUST be `draft`

#### Scenario: Missing required recipient

- GIVEN a request without `recipient`
- WHEN POST /api/projects is called
- THEN response MUST be 422

### RQ-PRJ-02: Add Story Fragment

The system MUST expose `PATCH /api/projects/{id}` accepting optional `genre`, `mood`, `voice`, `reference_song` changes and an optional `fragment` object with `text` (max 2000 chars). Returns 200.

#### Scenario: Add first fragment

- GIVEN an existing project
- WHEN PATCH with `{"fragment": {"text": "Nuestro primer viaje"}}`
- THEN response MUST be 200
- AND fragment MUST appear in GET with `sort_order: 1`

#### Scenario: Add third fragment

- GIVEN a project with 2 fragments
- WHEN PATCH with a new fragment
- THEN sort_order MUST be 3
- AND accumulated story MUST be "frag1 frag2 frag3"

#### Scenario: Project not found

- GIVEN a non-existent project_id
- WHEN PATCH is called
- THEN response MUST be 404

### RQ-PRJ-03: Generate Preview

The system MUST expose `POST /api/projects/{id}/preview` that creates a job with model `lyria-3-clip-preview` and returns 202 with `job_id`. The accumulated story is concatenated and truncated at 2000 chars for the prompt.

#### Scenario: Preview created

- GIVEN a project with fragments
- WHEN POST /api/projects/{id}/preview
- THEN response MUST be 202 with a `job_id`
- AND a row MUST exist in `project_jobs` with `job_type: "preview"`
- AND the job's model param MUST be `lyria-3-clip-preview`

#### Scenario: Empty project preview

- GIVEN a project with no story fragments
- WHEN POST /api/projects/{id}/preview
- THEN response MUST be 422
- AND error MUST indicate "no story fragments"

### RQ-PRJ-04: Generate Final Song

`POST /api/projects/{id}/final`. OpenClaw: clip-chain when `chaining_enabled`, else pro-preview. Suno: single generate call — chaining irrelevant.
(Previously: always OpenClaw, no provider branching)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw chained | `chaining_enabled`, OpenClaw | POST /final | 202 + job_id, clip-chaining |
| OpenClaw no chain | no chaining, OpenClaw | POST /final | 202 + job_id, pro-preview, no stitch |
| Suno single call | `music_provider=suno` | POST /final | 202 + job_id, SunoProvider, NO chaining |
| No fragments | project without fragments | POST /final | 422 |

### RQ-PRJ-05: Get Project

The system MUST expose `GET /api/projects/{id}` returning project settings, fragments (by sort_order), and previews (by newest first) with their job status.

#### Scenario: Full project response

- GIVEN a project with 2 fragments and 1 preview job
- WHEN GET /api/projects/{id}
- THEN response MUST include `recipient`, `genre`, `mood`, `voice`, `reference_song`
- AND `fragments` array MUST have 2 items ordered by sort_order
- AND `previews` array MUST have 1 item with job_id and status

#### Scenario: Project not found

- GIVEN a non-existent project_id
- WHEN GET /api/projects/{id}
- THEN response MUST be 404

### RQ-PRJ-06: Story Accumulation

The system MUST concatenate all fragments ordered by sort_order. The accumulated story string MUST be truncated to 2000 characters before being passed to the generation prompt.

#### Scenario: Accumulation under limit

- GIVEN fragments ["Hola", "Mundo"]
- WHEN accumulated
- THEN result MUST be "Hola Mundo"
- AND no truncation occurs

#### Scenario: Accumulation exceeds limit

- GIVEN fragments totalling 2500 characters
- WHEN accumulated
- THEN the result MUST be at most 2000 characters
- AND the result MUST end with "..."

### RQ-PRJ-09: Asynchronous Preview UI Re-render

The preview UI MUST re-render the template whenever async subscription callbacks (initial project load and job-status polling) mutate render state (`project`, `loading`, `streamUrl`). This MUST hold under zoneless change detection; polling/spinner state MUST reflect real subscription outcomes. (Scope: `canciones-personalizadas/preview`, plus defensive audit of `download`/`create`.)

#### Scenario: Existing complete preview renders player without regeneration

- GIVEN a stored project whose latest preview job has `status: complete`
- WHEN the preview page loads and the initial project subscription resolves
- THEN the template MUST render the sample player showing the preview stream URL
- AND MUST NOT re-queue or regenerate the preview
- AND `loading` MUST become `false`

#### Scenario: Queued preview shows spinner then player on completion

- GIVEN a project with a `queued`/`processing` preview job for the first visit
- WHEN the page loads
- THEN the template MUST show a "Generating preview…" spinner (`loading: true`)
- WHEN the polling subscription observes the job transition to `complete`
- THEN the template MUST swap the spinner for the player within the same change detection cycle
- AND `loading` MUST become `false` and `streamUrl` MUST be set

#### Scenario: Subscription error updates the view

- GIVEN a project whose initial load or poll fails
- WHEN the `error` handler runs and mutates state
- THEN the template MUST reflect the error state (no stale spinner)
- AND the UI MUST offer retry/back navigation

#### Scenario: Defensive CDR across preview/download/create async handlers

- GIVEN any in-subscription field mutation in the `preview`, `download`, or `create` components
- WHEN the subscription callback completes synchronously
- THEN the affected template region MUST re-render within the same change-detection cycle
- AND the component MUST NOT rely on data that remains stale under zoneless change detection

### RQ-DIT-01: Replace All Fragments

The system MUST expose `PUT /projects/{id}/fragments` accepting `fragments: list[str]`. It MUST replace all existing fragments with the provided set in a single SQLite transaction (DELETE-all + INSERT-set), resetting sort_order sequentially from 1. On success it MUST return 200 with the updated project.

#### Scenario: Atomic replace happy path

- GIVEN an existing draft project with fragments `["viejo"]`
- WHEN PUT /projects/{id}/fragments with `{"fragments": ["nuevo", "otro"]}`
- THEN response MUST be 200
- AND GET /projects/{id} MUST return exactly those 2 fragments ordered by sort_order

#### Scenario: Replace with empty list

- GIVEN an existing draft project
- WHEN PUT /projects/{id}/fragments with `{"fragments": []}`
- THEN response MUST be 200
- AND GET /projects/{id} MUST return an empty fragments array

### RQ-DIT-02: Editable Status Gate

The system MUST return 409 Conflict for `PUT /projects/{id}/fragments` when the project's `status` is `paid` or `completed`. Delivered songs MUST NOT be editable. Draft/processing projects MUST remain editable.

#### Scenario: Paid project rejected

- GIVEN a project with `status: paid`
- WHEN PUT /projects/{id}/fragments is called
- THEN response MUST be 409 Conflict
- AND fragments MUST remain unchanged

#### Scenario: Draft project accepted

- GIVEN a project with `status: draft`
- WHEN PUT /projects/{id}/fragments is called
- THEN response MUST be 200

### RQ-DIT-03: Edit Route in Create Component

The frontend `CreateProjectComponent` MUST detect a route param `:id` on `/canciones/edit/:id` and MUST enter edit mode.

#### Scenario: edit/:id renders component in edit mode

- GIVEN the route `/canciones/edit/{id}` is activated
- WHEN `CreateProjectComponent` initializes
- THEN the component MUST run in edit mode with the project `id` captured from the route

### RQ-DIT-04: Edit Mode Prefill

In edit mode, the component MUST fetch the project via `getProject(id)` and populate `model` (settings) plus `fragments[]`, preserving `reference_audio_url`. Existing fragments MUST NOT be cleared until a successful submit.

#### Scenario: Edit mode populates model and fragments

- GIVEN an existing project with fragments and a reference audio
- WHEN edit mode loads and `getProject(id)` resolves
- THEN the form MUST show the project's model fields, fragments, and preserve `reference_audio_url`
- AND existing fragments MUST remain until submit succeeds

### RQ-DIT-05: Rehacer Navigation

The "Rehacer" button in the preview component MUST navigate to `/canciones/edit/{project.id}` instead of the create route, so iterations edit the same project rather than duplicating it.

#### Scenario: Rehacer links to edit route

- GIVEN a project with `id` on the preview page
- WHEN "Rehacer" is triggered
- THEN the template binding MUST navigate to `/canciones/edit/{project.id}`
- AND MUST NOT navigate to `/canciones/create`
