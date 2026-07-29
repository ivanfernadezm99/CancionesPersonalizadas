# Delta Spec: clip-chaining-brenda

## New Capability: clip-chaining

### Purpose
Split Brenda's lyrics at `[Verse N]`/`[Chorus]`/`[Bridge]`/`[Outro]` markers, generate clips in parallel via `lyria-3-clip-preview`, stitch with crossfade to produce a full ~150s song — bypassing unreliable pro-preview model.

### Requirements

**RQ-CHAIN-01: Lyrics Splitting** — MUST split lyrics at section markers into N clips (N ≤ 6). Each clip MUST contain complete sections, not split mid-line.
- GIVEN Brenda lyrics with Verse 1, Chorus, Verse 2, Chorus, Bridge, Outro
- WHEN `split_lyrics(n=6)` is called
- THEN each clip MUST contain one section, boundaries NOT split mid-line

**RQ-CHAIN-02: Parallel Generation** — MUST generate clips via `lyria-3-clip-preview` with Semaphore(3). All clips MUST use identical `voice_prompt` + `reference_description`.
- GIVEN 6 clips and working gateway, WHEN generated concurrently (max 3)
- THEN all 6 MUST complete and download as MP3
- AND every invoke MUST use the identical prompt
- AND at most 3 MUST be in-flight simultaneously

**RQ-CHAIN-03: Failure Recovery** — MUST retry failed clips 2× with 10s backoff. If ≥1 succeed, stitch them + fallback `extend_duration()` if <150s. If 0 succeed, raise `all_providers_unavailable`.
- GIVEN 6 clips, clip #4 fails after retries; WHEN 5 succeed
- THEN stitch 5 clips AND call extend_duration() if <150s
- GIVEN all 6 fail; WHEN 0 clips → MUST raise `all_providers_unavailable`

**RQ-CHAIN-04: Stitching** — MUST stitch via pydub `append(crossfade=2500ms)`, 3s fade-out on final clip, export 192k MP3.
- GIVEN 6 clips ~30s each; WHEN stitched → output ~167s ± 2s, 3s fade-out, 192k

**RQ-CHAIN-05: Config** — CLIP_DURATION=30s, CLIP_CROSSFADE_MS=2500, MAX_CLIPS=6, MAX_PARALLEL=3, CLIP_RETRY_ATTEMPTS=2

### Edge Cases
| Condition | Behavior |
|-----------|----------|
| OpenClaw 503 on clip invoke | Retry 2× with 10s backoff |
| Download URL expires | Retry 3× with exponential backoff |
| pydub unavailable for stitch | Raise error — stitch requires pydub |
| Stitched > 180s | Trim to 150s |
| All clips succeed but < 120s total | Fallback to `extend_duration()` |

## Modified Capability: music-generation

### MODIFIED Requirements

**RQ-MUS-03: Duration Extension** (Previously: only single-clip looping available)
Extension techniques reordered — #2 is **Stitch**: generate multiple clips and crossfade them.
- GIVEN a `chaining_enabled` final job with 6 segments
- WHEN clips are stitched → output MUST be ≥150s AND `stitching_used: true` in metadata

**RQ-MUS-05: Model Selection by Job Type** (Previously: final always used lyria-3-pro-preview)
Final jobs now use clip-chaining when `chaining_enabled: true`, falling back to pro-preview.
- GIVEN final job with `chaining_enabled: true` → use clip-chaining (not pro-preview)
- GIVEN final job without `chaining_enabled` → use lyria-3-pro-preview (existing)

## Modified Capability: song-projects

### MODIFIED Requirements

**RQ-PRJ-04: Generate Final Song** (Previously: final always used lyria-3-pro-preview)
When `chaining_enabled: true` in project, final MUST use clip-chaining instead of pro-preview.
- GIVEN project with `chaining_enabled: true`, fragments
- WHEN POST /api/projects/{id}/final → 202 with job_id, metadata includes `chaining_enabled: true, num_clips: 6`
- GIVEN project without `chaining_enabled` → existing pro-preview behavior preserved
