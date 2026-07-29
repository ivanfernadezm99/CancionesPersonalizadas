# Delta for music-generation
## MODIFIED Requirements

### RQ-MUS-03: Duration Extension

The system SHOULD extend generated audio to achieve 2-3 minutes total duration, since Lyria 3 typically produces 30-90 seconds. For pro-preview model outputs (`lyria-3-pro-preview`), the system MUST attempt duration extension (target 120-180s). For clip-preview outputs (`lyria-3-clip-preview`), extension is optional unless used in clip-chaining mode.

Extension techniques (in priority order):
1. **Smart loop**: Crossfade-loop the segment for natural-sounding extension
2. **Stitch**: Generate multiple short clips and crossfade them (NEW — for clip-chaining)
3. **Simple loop**: Append a looped version with fade-out
4. **Fallback**: Return shorter audio with a duration metadata header

(Previously: stitching was not listed as an extension technique)

#### Scenario: Stitch technique produces full song

- GIVEN a `chaining_enabled` final job with 6 lyric segments
- WHEN the system generates 6 clips and stitches them
- THEN the output MUST be ≥ 150s
- AND `stitching_used: true` MUST be set in job metadata

#### Scenario: Clip-preview with chaining produces output

- GIVEN a clip-chaining job with 6 clips using `lyria-3-clip-preview`
- WHEN the clips are generated and stitched
- THEN the output MUST be valid MP3 at 192k
- AND the output SHOULD be longer than a single clip-preview output

(Previous scenarios for smart loop, simple loop, and fallback remain unchanged)

### RQ-MUS-05: Model Selection by Job Type

The system MUST select the OpenClaw model based on job type: `lyria-3-clip-preview` for preview jobs (30s clips). For final jobs, the system MUST use **clip-chaining** (multiple clip-preview calls + stitch) when `chaining_enabled` is true, falling back to `lyria-3-pro-preview` when chaining is disabled. Existing `POST /api/generate` jobs MUST continue using `lyria-3-clip-preview` (backward compatible).

(Previously: final always used lyria-3-pro-preview)

#### Scenario: Final uses clip-chaining when enabled

- GIVEN a final job with `chaining_enabled: true` in metadata
- WHEN music generation starts
- THEN the system MUST use the clip-chaining approach (multiple `lyria-3-clip-preview` calls)
- AND the system MUST NOT call `lyria-3-pro-preview`

#### Scenario: Final falls back to pro-preview when chaining disabled

- GIVEN a final job without `chaining_enabled` (default false)
- WHEN music generation starts
- THEN the system MUST use `lyria-3-pro-preview` (existing behavior)
- AND the system MUST NOT use clip-chaining

(Previous scenarios for preview uses clip model and existing generate remain unchanged)
