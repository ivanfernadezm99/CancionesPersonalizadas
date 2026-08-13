# Archive Report: reference-song-style

- Status: **COMPLETED**
- Verdict: **PASS**
- Archived on: **2026-08-06**
- Archived to: `openspec/changes/archive/2026-08-06-reference-song-style/`

## Summary

Closed the legacy-routing gap: `POST /api/generate` now accepts and propagates
optional `reference_song` / `reference_description` into the lyrics and
voice/music prompts, reusing the exact downstream signatures already exposed by
the project flow. No frontend wiring, no clipchain/Suno changes, no OpenClaw
changes.

## Verification

- Pipeline: explore ✅ → propose ✅ → spec ✅ → design ✅ → tasks ✅ → apply ✅ → verify ✅ (PASS)
- Tasks: **11/11 complete** (all `[x]` in `tasks.md`, no stale unchecked tasks)
- Spec coverage: **5/5** RQ-RS requirements (RQ-RS-01 → RQ-RS-05) verified PASS
- Tests: `python3 -m pytest tests/test_worker_reference.py -v` → **3 passed** in 0.22s
- Lint: `ruff check` clean on changed lines (`app/jobs/worker.py`,
  `tests/test_worker_reference.py`); 6 pre-existing E501 in `app/models.py`
  (lines 21, 109–131, `SongProjectCreate`/voice) — unrelated to this change
- CRITICAL: **None**
- WARNINGS: RQ-RS-01 max_length (200/1000) enforced via Pydantic but no dedicated
  suite assertion (verified inline); spec path `tests/jobs/...` vs actual flat
  `tests/test_worker_reference.py` (cosmetic)
- SUGGESTION: add a 422 rejection unit test for >200 / >1000 lengths; the
  `getattr` fallback could be simplified to direct access (both fine)

## Spec Sync (delta → main)

- Domain: `job-orchestration`
- `openspec/specs/job-orchestration/spec.md`
  - **MODIFIED** RQ-JOB-01 (Generate Endpoint): request body now MAY include
    optional `reference_song` / `reference_description`; body example updated
  - **ADDED** RQ-JOB-08 (Reference Song Style on Legacy Endpoint): RQ-RS-01..05
    requirements table + 3 acceptance scenarios
  - Preserved all other requirements (RQ-JOB-02..07 untouched)

## Archive Contents

- proposal.md ✅
- specs/job-orchestration/spec.md ✅ (delta)
- design.md ✅
- tasks.md ✅ (11/11 complete)
- verify-report.md ✅
- archive-report.md ✅

## Review Workload Summary

| Field | Value |
|-------|-------|
| Lines changed (prod + test) | ~50 (2 production + 1 test file) |
| 800-line budget | Low risk |
| PR shape | Single PR, <800 lines, auto-forecast |
| Chained PRs | No |
| Changed files | `app/models.py`, `app/jobs/worker.py`, `tests/test_worker_reference.py` |

## Lessons Learned

- **Small, high-reuse change**: the implementation added only ~30 lines across
  2 production files because the downstream signatures
  (`app/lyrics/__init__.py:generate`, `app/voice/__init__.py:build_prompt`)
  already accepted `reference_*` kwargs from the project flow. Maximal reuse of
  existing downstream contract → minimal diff.
- **Prioritization convention**: `reference_description` > `reference_song`
  (description-first via `if/elif`), replicated consistently from
  `app/projects/__init__.py` and `app/voice/__init__.py` to avoid ambiguity.
- **Backward compat preserved**: optional fields with `None` default + `getattr`
  fallback in `job_worker` make the contract robust against in-flight legacy
  serializations; no data migration, clean revert = plain file revert.

## Engram Observations

- `sdd/reference-song-style/verify-report` (observation ID recorded in Engram)
- `sdd/reference-song-style/archive-report` (this report, topic upsert)

## Intentional Overrides

None. Archive proceeded clean (no CRITICAL, no stale unchecked tasks, no
missing artifacts).
