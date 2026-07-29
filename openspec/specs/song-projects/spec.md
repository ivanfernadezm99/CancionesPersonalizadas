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
