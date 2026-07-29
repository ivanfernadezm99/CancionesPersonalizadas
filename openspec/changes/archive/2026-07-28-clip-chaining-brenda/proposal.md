# Proposal: Clip Chaining for Brenda Full Song

## Intent

Google Lyria 3 `lyria-3-pro-preview` (full 150s song) is unstable — returns 503 under load. But `lyria-3-clip-preview` (30s snippets) works reliably. Generate 5-6 clips in parallel from split lyrics and stitch with crossfade to produce a full 2:30 song without relying on the unreliable pro model.

## Scope

### In Scope
- Split lyrics into 6 sections at marker boundaries (Verse/Chorus/Bridge/Outro)
- Parallel generation of up to 3 clips concurrently via OpenClaw
- Download all MP3s and stitch with pydub crossfade (2.5s between clips, 3s final fade-out)
- Fallback: if a clip fails after retries, continue with remaining clips + smart-loop to reach 150s
- New `app/music/clipchain.py` module: `split_lyrics()`, `generate_clips_parallel()`, `stitch_clips()`, `generate_stitched()`
- Extend `app/music/durext.py` with `concatenate_clips()` for heterogeneous stitching
- New settings: CLIP_DURATION=30, CLIP_CROSSFADE_MS=2500, MAX_CLIPS=6, MAX_PARALLEL=3
- Update `project_worker()` to use clip chaining for final jobs

### Out of Scope
- MiniMax integration (requires API key — future)
- ffmpeg acrossfade (pydub crossfade sufficient for v1)
- Sequential overlapping generation (slower, more complex)
- Chorus lyrics generation — both chorus sections use identical lyrics provided upfront

## Capabilities

### New Capabilities
- `clip-chaining`: Lyrics splitting at section markers, parallel clip generation via OpenClaw, MP3 stitching with crossfade, per-clip failure recovery

### Modified Capabilities
- `music-generation`: RQ-MUS-05 updated — final jobs use clip-chaining instead of pro-preview; RQ-MUS-03 adds stitching as extension technique #2
- `song-projects`: RQ-PRJ-04 updated — final song generation uses clip-chaining approach with `chaining_enabled` metadata

## Approach

Split full lyrics at `[Verse N]`/`[Chorus]`/`[Bridge]`/`[Outro]` markers into 6 self-contained segments. Launch clips via OpenClaw `lyria-3-clip-preview` using `asyncio.Semaphore(3)` for concurrency. Poll independently at 5s interval. Download MP3s as each completes. Stitch sequentially with pydub `append(crossfade=2500)`. Apply 3s final fade-out. Trim/pad to 150s total.

| Clip | Section | Chars | Role |
|------|---------|-------|------|
| 1 | Verse 1 | ~100 | Establishes melody, soft start |
| 2 | Chorus | ~80 | First hook, higher energy |
| 3 | Verse 2 | ~100 | Continues story, builds |
| 4 | Chorus (reprise) | ~80 | Hook return, more intensity |
| 5 | Bridge | ~80 | Climax/emotional peak |
| 6 | Outro + fade | ~60 | Resolution, wind down |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/music/clipchain.py` | New | Split, parallel gen, stitch orchestration |
| `app/music/durext.py` | Modified | Add `concatenate_clips()` |
| `app/music/__init__.py` | Modified | Export `generate_stitched()` |
| `app/projects/__init__.py` | Modified | Update `project_worker()` for clip-chaining |
| `app/config.py` | Modified | Add CLIP_DURATION, CLIP_CROSSFADE_MS, MAX_CLIPS, MAX_PARALLEL |
| `openspec/specs/music-generation/spec.md` | Modified | New RQs for parallel clip invocation |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Style drift between clips | Med | Same prompt+seed; 2.5s crossfade masks differences |
| OpenClaw throttles concurrent requests | Med | Semaphore(3) limits concurrency |
| One clip fails permanently | Low | 2 retries; fallback to remaining clips + smart-loop |
| Vocal overlap at crossfade | Low | Different lyrics per clip reduces echo effect |

## Rollback Plan

Set `chaining_enabled: false` in job metadata to revert to single-model generation (pro-preview or clip + `extend_duration()`). Existing `generate()` function unchanged.

## Dependencies

- pydub (already installed)
- ffmpeg (already installed, required by pydub)
- OpenClaw gateway with `lyria-3-clip-preview` access

## Success Criteria

- [ ] 6 clips generated in parallel (max 3 concurrent) without errors
- [ ] Stitched output is 150s ± 5s with smooth crossfades
- [ ] No audible glitch at any clip boundary
- [ ] Fallback produces valid output when a clip fails
- [ ] All existing preview jobs continue working unchanged
