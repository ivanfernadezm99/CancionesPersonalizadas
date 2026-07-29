# Delta for song-projects
## MODIFIED Requirements

### RQ-PRJ-04: Generate Final Song

The system MUST expose `POST /api/projects/{id}/final` that creates a song job. When `chaining_enabled: true` is set in project metadata, the job MUST use clip-chaining (multiple `lyria-3-clip-preview` + stitch). When chaining is disabled, the job MUST use `lyria-3-pro-preview` with duration extension (existing behavior). Returns 202 with `job_id`.

(Previously: final always used lyria-3-pro-preview with duration extension)

#### Scenario: Final song via clip-chaining

- GIVEN a project with `chaining_enabled: true` and accumulated story fragments
- WHEN POST /api/projects/{id}/final
- THEN response MUST be 202 with a `job_id`
- AND the job MUST use clip-chaining strategy
- AND metadata MUST include `chaining_enabled: true`
- AND metadata MUST include `num_clips: 6`

#### Scenario: Final song without chaining (existing behavior preserved)

- GIVEN a project without `chaining_enabled` (default false)
- WHEN POST /api/projects/{id}/final
- THEN response MUST be 202 with a `job_id`
- AND the job's model param MUST be `lyria-3-pro-preview`
- AND the job MUST have `duration_extended: true` metadata
- AND no clipping/stitching occurs

(Previous scenario for final without fragments remains unchanged)
