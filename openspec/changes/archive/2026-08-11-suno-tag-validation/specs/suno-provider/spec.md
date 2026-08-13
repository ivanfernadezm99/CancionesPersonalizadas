# Delta for Suno Provider

## MODIFIED Requirements

### RQ-SUNO-01: Text-to-Music

`POST /api/generate` with `prompt`, `lyrics`, `model`. Returns generation ID for polling.

When `SunoProvider._invoke` receives a response whose error message indicates Suno's artist rejection (e.g. `Your tags contain artist name ...`), the provider MUST raise the error translated to a friendly Spanish message instead of the raw English text. The translated message MUST be: "El nombre de la canción de referencia contiene un artista. Por favor quitá el nombre del artista y probá de nuevo."
(Previously: the raw English Suno error message was raised and persisted verbatim in the job `error` field.)

- GIVEN lyrics + prompt WHEN `generate()` called THEN Suno API receives params AND generation ID returned
- GIVEN HTTP 429 WHEN received THEN wait Retry-After AND retry
- GIVEN a response with `code=400` and a message matching the artist-rejection pattern WHEN `_invoke` raises THEN the raised error MUST be the friendly Spanish translation
- GIVEN any other Suno error message WHEN `_invoke` raises THEN the original message MUST be preserved unchanged
