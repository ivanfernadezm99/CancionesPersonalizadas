# Suno — Rechazo por nombre de artista en tags (fix 2026-08-19)

## Resumen

Al generar una canción, Suno devolvía:

```
Suno generation failed: Your tags contain artist name michael jackson -
we don't reference specific artists on Our, please change your tags and try again.
```

Suno **no permite nombres de artistas** en los `style`/tags. Si el valor de
referencia (campo "Estilo de canción de referencia") contenía un artista que el
sanitizador no filtraba, el nombre viajaba hasta los tags y Suno rechazaba la
generación.

## Causa raíz

El backend ya tiene un sanitizador en capas (`app/tag_sanitizer.py` →
`sanitize_reference_song()`), aplicado en: validación Pydantic (422 con mensaje
amigable), construcción del prompt, lírica, y ambos workers. Pero solo filtra
artistas cuando:

1. Siguen un formato separable:
   - `"Canción - Artista"` → `"Canción"`
   - `"Canción de Artista"` → `"Canción"`
   - `"Canción (Artista)"` → `"Canción"`
2. O el artista está en `ARTIST_BLOCKLIST` (un set curado).

Cuando el usuario escribía un **artista solo** (ej. `"Michael Jackson"`, sin
formato separable) y ese nombre **no estaba en el blocklist**, el sanitizador lo
devolvía tal cual → el nombre llegaba a los tags de Suno → rechazo.

## Diagnóstico (cómo se descartó y confirmó)

- El mensaje de error es el de Suno, ya traducido a un mensaje amigable por
  `_translate_suno_error` (capa de red de seguridad de `SunoProvider`).
- El sanitizador pasaba `"Michael Jackson"` intacto porque no había ningún
  formato separable que detectar ni una entrada de blocklist que matcheara.

## Fix aplicado

Se amplió `ARTIST_BLOCKLIST` en `app/tag_sanitizer.py` con artistas conocidos que
Suno rechaza por nombre:

```
michael jackson, the beatles, elvis presley, queen, shakira,
madonna, luis miguel, daddy yankee, bad bunny
```

Comportamiento resultante (verificado):

| Entrada | Salida | Efecto |
|---------|--------|--------|
| `"Michael Jackson"` | `None` | Se descarta la referencia → no llega a Suno |
| `"Billie Jean - Michael Jackson"` | `"Billie Jean"` | Se limpia el artista, sobrevive la canción |
| `"Despacito"` | `"Despacito"` | Intacto |

El matcheo es **case-insensitive por substring** (diseño original del módulo), por
lo que valores como `"Género musical estilo de Michael Jackson"` también se
descartan/limpian. La idempotencia se mantiene (re-sanitizar no cambia el valor).

## Tests y entrega

- `tests/test_tag_sanitizer.py`: artistas nuevos → artist-only devuelve `None`;
  la canción sobrevive al artista (`"Michael Jackson - Billie Jean"` →
  `"Billie Jean"`, `"Billie Jean de Michael Jackson"`, `"Human Nature (Michael
  Jackson)"`); idempotencia ampliada.
- `tests/test_voice_router.py`: se actualizó `test_get_voices_jwt_enforced_contract`
  → los voz son ahora una **ruta pública** (no requieren JWT; ver abajo).
- Suite completa: **481 passed**.
- Commit `502dcea` → pusheado a `origin/main`.
- Contenedor local **reconstruido** (`docker compose up -d --build`) → fix en vivo
  en el backend que sirve sugéncias/staging.

## Contexto relacionado: `/api/voices` ahora público

En la misma tanda se hizo `/api/voices` una **ruta pública** (commit `e90b88d`,
`app/auth/middleware.py` → `PUBLIC_ROUTES`). Es un **registro estático de voces**
(espejo del `FALLBACK_VOICES` del frontend) y estaba protegido por el
`JWTAuthMiddleware` global; con un token inválido/vencido devolvía
`{"error":"invalid_token"}`. Ahora responde 200 aunque el JWT no sea válido. El
resto del flujo de canciones (proyectos, generación, estado, streaming) ya era
público vía `PUBLIC_PREFIXES`.

## Cómo evitarlo a futuro

- Si un usuario reporta otro rechazo de Suno por artista, **agregar el nombre al
  `ARTIST_BLOCKLIST`** (minúsculas, sin acentos innecesarios) en
  `app/tag_sanitizer.py`, con su test en `tests/test_tag_sanitizer.py`, y
  reconstruir el contenedor local.
- No bloquear en bloque toda la generación ante este error: el diseño actual
  descarta la referencia problemática y deja generar la canción con el resto.

## Mejora: traducir la referencia a estilo Suno-safe (2026-08-19, commit `64b05ec`)

El fix anterior evitaba el error de Suno, pero cuando el usuario pedía un estilo
de un artista (ej. "Michael Jackson - Bad"), el sanitizador dejaba solo la
palabra que sobraba ("Bad") → la canción no se parecía en nada.

Ahora el sistema **traduce la referencia a un descriptor musical escrito sin
nombres de artistas** (Suno-safe) en dos capas:

1. **Mapa offline** (`ARTIST_STYLE_DESCRIPTORS` en `app/tag_sanitizer.py`):
   artista conocido → descriptor fijo. Ej:
   - `"Michael Jackson - Bad"` → `"energético pop-funk de los años 80, bajo
     funky, ritmo hipnótico, ganchos melódicos y voz soul brillante"`
   - `"Luis Miguel - ..."` → bolero/pop romántico orquestal.
   - Cubre todos los artistas del blocklist (+ unos extra).
2. **Traductor por LLM** (`app/lyrics/style_translator.py`,
   `translate_style()`): si la referencia no está en el mapa, un LLM la
   interpreta y devuelve un descriptor de 1-2 frases (prompt que prohíbe
   nombrar artistas/canciones). Best-effort: ante cualquier fallo devuelve
   `None` y se conserva el comportamiento previo.

Integración: `app/voice/__init__.py::build_prompt` acepta `reference_style`
y usa `artist_style_for` en la rama de `reference_song`; los workers
(`app/projects/__init__.py::project_worker` y `app/jobs/worker.py`) llaman a
`translate_style(...)` y pasan el resultado como `reference_style`.

### Nota: audio de referencia (Cover)
El **modo Cover** ya está soportado en el flujo de proyectos: si el usuario
sube un audio de referencia, `project_worker` lo pasa a
`music_generate(reference_audio=...)` → Suno `upload-cover`. Ese es el único
camino "fiel" a un artista puntual (Suno igual no acepta nombres); con subir un
audio parecido a lo que quiere se acerca al sonido deseado.

### Tests
- `tests/test_tag_sanitizer.py::TestArtistStyleFor`
- `tests/test_voice_prompt.py` (artista → descriptor; `reference_style` param)
- `tests/test_style_translator.py` (fast path offline + LLM best-effort)
- Suite completa: **491 passed**.
