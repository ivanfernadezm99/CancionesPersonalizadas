# Archive Report: mypy-type-safety

**Change**: mypy-type-safety
**Archived**: 2026-08-12
**Archived to**: `openspec/changes/archive/2026-08-12-mypy-type-safety/`
**Artifact store**: hybrid (OpenSpec filesystem + Engram)
**Type**: Pure type-annotation refactor — no spec delta, no capability change, no runtime behavior change

## Summary

The mypy strict gate (`python3 -m mypy app/ --ignore-missing-imports`) reported **15 errors** across 3 files (34 files checked). All were type-checking false positives or annotation gaps — zero runtime behavior change. The change fixed all 15 errors across **4 root-cause groups** without masking (`# type: ignore`) and without enabling the pydantic mypy plugin.

**Final state at close**: mypy **0 errors** (34 files), pytest **439 passed / 0 failed**, ruff **clean** — all re-confirmed live at archive time.

## Root Cause

**pydantic 2.13.1 + mypy 2.1.0 `Field(None)` positional default bug**: mypy 2.x `dataclass_transform` machinery only treats a pydantic `Field` as having a default when the `default`/`default_factory` keyword is present. The positional form `Field(None, ...)` is interpreted as a required positional argument, producing false `call-arg` errors on call sites that legitimately omit the field. Runtime behavior of both forms is identical in pydantic v2.

## What Was Fixed (15 errors, 4 root-cause groups)

| Group | Root cause | Fix | Errors | Location |
|-------|-----------|-----|--------|----------|
| A | `Field(None, ...)` positional default misinterpreted as required | `Field(None, ...)` → `Field(default=None, ...)` | 10 (14 conversions) | `app/models.py` |
| B | Bare generic `dict`/`list` annotations | `dict` → `dict[str, Any]`, `list` → `list[Any]` | 3 | `app/projects/router.py`, `app/music/clipchain.py` |
| C | Missing return annotation | `-> Any` on `_get_audio_segment()` | 1 | `app/music/clipchain.py` |
| D | Union narrowing via `hasattr` not recognized by mypy | `if hasattr(result, "error"):` → `if isinstance(result, AudioAnalysisError):` | 1 | `app/projects/router.py` |

### Group A detail (14 conversions)

- `GenerateRequest`: `story`, `reference_song`, `reference_description`, `idea` (4)
- `SongProjectUpdate`: `genre`, `mood`, `voice`, `reference_song`, `reference_description`, `idea`, `chaining_enabled` (7)
- Latent same-root-cause fields: `LyricsResult.bridge`, `JobStatusResponse.error`, `PaymentConfirmRequest.metadata` (3)

No field type changed (`str | None`, `bool | None`, `Bridge | None`, `dict[str, str] | None` intact); no default VALUE changed (all remain `None`).

## Files Changed

| File | Change |
|------|--------|
| `app/models.py` | 14 `Field(default=None, ...)` conversions |
| `app/projects/router.py` | `from typing import Any`; `project: dict[str, Any]` (39); `-> dict[str, Any]` (83); `AudioAnalysisError` import; `hasattr` → `isinstance` (357) |
| `app/music/clipchain.py` | `from typing import Any, NamedTuple`; `-> Any` on `_get_audio_segment()` (78); `segments: list[Any] = []` (321) |

Out of scope and untouched (per proposal): `app/projects/__init__.py`, `app/audio_analysis.py`, `store.py`, tests, `pyproject.toml` (pydantic plugin NOT enabled — incompatible with mypy 2.1.0).

## Verification State (final, at close)

| Check | Result | Evidence |
|-------|--------|----------|
| Verify verdict | ✅ PASS (6/6 checks) | `verify-report.md`, observed #3282 |
| mypy gate | ✅ 0 errors, 34 files | `Success: no issues found in 34 source files` — re-run at archive |
| pytest | ✅ 439 passed / 0 failed | re-run at archive (83.29s) |
| ruff | ✅ `All checks passed!` | re-run at archive |
| Spec compliance | ✅ 0 requirements / 0 scenarios | no delta spec — proposal declares zero spec-level behavior change |
| `# type: ignore` added | ✅ zero | `warn_unused_ignores=true` clean |

Note: verify-report recorded 3 pre-existing aiosqlite `PytestUnhandledThreadExceptionWarning` (worker thread on closed event loop, `tests/test_integration.py`); the archive re-run showed 2 warnings. Non-blocking, unrelated to this change, run-to-run variance in thread warnings.

## Task Completion Gate

All **11/11** implementation tasks checked `[x]` in `openspec/changes/mypy-type-safety/tasks.md` (Groups A–D + regression guard). No stale unchecked tasks at archive. No archive-time reconciliation was needed.

## Native Review Receipt Gate

`reviewGate` is **structurally absent** — no `reviews/` directory, no review transaction/ledger/receipt/gate-context ever existed for this candidate (kill switch off / no review discovered). Archive proceeded under ordinary repository policy. No review artifacts to read or block on.

## Spec Sync

**No spec merge performed** — this change has NO delta specs. `openspec/changes/mypy-type-safety/specs/` does not exist (confirmed before archiving). No capability behavior changed; `openspec/specs/*` untouched by this change. Per the orchestrator's explicit instruction, no spec files were created or merged.

## Archive Contents

- `exploration.md` ✅
- `proposal.md` ✅
- `tasks.md` ✅ (11/11 complete)
- `verify-report.md` ✅

**Missing artifacts (intentional)**: `design.md` was not produced — this is an annotation-only refactor whose approach, alternatives, and risks are fully documented in `exploration.md` (approach 1 empirically validated) and `proposal.md` (Approach/Risks/Rollback). No architecture decisions beyond those covered. `state.yaml` absent (orchestrator-owned metadata; not part of change artifacts).

## Traceability — Observation IDs Read

| Artifact | Engram obs | Filesystem |
|----------|-----------|------------|
| exploration | #3278 `sdd/mypy-type-safety/explore` | `exploration.md` |
| proposal | #3279 `sdd/mypy-type-safety/proposal` | `proposal.md` |
| tasks | #3280 `sdd/mypy-type-safety/tasks` | `tasks.md` |
| apply-progress | #3281 `sdd/mypy-type-safety/apply-progress` | (Engram only) |
| verify-report | #3282 `sdd/mypy-type-safety/verify-report` | `verify-report.md` |

## Mechanical Copy Verification

- Archive move: `openspec/changes/mypy-type-safety/` → `openspec/changes/archive/2026-08-12-mypy-type-safety/` via `mv` fallback (`git mv` declined the untracked folder; source confirmed gone after move).
- Pre-move recursive snapshot taken; `diff -r snapshot/source archived` → **empty output = byte-identical**. Verbatim output:

```
--- DIFF -r READBACK ---
--- END DIFF (empty = byte-identical) ---
```

## Risks / Caveats (carried from verify-report SUGGESTION)

1. The working tree carries **pre-existing uncommitted changes in the same 3 files** (reference-song sanitizer validator + description text in `app/models.py`, error-class renames `AllProvidersUnavailableError`/`PydubUnavailableError` + `audio_segment` rename in `app/music/clipchain.py`, `from exc` chaining + import reordering in `app/projects/router.py`) from the archived `form-voice-lyrics-reference` change. Rollback of this change is **not** a clean single `git revert` until those pre-existing changes are committed separately. Orchestrator should commit/separate them before the PR to keep the "single PR, 3 files" boundary real.
2. 2–3 pre-existing aiosqlite thread warnings in pytest output (non-blocking, unrelated).

## SDD Cycle Status

**COMPLETE** — planned, implemented, verified (PASS), and archived. The mypy strict gate now passes cleanly and the archived `tasks.md` shows 11/11 complete with no stale unchecked tasks.
