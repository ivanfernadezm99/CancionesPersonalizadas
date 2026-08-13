# Tasks: Add reference song style to legacy /api/generate

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~40-60 (2 source files + 1 test) |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Reference song style support in /api/generate | PR 1 | Single PR, <800 líneas |

## Phase 1: Tests (TDD — RED first)

- [x] 1.1 Crear `tests/test_worker_reference.py` con fixture worker + mock de `lyrics_generate`
- [x] 1.2 Scenario A: `reference_song` presente → assert propagado a `lyrics_generate` y metadata
- [x] 1.3 Scenario B: `reference_description` presente → assert en `build_prompt` y metadata
- [x] 1.4 Scenario C: ambos ausentes → assert `None` por defecto, sin regresión en prompt

## Phase 2: Modelo (GREEN)

- [x] 2.1 `app/models.py:GenerateRequest` → `reference_song: Optional[str] = None` (max 200)
- [x] 2.2 `app/models.py:GenerateRequest` → `reference_description: Optional[str] = None` (max 1000)

## Phase 3: Worker (GREEN)

- [x] 3.1 `app/jobs/worker.py:job_worker` → propagar `reference_song`/`reference_description` a `lyrics_generate`
- [x] 3.2 `app/jobs/worker.py` → pasar fields a `build_prompt`
- [x] 3.3 `app/jobs/worker.py` → setear metadata del job con ambos fields

## Phase 4: Verificación

- [x] 4.1 Correr `python3 -m pytest` full suite, arreglar regresiones
- [x] 4.2 `ruff check .` y `ruff format .` sin errores

## DAG

T1 (RED) → T2 (GREEN) → T3 (GREEN) → T4 (verificación) — secuencial TDD
