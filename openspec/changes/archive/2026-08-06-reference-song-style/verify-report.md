# Verify Report: reference-song-style

- Status: **PASS**
- Verdict: **PASS**

## Tests

`python3 -m pytest tests/test_worker_reference.py -v` → **3 passed** in 0.23s.

## Spec Coverage (traceability)

| Req | Descripción | Test | Resultado |
|-----|-------------|------|-----------|
| RQ-RS-01 | `GenerateRequest` acepta `reference_song` (max 200) y `reference_description` (max 1000), default `None` | Validado inline: max 200/1000 enforced vía Pydantic; `make_request` construye el modelo con ambos campos | PASS |
| RQ-RS-02 | `job_worker` propaga `reference_song` a `lyrics_generate` solo cuando `reference_description` es `None` | `test_reference_song_only_propagates_to_lyrics_and_metadata` (asserts `reference_song=REF_SONG`, `reference_description=None`) | PASS |
| RQ-RS-03 | `job_worker` propaga `reference_description` a `build_prompt` priorizando sobre `reference_song` | `test_reference_description_propagates_to_lyrics_and_voice` (desc llega a lyrics y build_prompt) | PASS |
| RQ-RS-04 | `job.metadata` persiste ambas keys (referencia o `None`) | Los 3 tests validan metadata (desc-set/song-None, song-set/desc-None, ambos-None) | PASS |
| RQ-RS-05 | Requests legacy con ambos `None` se comportan igual que antes | `test_legacy_request_without_reference_is_backward_compatible` + simulación de params dict legacy sin campos | PASS |

## Code Review Inline

- **`GenerateRequest`**: `reference_song: str | None = Field(None, max_length=200)`, `reference_description: str | None = Field(None, max_length=1000)` — default `None`, validators correctos, descripciones claras. Coincide con `SongProjectCreate` (misma firma).
- **`job_worker`**: `ref_song = getattr(params, "reference_song", None)` y `ref_desc = getattr(params, "reference_description", None)` — fallback robusto ante serializaciones legacy sin el attr.
  - Lyrics: `reference_song=ref_desc or ref_song` (desc prioriza sobre song) y `reference_description=ref_desc` → cumple RQ-RS-02.
  - Voice: `build_prompt(..., reference_description=ref_desc, reference_song=ref_song)` → `app/voice/__init__.py:73-76` hace `if reference_description ... elif reference_song`, desc prioriza → cumple RQ-RS-03.
- **Metadata**: ambas keys `reference_song` y `reference_description` setteadas (como provistas o `None`) → cumple RQ-RS-04.
- Firmas downstream (`lyrics.generate`, `build_prompt`) ya aceptaban `reference_*` como kwargs — no hubo cambios downstream, confirmado leyendo `app/lyrics/__init__.py:41-49` y `app/voice/__init__.py:36-41`.

## Backward Compatibility

Simulación inline con params dict legacy sin los nuevos campos: `GenerateRequest(**legacy)` parsea OK, ambos campos default `None` → comportamiento idéntico al pre-cambio. Sin migración de datos requerida.

## CRITICAL

None.

## WARNING

- La traza de RQ-RS-01 (validators max_length) no tiene test dedicado en el archivo; se verificó manualmente. Los límites 200/1000 se enforcean vía Pydantic pero no hay assertion de suite sobre ellos.
- Spec refiere `tests/jobs/test_worker_reference.py` pero el archivo vive en `tests/test_worker_reference.py` (layout flat, decisión de tasks). Cosmético.

## SUGGESTION

- Agregar un test unitario que valide el rechazo de `reference_song > 200` y `reference_description > 1000` (422 vía endpoint) para cubrir RQ-RS-01 explícitamente en suite.
- El `getattr` fallback es defensivo: dado que `GenerateRequest` ya incluye los campos con default, el attr siempre existe tras instanciación; podría simplificarse a acceso directo, pero no es incorrecto mantenerlo.
