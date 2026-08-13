# Delta for Song Projects

## ADDED Requirements

### RQ-IDEA-01: Idea Field Persistence

The system MUST accept an optional free-text `idea` field on `POST /api/projects`, `PATCH /api/projects/{id}`, and MUST return it in `GET /api/projects/{id}`. The `idea` MUST be persisted as a nullable column in the `projects` table.

#### Scenario: Create with idea

- GIVEN a valid project create request with `idea: "canción para mi esposa"`
- WHEN POST /api/projects is called
- THEN response MUST be 201
- AND GET /api/projects/{id} MUST return the stored `idea`

#### Scenario: Idea optional

- GIVEN a project create request without `idea`
- WHEN POST /api/projects is called
- THEN response MUST be 201
- AND the stored `idea` MUST be null

#### Scenario: Patch updates idea

- GIVEN an existing project
- WHEN PATCH with `{"idea": "nueva idea"}` is called
- THEN response MUST be 200
- AND GET MUST return the updated `idea`

### RQ-REF-01: Reference Song Field Deployed

The deployed staging frontend MUST expose the `reference_song` (free-text name) and `reference_description` fields, MUST include them in the project payload, and MUST support MP3 reference audio upload. These MUST be verified working on staging, not just locally.

#### Scenario: Reference song visible on staging

- GIVEN the staging frontend at `/canciones`
- WHEN the create/edit form renders
- THEN the `reference_song` input and MP3 upload MUST be visible

#### Scenario: Reference song in payload

- GIVEN a user enters reference_song="Bachata Rosa" and a reference_description
- WHEN the project is created or updated
- THEN the request payload MUST include `reference_song` and `reference_description`

#### Scenario: MP3 upload works

- GIVEN a user uploads an MP3 reference
- WHEN the project is saved
- THEN the upload MUST succeed
- AND the stored `reference_audio_url` MUST be retrievable

## MODIFIED Requirements

### RQ-PRJ-01: Create Project

The system MUST expose `POST /api/projects` accepting `recipient`, `relationship`, `genre`, `mood`, `voice`, optional `reference_song`, and optional `idea`. Returns 201 with `project_id`.
(Previously: accepted recipient, relationship, genre, mood, voice, and optional reference_song.)

#### Scenario: Happy path creation

- GIVEN valid `recipient`, `genre`, and `reference_song`
- WHEN POST /api/projects is called
- THEN response MUST be 201 with a UUID `project_id`
- AND status MUST be `draft`

#### Scenario: Missing required recipient

- GIVEN a request without `recipient`
- WHEN POST /api/projects is called
- THEN response MUST be 422

### RQ-PRJ-05: Get Project

The system MUST expose `GET /api/projects/{id}` returning project settings (including `idea`), fragments (by sort_order), and previews (by newest first) with their job status.
(Previously: returned settings without `idea`.)

#### Scenario: Full project response

- GIVEN a project with 2 fragments and 1 preview job
- WHEN GET /api/projects/{id}
- THEN response MUST include `recipient`, `genre`, `mood`, `voice`, `reference_song`, and `idea`
- AND `fragments` array MUST have 2 items ordered by sort_order
- AND `previews` array MUST have 1 item with job_id and status

#### Scenario: Project not found

- GIVEN a non-existent project_id
- WHEN GET /api/projects/{id}
- THEN response MUST be 404
