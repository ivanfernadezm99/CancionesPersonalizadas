# Design: Suno Tag Validation (artist names in reference_song)

## Technical Approach

One pure, dependency-free module `app/tag_sanitizer.py` applied at three layers, per the proposal:

1. **Input**: Pydantic `field_validator` on `SongProjectCreate`/`SongProjectUpdate` → sanitize-and-store, reject artist-only with 422.
2. **Generation**: `build_prompt` (voice) and `build_user_prompt` (lyrics) sanitize before injecting → covers legacy stored projects and both worker paths.
3. **Error net**: `SunoProvider._invoke` translates the opaque Suno artist-rejection message to friendly Spanish.

Frontend mirrors the strip heuristic and fixes the hint. Specs: RQ-TAG-01..04, RQ-PRJ-01/02, RQ-REF-01, RQ-VOI-05, RQ-LYR-04/06, RQ-SUNO-01, RQ-JOB-02/06/08.

## Architecture Decisions

| Decision | Tradeoffs | Choice |
|----------|-----------|--------|
| Sanitizer location | `app/models` would create import coupling; a shared module is importable everywhere | New `app/tag_sanitizer.py`; pure function, no I/O, no app imports → zero circular-import risk |
| Validator scope | Applying to `GenerateRequest` would 422 the legacy endpoint (RQ-RS-05 backward compat) | Validator ONLY on `SongProjectCreate`/`SongProjectUpdate`; legacy path sanitizes at generation time |
| Empty-string handling | Sanitizer returns `None` for empty, but RQ-PRJ-01 requires `""` to remain valid | Validator passes `None`/`""` through unchanged; only a *non-empty* value that sanitizes to `None` raises ValueError → 422 |
| Strip order | Blocklist on raw input would reject "Los Palmeras - Mi Amor" (a valid song) | Strip separators first, then substring-blocklist the remainder; blocklist entries lowercase, matched case-insensitively |
| Double sanitization | `build_prompt` AND workers both sanitize | Safe — strip/blocklist are idempotent; defense in depth for future drift |
| Shared message | Two Spanish messages would drift | One constant `ARTIST_REJECTION_MESSAGE` in `tag_sanitizer.py`, reused by validator and Suno translator |
| Translation site | Only in `_invoke`'s biz-code branch would miss the HTTP-!=200 branch | Pure helper `_translate_suno_error(msg)` applied at both raise sites in `_invoke` |
| `job_worker` lyrics ref | RQ-RS-02: song only when description is `None` | Keep `ref_desc or ref_song` (matches current semantics), but sanitize `ref_song` first; metadata persists ORIGINALS (RQ-RS-04) |
| Blocklist content | RQ-TAG-03 requires "Juan Luis Guerra" (non-Argentine) | Curated set of *known-rejected artist names*, not strictly Argentine: seed with `los palmeras`, `la mona jiménez`, `juan luis guerra`; extensible |
| Frontend mirror | Full blocklist client-side would need server sync | Mirror strip-only; blocklist hits surface the server 422/friendly error |

## Data Flow

```
POST /api/projects ──► SongProjectCreate validator ──► sanitize_reference_song ──► store (sanitized)
        │ artist-only ──► ValueError ──► 422 (Spanish)
        │
GET  stored project (legacy raw value)
        │
        ▼
project_worker / job_worker ──► sanitize_reference_song ──► build_prompt + lyrics_generate
        │                                                          │
        ▼                                                          ▼
SunoProvider._invoke ── artist-rejection msg ──► _translate_suno_error ──► job.error (Spanish)
        │
        ▼
GET /api/status ──► job.error ──► frontend failure state (renders error as-is)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/tag_sanitizer.py` | Create | `sanitize_reference_song`, `ARTIST_REJECTION_MESSAGE`, `ARTIST_BLOCKLIST` |
| `app/models.py` | Modify | Validators on `SongProjectCreate`/`SongProjectUpdate`; update `reference_song` docstrings (song-only examples) |
| `app/voice/__init__.py` | Modify | `build_prompt`: sanitize before appending style line; skip if no usable token |
| `app/lyrics/prompts.py` | Modify | `build_user_prompt`: sanitize before `Referencia musical:` block; skip if none |
| `app/music/providers.py` | Modify | `_translate_suno_error` + apply at both `_invoke` raise sites |
| `app/projects/__init__.py` | Modify | `project_worker`: sanitize `metadata["reference_song"]` before lyrics + prompt |
| `app/jobs/worker.py` | Modify | `job_worker`: sanitize `ref_song` before lyrics + prompt |
| `tests/*` | Modify | `test_voice_prompt.py`, `test_lyrics_generate.py`, `test_projects_router.py`, `test_projects_orchestrator.py`, `test_worker_reference.py` — expect sanitized tokens; new `tests/test_tag_sanitizer.py` |
| `POSCuentasCorrientes: src/app/canciones-personalizadas/create/create-project.component.ts` | Modify | Hint text → song-only examples (line ~105) |
| `POSCuentasCorrientes: src/app/canciones-personalizadas/reference-song.ts` | Create | Client-side `sanitizeReferenceSong` mirror; applied in payload build (lines ~790/874) |

## Interfaces / Contracts

```python
# app/tag_sanitizer.py
ARTIST_REJECTION_MESSAGE = (
    "El nombre de la canción de referencia contiene un artista. "
    "Por favor quitá el nombre del artista y probá de nuevo."
)
ARTIST_BLOCKLIST: frozenset[str] = frozenset({...})  # lowercase; seed: los palmeras, la mona jiménez, juan luis guerra

def sanitize_reference_song(value: str | None) -> str | None:
    """Strip 'Song - Artist' / 'Song de Artist' / 'Song (Artist)' (case-insensitive,
    trimmed). Blocklist substring-match on remainder. Return song token, or None
    when no usable reference (artist-only, empty, or blocklist hit)."""
```

Validator (same pattern as `_validate_voice`):

```python
def _validate_reference_song(v: str | None) -> str | None:
    if v is None or not v.strip():
        return v
    sanitized = sanitize_reference_song(v)
    if sanitized is None:
        raise ValueError(ARTIST_REJECTION_MESSAGE)
    return sanitized
```

`_translate_suno_error(msg: str) -> str` in providers.py matches `artist\s+name` / `tags?.*contain.*artist` (IGNORECASE).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Sanitizer table (RQ-TAG-01..03), idempotency, blocklist, `""`/`None` | Parametrized `test_tag_sanitizer.py` |
| Unit | Validator: strip-on-create/patch, 422 artist-only, empty passes; `GenerateRequest` untouched | Pydantic model tests |
| Unit | `_translate_suno_error`: pattern → Spanish, other errors preserved | Direct function tests |
| Integration | `build_prompt`/`build_user_prompt` sanitize; workers pass sanitized refs; metadata keeps originals | Extend existing worker/router tests + respx Suno 400 |
| E2E/Frontend | Hint text; mirror util; error rendering | Update component specs |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Pure validation + error-translation logic.

## Migration / Rollout

No data migration — stored `reference_song` untouched; guard is read-time (matches rollback plan). Rollback: remove sanitizer call sites; keep translation if isolated.

## Open Questions

- [ ] RQ-VOI-05/RQ-LYR-06 scenarios assert suffix "al estilo de Bachata Rosa", but templates say "Inspirada en el estilo de {song}". Recommend tasks/apply assert song-presence + artist-absence; update scenario wording if literal.
- [ ] Blocklist seed set beyond the 3 mandated entries (~10 popular Argentine artists) — product decision, non-blocking.
