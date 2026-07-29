# Clip Chaining Specification

## Purpose

Generate full ~150s songs by splitting Brenda's lyrics at section markers, generating clips in parallel via Google Lyria 3 clip-preview, and stitching with crossfade — bypassing the unreliable pro-preview model.

## Requirements

### RQ-CHAIN-01: Lyrics Splitting

The system MUST split lyrics at `[Verse N]`/`[Chorus]`/`[Bridge]`/`[Outro]` markers into N self-contained clips (N ≤ MAX_CLIPS). Each clip MUST contain complete section content.

#### Scenario: Split Brenda lyrics into 6 clips

- GIVEN full Brenda lyrics with Verse 1, Chorus, Verse 2, Chorus, Bridge, Outro
- WHEN `split_lyrics(n=6)` is called
- THEN each clip MUST contain exactly one section
- AND section boundaries MUST NOT be split mid-line

#### Scenario: Fewer markers than requested clips

- GIVEN lyrics with only 3 distinct markers
- WHEN `split_lyrics(n=6)` is called
- THEN the system SHOULD distribute content across clips
- AND every clip MUST start at a section boundary

### RQ-CHAIN-02: Parallel Generation

The system MUST generate clips via `lyria-3-clip-preview` using `asyncio.Semaphore(MAX_PARALLEL=3)`. All clips MUST use the same `voice_prompt` and `reference_description` for style consistency.

#### Scenario: 6 clips all succeed — happy path

- GIVEN 6 lyric clips and a working OpenClaw gateway
- WHEN all clips are generated concurrently (max 3 at a time)
- THEN all 6 MUST reach "completed" status
- AND each MUST be downloaded as valid MP3 bytes
- AND total wall time SHOULD be ~2× single clip time

#### Scenario: Style consistency across all clips

- GIVEN 6 lyric clips and one shared `voice_prompt` + `reference_description`
- WHEN all 6 invoke calls are made
- THEN every payload MUST contain the identical `prompt` field
- AND every payload MUST contain the identical lyrics-relevant args

#### Scenario: Rate limit — concurrency cap enforced

- GIVEN a Semaphore(3) and 6 clips ready for generation
- WHEN generation starts
- THEN at most 3 invocations MUST be in-flight simultaneously
- AND remaining clips MUST queue until a slot becomes available

### RQ-CHAIN-03: Failure Recovery

The system MUST retry failed clips up to CLIP_RETRY_ATTEMPTS (default 2) times with 10s backoff between attempts.

#### Scenario: Partial failure — 1 clip fails, fallback activates

- GIVEN 6 clips where clip #4 fails after 2 retries
- WHEN 5 clips succeed
- THEN the system MUST stitch the 5 clips
- AND if total stitched duration < 150s, the system SHOULD call `extend_duration()` on the result
- AND the output MUST be a valid 192k MP3

#### Scenario: Total failure — all clips fail

- GIVEN all 6 clips fail after 2 retries each
- WHEN clip generation completes with 0 clips
- THEN the system MUST raise `all_providers_unavailable`
- AND the job MUST be marked "failed"

#### Scenario: Generation timeout on a single clip

- GIVEN a clip that polls for >300s without completing
- WHEN the polling loop times out
- THEN that clip MUST be treated as failed
- AND the retry logic MUST attempt it again (up to 2 retries)

### RQ-CHAIN-04: Clip Stitching

The system MUST stitch clips via pydub `AudioSegment.append(crossfade=CLIP_CROSSFADE_MS)`. The final clip MUST have a 3s fade-out. The output MUST be exported as 192k MP3.

#### Scenario: 6 clips stitched to full length

- GIVEN 6 downloaded MP3 clips of ~30s each
- WHEN stitched with 2.5s crossfade between each
- THEN output MUST be ~167s ± 2s (180s raw - 5 × 2.5s overlap)
- AND output MUST have 3s fade-out at end
- AND bitrate MUST be 192k

#### Scenario: Crossfade masks boundary artifacts

- GIVEN two adjacent clips with differing musical characteristics
- WHEN stitched with 2500ms crossfade
- THEN the output MUST NOT have audible glitches at boundaries
- AND the transition SHOULD sound natural

### RQ-CHAIN-05: Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| CLIP_DURATION | 30 | Target seconds per clip |
| CLIP_CROSSFADE_MS | 2500 | Crossfade between clips (ms) |
| MAX_CLIPS | 6 | Maximum clips to generate |
| MAX_PARALLEL | 3 | Max concurrent generations |
| CLIP_RETRY_ATTEMPTS | 2 | Max retries per failed clip |

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| OpenClaw returns 503 on clip invoke | Retry 2 times with 10s backoff |
| Clip download URL expires before download | Retry download 3× with exponential backoff |
| pydub/ffmpeg unavailable for stitch | Raise clear error — stitching requires pydub |
| Stitched audio > 180s | Trim to 150s at end |
| All clips succeed but total < 120s | Fallback to `extend_duration()` on stitched result |

## Dependencies

- **Internal**: `app/music/openclaw.py` — OpenClawClient for invoke/poll/download
- **Internal**: `app/music/durext.py` — `extend_duration()` for fallback
- **External**: pydub (already installed)
- **External**: ffmpeg (already installed)
- **External**: OpenClaw gateway with `lyria-3-clip-preview` access
