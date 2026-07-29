# Delta for song-projects

## MODIFIED Requirements

### RQ-PRJ-04: Generate Final Song

`POST /api/projects/{id}/final`. OpenClaw: clip-chain when `chaining_enabled`, else pro-preview. Suno: single generate call — chaining irrelevant.
(Previously: always OpenClaw, no provider branching)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw chained | `chaining_enabled`, OpenClaw | POST /final | 202 + job_id, clip-chaining |
| OpenClaw no chain | no chaining, OpenClaw | POST /final | 202 + job_id, pro-preview, no stitch |
| Suno single call | `music_provider=suno` | POST /final | 202 + job_id, SunoProvider, NO chaining |
| No fragments | project without fragments | POST /final | 422 |
