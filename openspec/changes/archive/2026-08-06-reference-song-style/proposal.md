# Proposal: reference-song-style on legacy /api/generate

## Intent
Cerrar el gap de la ruta legacy `POST /api/generate`: hoy solo el flujo de proyectos acepta `reference_song`/`reference_description`, así que quien genera sin proyecto no puede usar estilos de canción de referencia.

## Scope

### In Scope
- Agregar `reference_song?: str` (max 200) y `reference_description?: str` (max 1000) a `GenerateRequest` (`app/models.py`).
- Propagarlos en `job_worker` (`app/jobs/worker.py`) a `lyrics_generate` y a `build_prompt` (reusando las funciones del flujo proyecto).
- Incluir ambos en el `metadata` del job al completar.
- Validar/ajustar tests existentes de worker y endpoint.

### Out of Scope
- **Frontend** (POSCuentasCorrientes, otro repo): sin wiring de UI.
- **Clipchain / Suno cover**: sin cambios (ya inyecta `reference_description` en su prompt; chaining forzado-off con Suno).
- **OpenClaw**: no consume audio de referencia — solo inyección de texto (limitación del provider, no se toca).
- **Subida de audio de referencia** en legacy: sin `project_id` para almacenar; se soporta solo texto (`reference_song`/`reference_description`), no `reference_audio_url`.

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `job-orchestration`: el endpoint legacy `/api/generate` (RQ-JOB-01) y `job_worker` pasan a aceptar y propagar `reference_song`/`reference_description` en los prompts de letras y voz/música.

## Approach
1. En `app/models.py` agregar los dos campos opcionales a `GenerateRequest`, reusando las mismas constraints que `SongProjectCreate` (max_length 200/1000).
2. En `app/jobs/worker.py` `job_worker`: pasar `reference_song=params.reference_song`, `reference_description=params.reference_description` a `lyrics_generate(...)` (firma ya los acepta) y a `build_prompt(...)` (idem), replicando `app/projects/__init__.py` que prefiere `reference_description` sobre `reference_song`.
3. Agregar ambos a `metadata` del job final.
4. Actualizar tests existentes (worker/endpoint) y agregar escenario con referencia.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/models.py` | Modified | Campos `reference_song`/`reference_description` en `GenerateRequest` |
| `app/jobs/worker.py` | Modified | Propagación a `lyrics_generate` y `build_prompt` + metadata |
| `tests/` | Modified | Validación de campos nuevos y comportamiento del worker |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| OpenClaw ignora audio: la referencia es solo texto | Med | Limitar el campo a texto; documentar que es style-only |
| Ambigüedad si vienen ambos campos | Bajo | Priorizar `reference_description` (igual que flujo proyecto) |
| Desvío de comportamiento de jobs legacy en vuelo | Bajo | Campos opcionales; jobs viejos siguen parseando (None) |

## Rollback Plan
Revertir los commits de `app/models.py` y `app/jobs/worker.py`; los campos son opcionales, así que jobs existentes no se rompen y el contrato de `GenerateRequest` vuelve al estado anterior sin migración de datos.

## Dependencies
- Ninguna externa. Depende de que `lyrics_generate` y `build_prompt` ya expongan los parámetros (confirmado).

## Success Criteria
- [ ] `POST /api/generate` acepta `reference_song`/`reference_description` sin error de validación.
- [ ] El prompt de letras incluye la referencia (cuando viene) y el de voz/música prioriza `reference_description`.
- [ ] Suite de tests (pytest) pasa sin romper jobs existentes.
