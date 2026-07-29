# Tasks: Clip Chaining for Brenda Full Song

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

| Field | Value |
|-------|-------|
| Estimated changed lines | ~380–430 (additions) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |

## Phase 1: Foundation

- [x] 1.1 **Config** — Add `CLIP_DURATION=30`, `CLIP_CROSSFADE_MS=2500`, `MAX_CLIPS=6`, `MAX_PARALLEL=3`, `CLIP_RETRY_ATTEMPTS=2` to `app/config.py`
- [x] 1.2 **Model + Store** — Add `chaining_enabled: bool = False` to `SongProjectCreate`/`SongProjectUpdate` in `app/models.py`; add column + migration in `app/projects/store.py`
- [x] 1.3 **ClipSection + ENERGY_MAP** — New `app/music/clipchain.py` with `ClipSection` NamedTuple and `ENERGY_MAP` (verse→suave, chorus→enérgico, bridge→clímax, outro→gentil). Unknown section → "neutro"

## Phase 2: Core ClipChain

- [x] 2.1 **split_lyrics()** — Parse lyrics at `[Verse N]`, `[Chorus]`, `[Bridge]`, `[Outro]` markers into `list[ClipSection]`. Max N clips, no mid-line splits. Bound unknown markers to `[Desconocido]`
- [x] 2.2 **generate_clips_parallel()** — Async function: Semaphore(MAX_PARALLEL=3), for each section invoke OpenClaw `lyria-3-clip-preview` with same `voice_prompt` + `reference_description` + section-specific energy descriptor. Retry failed invokes 2× with 10s backoff. Individual polling per clip. Return `list[Path | None]`
- [x] 2.3 **stitch_clips()** — pydub `.append(crossfade=2500ms)` for available clips, 3s fade-out on final, trim at 150s target if exceeding 180s. If 1+ clips succeed but <120s total → fallback to `extend_duration()`. Raise `all_providers_unavailable` if 0 clips succeed
- [x] 2.4 **generate_stitched()** — Orchestrator: `split_lyrics()` → `generate_clips_parallel()` → `stitch_clips()` → export 192k MP3 to `{OUTPUT_DIR}/{job_id}/final.mp3`
- [x] 2.5 **Export** — Add `generate_stitched` to `app/music/__init__.py` `__all__`

## Phase 3: Project Integration

- [x] 3.1 **create_final_job() wiring** — In `app/projects/__init__.py`: read project's `chaining_enabled`, set `chaining_enabled: true` + `num_clips: 6` in job metadata
- [x] 3.2 **project_worker() dispatch** — When job metadata has `chaining_enabled: true`, call `generate_stitched()` instead of `music_generate()` + `extend_duration()`. Include `stitching_used: true` in completion metadata

## Phase 4: Tests

- [x] 4.1 **Unit: split_lyrics + ENERGY_MAP** — Parametrized: 6 sections, 4 sections, no markers, single section, unknown marker; each section→expected descriptor, unknown → "neutro"
- [x] 4.2 **Unit: stitch_clips** — Generate MP3s via pydub, verify output duration ± crossfade math; test trim, fallback to extend_duration, all-fail raises error
- [x] 4.3 **Integration: generate_clips_parallel** — Mock OpenClawClient, verify Semaphore(3) concurrency, retry on failure, partial success returns `[Path, None, Path, ...]`
- [x] 4.4 **Integration: project_worker chaining path** — Insert job record with `chaining_enabled` metadata, mock `generate_stitched`, verify dispatch and completion metadata
