# Design: reference-song-style on legacy /api/generate

## Technical Approach

Rellena el gap de la ruta legacy `POST /api/generate`: hoy solo `app/projects/__init__.py` propaga `reference_song`/`reference_description`. El worker legacy construye los prompts sin referencia. La solución es simétrica al flujo proyecto: agregar los dos campos opcionales a `GenerateRequest` (`app/models.py`) y propagarlos en `job_worker` (`app/jobs/worker.py`) a las firmas ya existentes `lyrics_generate` (via `app.lyrics.generate`) y `build_prompt` (`app/voice`).

No se toca ninguna función downstream: solo pasan kwargs que ya aceptan.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|----------|---------|--------|-----------|
| D1: Dónde viven los campos | `app/models.py` vs `worker` | `GenerateRequest` | Único entry point tipado del job; vuelve persistente el contrato y valida via Pydantic igual que `SongProjectCreate` |
| D2: Prioridad description vs song | description-first vs song-first | **description > song** en ambos | Replica `app/projects/__init__.py` y `app/voice/__init__.py:73-76` (`elif`); evita ambigüedad |
| D3: Acceso a los campos en worker | `params.reference_*` directo vs `getattr` | `getattr(request, ..., None)` | Jobs legacy en vuelo se parsean con el `GenerateRequest` nuevo, pero un `getattr` con default hace el contrato robusto ante serializaciones viejas sin el attr |
| D4: Persistencia audit | `metadata` extendida | Inyectar ambos campos | Satisfacen RQ-RS-04 y dan trazabilidad de estilos usados |

## Data Flow

```
POST /api/generate (GenerateRequest)
        │  ref_song / ref_description (opcional)
        ▼
job_worker(job_id)  ── params = GenerateRequest(**params_dict)
        │  ref_song = getattr(params,'reference_song',None)
        │  ref_desc = getattr(params,'reference_description',None)
        │
        ├─ lyrics: lyr_ref = ref_desc or ref_song
        │    lyrics_generate(..., reference_song=lyr_ref,
        │                    reference_description=ref_desc)
        │        └─ build_user_prompt(...)  [prompts.py:95-96]
        │
        ├─ voice: build_prompt(..., reference_description=ref_desc,
        │                      reference_song=ref_song)   [voice/__init__.py:40-41]
        │        └─ desc prioriza sobre song (if/elif, líneas 73-76)
        │
        └─ metadata["reference_song"] = ref_song
           metadata["reference_description"] = ref_desc
```

## Change #1 — `GenerateRequest` (`app/models.py`, line 21)

Two optional fields appended after `voice` (line 21), mirroring `SongProjectCreate` (lines 98-103):

```python
reference_song: str | None = Field(
    None, max_length=200,
    description="Optional reference song for style (e.g. 'Bachata Rosa - Juan Luis Guerra')")
reference_description: str | None = Field(
    None, max_length=1000,
    description="Auto-generated style description from audio reference")
```

Validación de max length via Pydantic → 422 de entrada, sin touch a validators manuales.

## Change #2 — `job_worker` (app/jobs/worker.py)

- Tras `params = GenerateRequest(**params_dict)` (line 41):
```python
ref_song = getattr(params, "reference_song", None)
ref_desc = getattr(params, "reference_description", None)
```
- Lyrics (line 49-56): add `lyr_ref = ref_desc if ref_desc else ref_song` y pasar `reference_song=lyr_ref, reference_description=ref_desc`.
- Voice (line 67-71): add `reference_description=ref_desc, reference_song=ref_song`.
- Metadata (line 89-87): add `"reference_song": ref_song, "reference_description": ref_desc`.

## Interfaces / Contracts

Firma downstream ya confirmada (no cambia):
- `app/lyrics/__init__.py:generate` — `reference_song=None`, `reference_description=None` (líneas 48-49).
- `app/lyrics/prompts.py:build_user_prompt` — acepta `reference_song`/`reference_description` (líneas 95-96); la usa la rama `if reference_song` (129) y `if reference_description` (135).
- `app/voice/__init__.py:build_prompt` — `reference_song=None`, `reference_description=None` (40-41); `if reference_description` → `elif reference_song` (73-76).

## Test Plan Integration

Nuevo archivo `tests/test_worker_reference.py` (reusa el patrón de `tests/test_worker.py`: `tmp_path`, `settings` monkeypatch, `patch("app.jobs.worker.*")`). Helpers:

```python
def make_request(**overrides) -> GenerateRequest:   # defaults sin refs
def capture_metadata(job_id, db_path) -> dict:      # json.loads(job["metadata"])
```

| Spec scenario | Test asserts |
|---------------|--------------|
| `reference_description` set, song None | `mock_lyrics` llamado con `reference_description="..."`; `mock_build_prompt` recibió desc; metadata `reference_description=...`, `reference_song is None` |
| solo `reference_song` | `lyrics_generate` recibió `reference_song="Coldplay - Yellow"` y `reference_description=None`; `build_prompt` sin desc (solo song via elif); metadata afirma song |
| ambos None (legacy) | kwargs `reference_*` son `None`; metadata ambos `None`; sin cambio de contrato visible |

Verificación adicional: `build_user_prompt`/`build_prompt` unit tests ya existentes cubren el texto del prompt; no duplicar.

## Migration / Rollout

No migration. `GenerateRequest` optional; jobs legacy siguen parseando (campos default None). Rollback = revert `app/models.py` + `app/jobs/worker.py`.

## Risks

| Risk | Mitigation |
|------|-----------|
| `lyrics_generate`/`build_prompt` acepten `reference_description` como kwarg — **needs-read** | Validar en apply las firmas de `app/lyrics/__init__.py:41-56` y `app/voice/__init__.py:36-41`. En este design ya fueron verificadas leyendo el código: ambas exponen `reference_song=None`/`reference_description=None` y las usan en el prompt |

## Open Questions

- [ ] Ninguno bloqueante — las firmas downstream fueron verificadas leyendo el código real.