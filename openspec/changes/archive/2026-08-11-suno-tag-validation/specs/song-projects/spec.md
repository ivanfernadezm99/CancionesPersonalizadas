# Delta for Song Projects

## MODIFIED Requirements

### RQ-PRJ-01: Create Project

The system MUST expose `POST /api/projects` accepting `recipient`, `relationship`, `genre`, `mood`, `voice`, optional `reference_song`, and optional `idea`. Returns 201 with `project_id`.

The system MUST sanitize `reference_song` through the shared tag sanitizer before storing: safe `"Song - Artist"` / `"Song de Artist"` / `"Song (Artist)"` patterns MUST be stripped to the song token; when only an artist remains, the response MUST be 422 with a friendly Spanish message. An empty or absent `reference_song` MUST remain valid.
(Previously: `reference_song` was free text with no content validation and was stored verbatim.)

#### Scenario: Happy path creation

- GIVEN valid `recipient`, `genre`, and `reference_song`
- WHEN POST /api/projects is called
- THEN response MUST be 201 with a UUID `project_id`
- AND status MUST be `draft`

#### Scenario: Missing required recipient

- GIVEN a request without `recipient`
- WHEN POST /api/projects is called
- THEN response MUST be 422

#### Scenario: Artist name stripped on create

- GIVEN `reference_song="Bachata Rosa - Juan Luis Guerra"`
- WHEN POST /api/projects is called
- THEN response MUST be 201
- AND the stored `reference_song` MUST be `"Bachata Rosa"`

#### Scenario: Artist-only reference rejected

- GIVEN `reference_song="Los Palmeras"`
- WHEN POST /api/projects is called
- THEN response MUST be 422
- AND the error MUST be a friendly Spanish message indicating the artist name must be removed

#### Scenario: Empty reference_song still accepted

- GIVEN a request with `reference_song=""`
- WHEN POST /api/projects is called
- THEN response MUST be 201
- AND the stored `reference_song` MUST be empty

### RQ-PRJ-02: Add Story Fragment

The system MUST expose `PATCH /api/projects/{id}` accepting optional `genre`, `mood`, `voice`, `reference_song` changes and an optional `fragment` object with `text` (max 2000 chars). Returns 200.

A `reference_song` change MUST be sanitized with the same shared tag sanitizer as RQ-PRJ-01: strip safe patterns to the song token; reject artist-only values with 422 without persisting the change.
(Previously: `reference_song` changes were stored verbatim with no content validation.)

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

#### Scenario: Artist name stripped on patch

- GIVEN an existing project
- WHEN PATCH with `{"reference_song": "Bailando de Enrique Iglesias"}`
- THEN response MUST be 200
- AND the stored `reference_song` MUST be `"Bailando"`

#### Scenario: Artist-only reference rejected on patch

- GIVEN an existing project with stored `reference_song="Bachata Rosa"`
- WHEN PATCH with `{"reference_song": "La Mona Jiménez"}`
- THEN response MUST be 422
- AND the stored `reference_song` MUST remain `"Bachata Rosa"`

### RQ-REF-01: Reference Song Field Deployed

The deployed staging frontend MUST expose the `reference_song` (free-text name) and `reference_description` fields, MUST include them in the project payload, and MUST support MP3 reference audio upload. These MUST be verified working on staging, not just locally.

The frontend MUST NOT teach the rejected `"Song - Artist"` format: the `reference_song` hint text MUST show song-only examples. The frontend MUST mirror the strip heuristic client-side and MUST surface the friendly Spanish error from failed jobs (preview/download) instead of raw English provider messages.
(Previously: hint text showed `Ej: "Bailando" de Enrique Iglesias` and raw English Suno errors were rendered.)

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

#### Scenario: Hint text shows song-only examples

- GIVEN the create form renders
- WHEN the `reference_song` hint is displayed
- THEN the hint MUST NOT contain artist-format examples (e.g. `"Bailando" de Enrique Iglesias`)
- AND the hint MUST show song-only examples (e.g. `"Despacito"`, `"La Bamba"`)

#### Scenario: Friendly error surfaced on failure

- GIVEN a job fails with the translated Spanish artist message
- WHEN the preview/download page renders the failure state
- THEN the friendly Spanish message MUST be displayed
- AND no raw English Suno error text MUST reach the UI
