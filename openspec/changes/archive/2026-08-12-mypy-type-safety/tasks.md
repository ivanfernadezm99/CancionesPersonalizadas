# Tasks: mypy-type-safety

## Review Workload Forecast

Estimated changed lines: ~15-20 (annotation-only, 3 files)

| Field | Value |
|-------|-------|
| Estimated changed lines | ~15-20 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Fix all 15 mypy errors across 3 files (Groups A-D, annotation-only) | PR 1 (single) | `python3 -m mypy app/ --ignore-missing-imports` → 0 errors | `pytest` — full suite green proves zero behavior change | `git revert` of the 3-file diff; no schema or migration |

## Phase 1: Group A — Pydantic field defaults (`app/models.py`)

- [x] 1.1 `GenerateRequest`: `Field(None, ...)` → `Field(default=None, ...)` for `story` (60), `reference_song` (64), `reference_description` (69), `idea` (74)
- [x] 1.2 `SongProjectUpdate`: same conversion for `genre` (208), `mood` (209), `voice` (210), `reference_song` (211), `reference_description` (212), `idea` (213), `chaining_enabled` (216)
- [x] 1.3 Latent same-root-cause fields: `LyricsResult.bridge` (107), `JobStatusResponse.error` (139), `PaymentConfirmRequest.metadata` (298)

## Phase 2: Groups B+C — Generic args + return annotation

- [x] 2.1 `app/music/clipchain.py`: extend import to `from typing import Any, NamedTuple` (15); `-> Any` on `_get_audio_segment()` (78); `segments: list[Any] = []` (321)
- [x] 2.2 `app/projects/router.py`: add `from typing import Any`; `project: dict[str, Any]` (39); `-> dict[str, Any]` (83)

## Phase 3: Group D — Union narrowing

- [x] 3.1 `app/projects/router.py`: import `AudioAnalysisError` alongside `analyze_audio` from `app.audio_analysis` (16)
- [x] 3.2 Replace `if hasattr(result, "error"):` with `if isinstance(result, AudioAnalysisError):` (357) — narrows the union, clears `union-attr` at 360

## Phase 4: Regression guard + verification

- [x] 4.1 Gate: `python3 -m mypy app/ --ignore-missing-imports` → 0 errors (was 15 across 34 files)
- [x] 4.2 `pytest` — full suite green (behavior untouched; `app/projects/__init__.py` call sites 85/153 now typecheck)
- [x] 4.3 `ruff check .` passes; confirm zero `# type: ignore` added (`warn_unused_ignores`)
- [x] 4.4 Record the mypy gate as the verify entry command (no existing mypy test in repo)
