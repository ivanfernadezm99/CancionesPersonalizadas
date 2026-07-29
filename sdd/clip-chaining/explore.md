## Exploration: Clip Chaining + Full Song Generation for Brenda

### Current State

The system generates a **single** audio file per job:

1. **`app/music/openclaw.py`** — `OpenClawClient.invoke()` sends one lyrics block + one prompt → receives one task ID → polls → downloads one MP3
2. **`app/music/__init__.py`** — `generate()` calls invoke → poll → download → writes `generated.mp3`
3. **`app/music/durext.py`** — `extend_duration()` takes ONE MP3 and loops/crossfades the **same** audio segment to reach target duration via `smart_crossfade_loop()` (repeats the same clip)
4. **`app/projects/__init__.py`** — `project_worker()` runs: lyrics → `music_generate(lyrics, voice_prompt, model)` → `extend_duration()` → complete

**The problem**: `google/lyria-3-pro-preview` returns 503 (high demand). `google/lyria-3-clip-preview` (~30s clips) works reliably. Currently `extend_duration()` solves the "too short" problem by **repeating the same clip**, which sounds repetitive for a full song.

**OpenClaw gateway shows**:
| Provider | Duration support | Configured |
|----------|-----------------|------------|
| Google `lyria-3-clip-preview` | No (fixed ~30s clips) | ✅ Yes |
| Google `lyria-3-pro-preview` | ~150s but 503 | ✅ Yes |
| MiniMax `music-2.6` | ✅ `duration` parameter | ❌ No (`MINIMAX_API_KEY` not set) |
| MiniMax `music-2.6-free` | ✅ `duration` parameter | ❌ No |

### Affected Areas

- `app/music/__init__.py` — Main public API; needs new `generate_stitched()` or `generate_clips()` function
- `app/music/openclaw.py` — Currently single-invoke; needs ability to dispatch N parallel clip tasks
- `app/music/durext.py` — Has `smart_crossfade_loop()` for SAME-clip looping; needs `concatenate_clips()` for DIFFERENT clips
- **NEW: `app/music/clipchain.py`** — Orchestrates split → parallel generation → download → stitch → export
- `app/projects/__init__.py` — `project_worker()` needs to detect when to use clip chaining vs single model call
- `app/config.py` — May need `CLIP_DURATION_SECONDS`, `CLIP_CROSSFADE_SECONDS`, `MAX_CLIPS` settings
- `app/models.py` — May need `clip_count` or `chaining_enabled` field in project/gen request

### Approaches

1. **Lyrics-split parallel clip generation + pydub concatenation** — Split lyrics into N self-contained sections at marker boundaries (Verse/Chorus/Bridge), generate each as a parallel `clip-preview` (same prompt + reference), download all MP3s, stitch with pydub crossfade, export as final.mp3
   - Pros: Uses the WORKING model, parallel generation minimizes total time, pydub already a dependency, crossfade logic already exists in durext.py, preserves reference audio style across clips
   - Cons: Style may drift between clips (different generated takes), crossfade quality depends on musical compatibility of adjacent clips, total wall time still 5-6× generation time even with parallelism, need to handle clip failure mid-chain
   - Effort: Medium

2. **MiniMax single-shot generation** (if API key available) — MiniMax `music-2.6` supports `duration` parameter and is available via the same OpenClaw gateway. Set MINIMAX_API_KEY in .env, change model to `minimax/music-2.6` with `duration: 150`
   - Pros: Single generation = no stitching needed, supported through existing architecture, duration control
   - Cons: **API key NOT available** — `MINIMAX_API_KEY` not in .env or openclaw.json env block, MiniMax quality unknown vs Lyria 3, may handle Spanish lyrics differently, adds external dependency
   - Effort: Low (if API key configured) / High (if need to get API key first)

3. **Sequential clip generation with overlapping lyrics** — Generate clips sequentially, each overlapping in lyrics (last 2-3 lines of previous clip at start of next), then crossfade the overlapping sections
   - Pros: Natural transition because music content overlaps, better handling of melodic continuity
   - Cons: Much slower (can't parallelize), complex lyrics splitting, harder to manage clip boundaries
   - Effort: High

4. **Hybrid: Parallel clips + ffmpeg acrossfade** — Same as #1 but use ffmpeg concat with `acrossfade` filter for professional-grade crossfades instead of pydub
   - Pros: ffmpeg is already installed on the system, `acrossfade` filter handles waveform overlap better than pydub's simple gain crossfade, higher audio quality
   - Cons: Adds subprocess dependency, more complex error handling, pydub already works for basic crossfade
   - Effort: Medium

### Recommendation

**Approach #1 (lyrics-split parallel clip generation + pydub concatenation)** is the recommended path. Here's why:

- **It works today** — no API keys to acquire, no new dependencies beyond pydub (already installed)
- **Parallelism minimizes wall time** — 5-6 clips generated concurrently ≈ 30-60s total instead of 2.5-5min sequentially
- **Existing crossfade code** in durext.py provides the foundation; we extend it for heterogeneous clips
- **Style consistency** from using the same voice_prompt + reference_description for each clip

**Step-by-step architecture**:

```
lyrics (full text, 550 chars)
  │
  ├─▶ ClipSplitter.split(lyrics, n=6)
  │     [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Outro]
  │
  ├─▶ Parallel: invoke(clip_1, prompt, model=clip-preview)
  │             invoke(clip_2, prompt, model=clip-preview)
  │             invoke(clip_3, prompt, model=clip-preview)
  │             invoke(clip_4, prompt, model=clip-preview)
  │             invoke(clip_5, prompt, model=clip-preview)
  │             invoke(clip_6, prompt, model=clip-preview)
  │
  ├─▶ Parallel: download(clip_1_mp3)  │  Wait for ALL to complete
  │             download(clip_2_mp3)
  │             download(clip_3_mp3)
  │             download(clip_4_mp3)
  │             download(clip_5_mp3)
  │             download(clip_6_mp3)
  │
  ├─▶ pydub: stitch with crossfade (2-3s between clips)
  │     final = clip1 + crossfade(clip2, 2500ms) + crossfade(clip3, 2500ms) + ...
  │
  └─▶ Export: final.mp3 (trimmed to 150s, fade-out last 2s)
```

**Lyrics split plan for Brenda (~550 chars)**:

| Clip | Sections | Approx chars | Role |
|------|----------|-------------|------|
| 1 | [Intro] + [Verse 1] | ~100 | Establishes melody, soft start |
| 2 | [Chorus] (full) | ~80 | First hook, higher energy |
| 3 | [Verse 2] | ~100 | Continues story, builds |
| 4 | [Chorus] (reprise) | ~80 | Hook return, more intensity |
| 5 | [Bridge] | ~80 | Climax/emotional peak |
| 6 | [Outro] + fade | ~60 | Resolution, wind down |

**Duration math**: 6 clips × ~30s = 180s raw - (5 × 2.5s crossfade overlap) = 167.5s → trim to 150s with fade-out.

**New file structure**:

```
app/music/
├── __init__.py          # Add generate_stitched(), export clipchain functions
├── openclaw.py          # Unchanged (reused for individual clips)
├── durext.py            # Add concatenate_clips(clip_paths, crossfade_ms) function
├── clipchain.py         # NEW: split lyrics, orchestrate parallel clips, stitch
```

**ClipSplitter implementation notes**:
- Parse `[Verse N]`, `[Chorus]`, `[Bridge]`, `[Outro]` markers from formatted lyrics
- Group adjacent sections into balanced 30s clips (aim for ~80-120 chars per clip)
- Ensure each clip starts at a section boundary (not mid-verse)
- Allow chorus to span 2 clips if needed (Chorus 1 + Chorus 2)

### Risks

1. **Style inconsistency across clips** — The SAME prompt can yield different musical interpretations from Lyria 3. **Mitigation**: Generate all clips with identical voice_prompt + reference_description + model params. Add a `seed` parameter if Lyria 3 supports it (TBD). Longer crossfade (3s) can mask minor key/tempo differences.

2. **Parallel generation rate limits** — OpenClaw/Google may throttle concurrent requests. **Mitigation**: Use `asyncio.Semaphore(3)` to limit concurrency to 3 at a time, falling back to sequential if 429s occur.

3. **Clip boundary misalignment** — Lyria 3 generates music that naturally ends; a clipped ending might cut mid-phrase. **Mitigation**: The crossfade approach naturally masks this since trailing 2.5s overlaps with the next clip's intro. Use longer crossfade (3s) for bridge transitions where musical difference is greatest.

4. **One clip fails** — If 1 out of 6 generations fails, the whole chain breaks. **Mitigation**: Retry failed clips individually (up to 2 retries). If a clip fails permanently, offer a fallback that uses the remaining clips with longer crossfade to compensate.

5. **Doubled vocal overlap at transition** — Crossfade between two clips with vocals can sound like two singers if the phrasing overlaps. **Mitigation**: Since each clip has different lyrics sections, the overlap area has different words, reducing the "echo" effect. For chorus-to-chorus transitions, use a shorter crossfade (1.5s) to minimize vocal clash.

6. **Audio quality degradation** — Multiple MP3 decode/encode cycles through pydub may reduce quality. **Mitigation**: Export at same bitrate (192k), avoid unnecessary round-trips. The crossfade happens in-memory with pydub before single export.

### Ready for Proposal

**Yes**. The architecture is clear, the approach is feasible with existing dependencies, and the risk mitigations are well understood. The orchestrator should proceed to **Proposal phase** with these decisions set:

- **Recommended approach**: Approach #1 (parallel clip generation + pydub concatenation)
- **Number of clips**: 5-6 for a 2:30 song
- **Crossfade duration**: 2.5s standard, 3s for bridge transitions
- **Concurrency limit**: 3 parallel generations max (configurable)
- **New module**: `app/music/clipchain.py` with lyrics split, parallel generation, and stitch orchestration
- **Fallback**: If clip chain fails, fall back to existing `extend_duration()` behavior (single clip + loop)
- **MiniMax**: Worth exploring as a potential future optimization IF a MINIMAX_API_KEY becomes available, since it supports native duration control
