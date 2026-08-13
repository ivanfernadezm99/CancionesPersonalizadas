# Archive Report: suno-tag-validation

**Change**: suno-tag-validation — Sanitize artist names out of `reference_song` before Suno tags
**Archived**: 2026-08-11
**Artifact store**: hybrid (OpenSpec + Engram)
**Verification**: PASS — 14/14 requirements, 51/51 scenarios
**Tasks**: 17/17 complete (no stale unchecked implementation tasks)

## Summary

This change introduced a shared tag sanitizer that strips artist names from `reference_song` before any value reaches Suno's tags, applied at four layers: input validation (Pydantic 422), generation time (`build_prompt` + lyrics builder covering legacy storage and both worker paths), Suno error translation as a safety net, and a client-side mirror in the frontend. It also made Suno artist-rejection errors non-retryable and translated them to a friendly Spanish message.

## Delta Specs Merged → Canonical Specs

| Domain | Delta file | Action on `openspec/specs/` | Requirements touched |
|--------|-----------|----------------------------|----------------------|
| tag-sanitization | `specs/tag-sanitization/spec.md` | **Created** (new domain) | RQ-TAG-01..04 (4 added) |
| song-projects | `specs/song-projects/spec.md` | **Updated** (modified) | RQ-PRJ-01 (sanitize on create + 3 scenarios), RQ-PRJ-02 (sanitize on patch + 2 scenarios), RQ-REF-01 (song-only hint + friendly error + 2 scenarios) |
| voice-configuration | `specs/voice-configuration/spec.md` | **Updated** (modified) | RQ-VOI-05 (sanitize before append + 2 new scenarios) |
| lyrics-generation | `specs/lyrics-generation/spec.md` | **Updated** (modified) | RQ-LYR-04 (sanitized token, artist absent, no-style-guidance scenario), RQ-LYR-06 (sanitized reference, legacy artist-only scenario) |
| suno-provider | `specs/suno-provider/spec.md` | **Updated** (modified) | RQ-SUNO-01 (Spanish translation + 2 error-translation bullets) |
| job-orchestration | `specs/job-orchestration/spec.md` | **Updated** (modified) | RQ-JOB-02 (translated error scenario), RQ-JOB-06 (non-retryable + translated scenario), RQ-JOB-08 (RQ-RS-06 + consistent-sanitization scenario) |

No REMOVED or RENAMED requirements in this change. No destructive merges.

## Archive Contents

- `exploration.md` ✅
- `proposal.md` ✅
- `specs/` — 6 delta domains ✅
- `design.md` ✅
- `tasks.md` ✅ (17/17 complete, 0 unchecked)
- `apply-progress.md` ✅
- `verify-report.md` ✅ (PASS, archive-ready)
- `archive-report.md` ✅ (this file)

## Merge Integrity Notes

- All existing MODIFIED requirements were replaced in full (including preserved unchanged scenarios per OpenSpec convention).
- Requirements not mentioned in the deltas (e.g. song-projects RQ-PRJ-03..09/RQ-IDEA/RQ-DIT-*, voice RQ-VOI-01..04/RQ-VOICE-*, lyrics RQ-LYR-01..03/05/07, suno RQ-SUNO-02..06, job RQ-JOB-01/03/04/05/07) were preserved unchanged.
- The delta specs were consolidated into the canonical `openspec/specs/`; the change folder now lives at `openspec/changes/archive/2026-08-11-suno-tag-validation/`.

## Intentional-with-Warnings Notes (carried, not blockers)

The verify-report carries forward 5 non-blocking WARNINGs and a SUGGESTION list for orchestrator decision (dash tie-break orientation, literal scenario wording, RQ-SUNO-01 429 bullet unimplemented as pre-existing baseline outside translation scope, RQ-LYR-04 chorus-name conflict, pre-existing test failures). These do not block the archive and are recorded in the archived verify-report for the audit trail.

## Traceability (Engram)

Archive report persisted to Engram topic `sdd/suno-tag-validation/archive-report`.