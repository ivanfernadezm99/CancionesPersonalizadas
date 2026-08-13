# Delta for song-projects

## Modified Capability: song-projects

Adds an **edit workflow** on top of the existing iterative project lifecycle. Users can replace a draft's story fragments (via "Rehacer") and resubmit, instead of appending duplicates. All requirements below are ADDED to the `song-projects` capability.

## ADDED Requirements

### Requirement: RQ-DIT-01 — Replace All Fragments

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

### Requirement: RQ-DIT-02 — Editable Status Gate

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

### Requirement: RQ-DIT-03 — Edit Route in Create Component

The frontend `CreateProjectComponent` MUST detect a route param `:id` on `/canciones/edit/:id` and MUST enter edit mode.

#### Scenario: edit/:id renders component in edit mode

- GIVEN the route `/canciones/edit/{id}` is activated
- WHEN `CreateProjectComponent` initializes
- THEN the component MUST run in edit mode with the project `id` captured from the route

### Requirement: RQ-DIT-04 — Edit Mode Prefill

In edit mode, the component MUST fetch the project via `getProject(id)` and populate `model` (settings) plus `fragments[]`, preserving `reference_audio_url`. Existing fragments MUST NOT be cleared until a successful submit.

#### Scenario: Edit mode populates model and fragments

- GIVEN an existing project with fragments and a reference audio
- WHEN edit mode loads and `getProject(id)` resolves
- THEN the form MUST show the project's model fields, fragments, and preserve `reference_audio_url`
- AND existing fragments MUST remain until submit succeeds

### Requirement: RQ-DIT-05 — Rehacer Navigation

The "Rehacer" button in the preview component MUST navigate to `/canciones/edit/{project.id}` instead of the create route, so iterations edit the same project rather than duplicating it.

#### Scenario: Rehacer links to edit route

- GIVEN a project with `id` on the preview page
- WHEN "Rehacer" is triggered
- THEN the template binding MUST navigate to `/canciones/edit/{project.id}`
- AND MUST NOT navigate to `/canciones/create`

## Backward Compatibility

Unchanged and MUST keep existing tests green: `POST /projects`, `GET /projects/{id}`, `PATCH /projects/{id}` (append fragment, RQ-PRJ-02), preview/final generation, and requested-edit status behavior. The added `PUT` endpoint is additive; it does not alter create/append semantics.

## Exclusions

`POST /api/generate` (legacy), checkout/download/payment flow, and the existing project create flow are unchanged. Reference-audio upload is not added in edit mode (preserve-only display).

## Acceptance Scenarios (Tests)

1. Backend — Put /projects/{id}/fragments with `["nuevo","otro"]`: 200, then GET /projects/{id} returns exactly those 2 fragments (assert order and count).
2. Backend — Put with project `status: paid`: 409 Conflict, fragments unchanged.
3. Frontend — `edit/:id` route creates `CreateProjectComponent` in edit mode, fetches project, populates form.
4. Frontend — "Rehacer" button binding in preview targets `/canciones/edit/{project.id}`.