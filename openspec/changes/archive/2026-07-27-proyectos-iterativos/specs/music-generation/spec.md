# Delta for Music Generation

## ADDED Requirements

### RQ-MUS-05: Model Selection by Job Type

The system MUST select the OpenClaw model based on job type: `lyria-3-clip-preview` for preview jobs (30s clips) and `lyria-3-pro-preview` for final jobs (2+ min songs). Existing `POST /api/generate` jobs MUST continue using `lyria-3-clip-preview` (backward compatible).

#### Scenario: Preview uses clip model

- GIVEN a preview job triggered from POST /api/projects/{id}/preview
- WHEN the music_generate tool is invoked
- THEN the `model` arg MUST be `google/lyria-3-clip-preview`

#### Scenario: Final uses pro model

- GIVEN a final job triggered from POST /api/projects/{id}/final
- WHEN the music_generate tool is invoked
- THEN the `model` arg MUST be `google/lyria-3-pro-preview`

#### Scenario: Existing generate still uses clip

- GIVEN a job from POST /api/generate (not project-backed)
- WHEN music_generate is invoked
- THEN the `model` arg MUST be `google/lyria-3-clip-preview`

### RQ-MUS-06: Reference Song in Prompt

When a project has `reference_song` set, the system MUST include it in the prompt sent to OpenClaw, e.g. "al estilo de {reference_song}".

#### Scenario: Reference song appended to prompt

- GIVEN a project with reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN the music_generate prompt is constructed
- THEN the prompt MUST include "al estilo de Bachata Rosa - Juan Luis Guerra"

#### Scenario: No reference song

- GIVEN a project or request without reference_song
- WHEN the prompt is constructed
- THEN the prompt MUST NOT include any style reference

## MODIFIED Requirements

### RQ-MUS-03: Duration Extension

The system SHOULD extend generated audio to achieve 2-3 minutes total duration. For pro-preview model outputs, the system MUST attempt duration extension (target 120-180s). For clip-preview outputs, extension is optional (target 30-45s is sufficient).
(Previously: extension attempted for all outputs with target 120-180s)

#### Scenario: Pro-preview model, extension succeeds

- GIVEN a 60s MP3 from `lyria-3-pro-preview`
- WHEN duration extension runs with target 150s
- THEN output MUST be between 120-180s
- AND `duration_extended: true` MUST be set in metadata

#### Scenario: Clip-preview model, no extension

- GIVEN a 30s MP3 from `lyria-3-clip-preview`
- WHEN the job completes
- THEN output MAY be at original length (extension not required)
- AND `duration_extended` SHOULD remain false
