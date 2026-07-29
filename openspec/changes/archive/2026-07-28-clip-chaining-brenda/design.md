# Design: Clip Chaining for Brenda Full Song

## Technical Approach

New `app/music/clipchain.py` module orchestrates: split lyrics at section markers → launch 6 OpenClaw `lyria-3-clip-preview` invocations in parallel (Semaphore 3) → stitch downloaded MP3s with pydub crossfade → trim/pad to 150s. Same `voice_prompt` + `reference_description` injected into every clip plus a positional energy descriptor per section. Per-spec (RQ-CHAIN-01–05, RQ-PRJ-04, RQ-MUS-03/05).

## Architecture Decisions

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Stitch lib | ffmpeg (higher quality) vs pydub (simpler, existing dep) | pydub — 2.5s crossfade masks boundaries well enough for v1 |
| Energy arc | No arc vs section→descriptor map | Map — injects position-aware energy (e.g. Chorus="enérgico"), improves perceived structure |
| Per-clip prompt | Same for all vs base + energy suffix | Base prompt identical for coherence, energy descriptor appended per section |
| `chaining_enabled` store | Job metadata only vs project field + metadata | Both — project persists intent, job metadata drives runtime dispatch |
| Fallback strategy | Only extend_duration vs stitch + extend | Stitch what succeeded, extend_duration to 150s. Raise only when 0 succeed |

## Data Flow

```
split_lyrics(lyrics, 6) → [ClipSection × 6]
  │  (each gets energy descriptor via ENERGY_MAP)
generate_clips_parallel(sections, prompt, semaphore=3)
  ├─ invoke 1 → poll → download → clip_1.mp3
  ├─ invoke 2 → poll → download → clip_2.mp3
  └─ invoke 3 → ...  (max 3 in-flight)
  │
[Path|None, ...] → stitch_clips(paths, cf=2500, target=150.0)
  ├─ pydub.append(crossfade) pair by pair
  ├─ fade_out(3000) on final
  ├─ if <150s → extend_duration()
  └─ export 192k → {OUTPUT_DIR}/{job_id}/final.mp3
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/music/clipchain.py` | Create | Core module: `ClipSection`, `split_lyrics`, `generate_clips_parallel`, `stitch_clips`, `generate_stitched`, `ENERGY_MAP` |
| `app/music/__init__.py` | Modify | Export `generate_stitched` in `__all__` |
| `app/config.py` | Modify | Add `CLIP_DURATION=30`, `CLIP_CROSSFADE_MS=2500`, `MAX_CLIPS=6`, `MAX_PARALLEL=3`, `CLIP_RETRY_ATTEMPTS=2` |
| `app/models.py` | Modify | Add `chaining_enabled: bool = False` to `SongProjectCreate` and `SongProjectUpdate` |
| `app/projects/__init__.py` | Modify | `create_final_job()` reads project's `chaining_enabled`, sets metadata `chaining_enabled` + `num_clips`. `project_worker()` calls `generate_stitched()` when `chaining_enabled` is true |
| `app/projects/store.py` | Modify | Add `chaining_enabled` column to projects table schema + migration |

## Interfaces / Contracts

```python
class ClipSection(NamedTuple):
    section_name: str   # "Verse 1", "Chorus", etc.
    lyrics_text: str    # Full lyrics for this section
    order: int          # 0-based position

ENERGY_MAP = {
    "verse": "suave, estableciendo la historia",
    "chorus": "enérgico, poderoso, estallido emocional",
    "bridge": "clímax, intenso, momento culminante",
    "outro": "gentil, resolución, calmado descendiendo",
}

def split_lyrics(text: str, max_clips=6) -> list[ClipSection]
async def generate_clips_parallel(sections, prompt, model, max_concurrency=3,
    retry_attempts=2, job_id=None) -> list[Path | None]
def stitch_clips(paths, crossfade_ms=2500, target=150.0) -> Path
async def generate_stitched(lyrics, prompt, model, job_id=None) -> Path
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `split_lyrics` with various marker patterns | Parametrized: 6 sections, 4 sections, no markers, single section |
| Unit | `stitch_clips` with known-length fake MP3s | Generate mono 440Hz WAVs via pydub, verify output duration ± crossfade math |
| Unit | `ENERGY_MAP` lookup | Each section name → expected descriptor; unknown → "neutro" |
| Integration | `generate_clips_parallel` mock | Mock OpenClawClient, verify semaphore(3) concurrency and retry on failures |
| E2E | Full `generate_stitched` with real OpenClaw | Run against preview model, verify output exists ≥ 120s |

## Migration / Rollout

No data migration required. `chaining_enabled` defaults to `False` on existing projects (column added with `DEFAULT 0`). Final jobs without `chaining_enabled` continue using existing pro-preview path. The Brenda project will set `chaining_enabled: true` at creation time.

## Open Questions

- [ ] Should we expose `chaining_enabled` in the song project creation UI? Currently only useful via API.
- [ ] Trim-to-150s threshold: trim from end or center? Proposal says trim to 150s — center-trim risks cutting the outro, end-trim is simpler.
