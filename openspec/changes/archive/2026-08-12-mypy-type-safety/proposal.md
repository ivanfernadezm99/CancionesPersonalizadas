# Proposal: mypy-type-safety

## Intent

The stack declares mypy strict, but `python3 -m mypy app/ --ignore-missing-imports` reports **15 errors** in 3 files (34 checked). All are type-checking false positives or annotation gaps — **zero runtime behavior change** — yet they break the type-check gate and reject *correct* calls today (e.g. `SongProjectUpdate(reference_description=...)` is a valid PATCH that fails). Goal: pass the type checker cleanly, without masking.

## Scope

### In Scope
- `Field(None, ...)` → `Field(default=None, ...)` — Group A (10 errors)
- Generic args on bare `dict`/`list` — Group B (3 errors)
- `-> Any` on `_get_audio_segment()` — Group C (1 error)
- `hasattr(result, "error")` → `isinstance(result, AudioAnalysisError)` — Group D (1 error)
- Convert latent same-root-cause fields (`bridge`, `error`, `metadata`, `story`, `idea`) for completeness

### Out of Scope
- Enabling the pydantic mypy plugin (incompatible with mypy 2.1.0 — breaks every run)
- Any runtime, API-contract, or schema change
- `# type: ignore` masking (fights `warn_unused_ignores`, leaves latent traps)
- Changes to `app/projects/__init__.py`, `app/audio_analysis.py`, `store.py`, tests

## Capabilities

### New Capabilities
None — pure type-annotation refactor.

### Modified Capabilities
None — no spec-level behavior changes. `song-projects`/`clip-chaining` specs keep identical requirements and scenarios.

## Approach

Fix annotations in place (exploration approach 1, empirically validated → 0 errors on repro):
- `app/models.py` — `Field(default=None, ...)` on optional fields (Group A + latent)
- `app/projects/router.py` — `dict[str, Any]`, add `from typing import Any`, `isinstance` narrowing
- `app/music/clipchain.py` — `-> Any` on `_get_audio_segment()`, `segments: list[Any]`

`Field(None, ...)` and `Field(default=None, ...)` are runtime-identical in pydantic v2; `isinstance`/`hasattr` are provably equivalent for these two dataclasses. Do NOT enable the pydantic plugin.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/models.py` | Modified | ~10 edits: `Field(default=None, ...)` on optional fields |
| `app/projects/router.py` | Modified | `dict[str, Any]`, `typing.Any` import, `isinstance` (lines 39, 83, 357-366) |
| `app/music/clipchain.py` | Modified | `-> Any`, `list[Any]` (lines 78, 312, 321) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Pydantic plugin temptation | Med | Explicitly out of scope; incompatible with mypy 2.1.0 |
| Stray `type: ignore` trips `warn_unused_ignores` | Low | Prefer real fixes; exact codes if any |
| Regression from `isinstance` swap | Low | Behavior-identical; covered by pytest |

## Rollback Plan

Revert the single commit (3-file annotation diff). No migrations or schema — runtime byte-identical, so rollback is a pure git revert.

## Dependencies

None. No config changes, no new packages, no environment coupling.

## Success Criteria

- [ ] `python3 -m mypy app/ --ignore-missing-imports` → **0 errors**
- [ ] Full pytest suite stays green
- [ ] `ruff check .` passes
- [ ] No runtime change — API responses byte-identical
