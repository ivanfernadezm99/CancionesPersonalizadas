# API Reference — CancionesPersonalizadas

> Todas las APIs, endpoints, variables de entorno, y servicios usados en este proyecto.

---

## 1. Variables de Entorno (`.env`)

| Variable | Obligatoria | Provider | Propósito |
|----------|-------------|----------|-----------|
| `MUSIC_PROVIDER` | Sí | — | `suno` o `openclaw` (default). Selecciona el backend de generación |
| `SUNO_API_KEY` | Si MUSIC_PROVIDER=suno | SunoAPI | API key para sunoapi.org |
| `SUNO_BASE_URL` | Si MUSIC_PROVIDER=suno | SunoAPI | `https://api.sunoapi.org` |
| `SUNO_DEFAULT_MODEL` | No | SunoAPI | `V4_5ALL` — modelo por defecto |
| `OPENCLAW_TOKEN` | Si MUSIC_PROVIDER=openclaw | OpenClaw | Token del gateway local Lyria 3 |
| `OPENCLAW_BASE_URL` | No | OpenClaw | `http://localhost:18789` |
| `OPENAI_API_KEY` | No (recomendado) | OpenAI | Para generación de letras vía LLM |
| `GOOGLE_API_KEY` | No | Gemini | Alternativa para letras |
| `OPENROUTER_API_KEY` | No | OpenRouter | Alternativa para letras |
| `MISTRAL_API_KEY` | No | Mistral | Alternativa para letras |
| `DB_PATH` | No | — | `jobs.db` — base SQLite de jobs |
| `OUTPUT_DIR` | No | — | `./output` — carpeta de MP3 generados |
| `PUBLIC_BASE_URL` | No | — | URL base para servir audios de referencia |
| `TELEGRAM_BOT_TOKEN` | Para entrega | Telegram | Bot token de `@icemorphBot` |
| `TELEGRAM_CHAT_ID` | Para entrega | Telegram | Chat ID destino |

> `TELEGRAM_*` están en `/home/servidor/.env` (fuera del proyecto), no en `.env` del proyecto.

---

## 2. Suno API (`sunoapi.org`)

**Base URL:** `https://api.sunoapi.org`  
**Auth:** `Authorization: Bearer {SUNO_API_KEY}`  
**Content-Type:** `application/json`

### 2.1 Generar Cover (`POST /api/v1/generate/upload-cover`)

Endpoint principal usado para Brenda. Toma un audio de referencia + letra.

**Payload:**
```json
{
  "uploadUrl": "https://public-url.com/reference.mp3",
  "customMode": true,
  "style": "bachata romántica latina",
  "title": "Para Brenda",
  "prompt": "[Verse 1]\nLetra completa con secciones...",
  "model": "V4_5ALL",
  "callBackUrl": "https://hooks.example.com/callback",
  "instrumental": false
}
```

**Campos obligatorios específicos:**
- `callBackUrl`: debe ser un string **no vacío** — aunque no se use un webhook real, Suno lo exige
- `instrumental`: debe ser `false` para Cover con voz
- `uploadUrl`: URL pública del audio de referencia (accesible por Suno)

**Response exitoso:**
```json
{
  "code": 200,
  "msg": "success",
  "data": { "taskId": "8d3ef9158d34e9227eb1849b4808874f" }
}
```

**Errores comunes:**
- `401`: Token inválido o faltante
- `400` con `msg`: payload inválido (falta callBackUrl, instrumental incorrecto, etc.)
- `200` con `code: 400`: error de negocio (ej: cuota excedida)

### 2.2 Generar Text-to-Music (`POST /api/v1/generate`)

Para crear canciones sin audio de referencia.

**Payload:**
```json
{
  "prompt": "bachata romántica",
  "customMode": true,
  "style": "bachata romántica",
  "title": "",
  "model": "V4_5ALL",
  "lyrics": "Letra de la canción..."
}
```

### 2.3 Polling (`GET /api/v1/generate/record-info?taskId={taskId}`)

**Response cuando está listo:**
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "taskId": "...",
    "status": "SUCCESS",
    "response": {
      "sunoData": [
        {
          "id": "...",
          "audioUrl": "https://cdn...mp3",
          "sourceAudioUrl": "https://cdn1.suno.ai/...mp3",
          "streamAudioUrl": "https://musicfile.removeai.ai/...",
          "duration": 229.96,
          "title": "Para Brenda",
          "tags": "bachata romántica latina",
          "modelName": "chirp-auk-turbo"
        }
      ]
    }
  }
}
```

**Quirks descubiertos:**
- `status` puede ser `"SUCCESS"` o `"FIRST_SUCCESS"` — ambos significan "terminado"
- `FIRST_SUCCESS` aparece cuando hay al menos una canción lista (pueden venir 2 en sunoData)
- `audioUrl` está en `response.sunoData[0].audioUrl`
- `sunoData` puede tener 2 entries (dos versiones de la canción)
- La URL de `audioUrl` expira — descargar inmediatamente
- `sourceAudioUrl` de CDN de Suno suele ser más estable

---

## 3. Telegram Bot API

**Base URL:** `https://api.telegram.org/bot{TOKEN}/`  
**Bot:** `@icemorphBot` (token en `/home/servidor/.env`)  
**Chat destino:** `1422594274`

### 3.1 Enviar Audio (`sendAudio`)

```bash
curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendAudio" \
  -F "chat_id=${CHAT_ID}" \
  -F "audio=@output/{taskId}/generated.mp3" \
  -F "title=Para Brenda" \
  -F "performer=CancionesPersonalizadas" \
  -F "caption=🎵 Canción para..."
```

**Fields:**
- `audio`: file upload (multipart)
- `title`: visible en el reproductor de Telegram
- `performer`: se muestra abajo del título
- `caption`: texto que acompaña (soporta emojis, hasta 1024 chars)

**Response:**
```json
{
  "ok": true,
  "result": {
    "message_id": 32445,
    "audio": {
      "file_id": "CQACAgEAAxkB...",
      "file_size": 5299389,
      "duration": 229
    }
  }
}
```

**Límites:**
- Archivos hasta 50MB
- Formatos: MP3, M4A, OGG, WAV, FLAC

---

## 4. Nextcloud WebDAV

**URL pública:** `https://enlaceschacocloud.duckdns.org/public.php/webdav/`  
**File drop token:** `ojAcbHDQBTX97oD`  
**Auth:** Token como username, password vacío

### 4.1 Subir archivo

```bash
curl -T /tmp/reference.mp3 \
  -H "Content-Type: audio/mpeg" \
  "https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3"
```

### 4.2 Verificar disponibilidad

```bash
curl -sI "https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3"
# Esperado: HTTP/1.1 200 OK
```

### 4.3 Auth-embedded URL (funciona con httpx, curl)

```
https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3
```

**Quirk:** La URL con `TOKEN:@host` funciona perfectamente — Suno la acepta sin problemas.

---

## 5. Whisper (Transcripción)

**Comando:** `whisper` (CLI, sistema)  
**Modelo:** `tiny` (rápido en CPU, suficiente para capturar ritmo y frases)

```bash
whisper /tmp/audio.mp3 --model tiny --language Spanish
```

**Propósito:** No es transcripción literal — es para capturar el TONO, ritmo, pausas, y frases únicas de la persona. Eso se usa como inspiración para la letra.

---

## 6. ffplay (Reproducción)

```bash
ffplay output/{taskId}/generated.mp3 -nodisp -autoexit
```

- `-nodisp`: sin ventana
- `-autoexit`: cierra al terminar

---

## 7. Provider Architecture

```
app/music/__init__.py
  └── _select_music_provider()
        ├── MUSIC_PROVIDER=suno  → SunoProvider(sunoapi.org)
        └── MUSIC_PROVIDER=openclaw → OpenClawProvider(gateway local Lyria 3)

app/music/providers.py
  ├── BaseMusicProvider (ABC)
  ├── SunoProvider
  │     ├── _health_check() → HEAD al audio de referencia
  │     ├── _invoke()       → POST upload-cover o generate
  │     ├── _poll()         → GET record-info (polls hasta SUCCESS/FIRST_SUCCESS)
  │     └── _download()     → GET audioUrl → bytes
  └── OpenClawProvider
        └── delega en OpenClawClient (app/music/openclaw.py)
```

### Provider Selection Flow (provider abstraction refactor)

```
generate() in app/music/__init__
  ↓
  ¿MUSIC_PROVIDER es "suno" y es un string (no Mock)?
    → Sí → SunoProvider.generate()
    → No → OpenClawProvider.generate() (backward compat path)
```

---

## 8. Engram Topic Keys (persistent memory)

| Topic Key | Contenido |
|-----------|-----------|
| `pattern/letra-final-brenda-suno` | Letra final aprobada de Brenda |
| `pattern/workflow-canciones-personalizadas` | Workflow documentado (referencia rápida) |
| `skill-registry` | Índice de skills instalados |
| `sdd-init/{project}` | Cache de init SDD (testing capabilities, strict TDD) |
| `pattern/letra-final-{name}-suno` | **Convención:** usar este patrón para futuras canciones |

---

## 9. OpenSpec SDD Artifacts (locales)

| Ruta | Contenido |
|------|-----------|
| `openspec/specs/suno-provider/spec.md` | Spec del provider Suno |
| `openspec/specs/music-generation/spec.md` | Spec de generación de música |
| `openspec/specs/lyrics-generation/spec.md` | Spec de generación de letras |
| `openspec/specs/clip-chaining/spec.md` | Spec de encadenamiento de clips |
| `openspec/specs/job-orchestration/spec.md` | Spec de orquestación de jobs |
| `openspec/specs/voice-configuration/spec.md` | Spec de configuración de voz |
| `openspec/specs/song-projects/spec.md` | Spec de proyectos de canciones |
| `openspec/specs/audio-streaming/spec.md` | Spec de streaming de audio |
| `openspec/changes/archive/2026-07-28-suno-ai-adapter/` | SDD completo: propuesta → spec → design → tasks → apply → verify → archive (19 tareas TDD, 130 tests) |
| `openspec/changes/archive/2026-07-28-clip-chaining-brenda/` | SDD: clip chaining para canción larga |
| `openspec/changes/archive/2026-07-27-canciones-automaticas/` | SDD: canciones automáticas |
| `openspec/changes/archive/2026-07-27-proyectos-iterativos/` | SDD: proyectos iterativos |

---

## 10. Estructura del Proyecto

```
CancionesPersonalizadas/
├── app/
│   ├── __init__.py
│   ├── config.py          ← Settings vía pydantic-settings (mapea .env)
│   ├── main.py            ← Entry point (FastAPI)
│   ├── models.py          ← Modelos SQLAlchemy
│   ├── audio_analysis.py  ← Análisis de audio
│   ├── music/
│   │   ├── __init__.py    ← generate(), _select_music_provider()
│   │   ├── providers.py   ← BaseMusicProvider, SunoProvider, OpenClawProvider
│   │   ├── openclaw.py    ← OpenClawClient (Lyria 3)
│   │   ├── clipchain.py   ← Clip chaining
│   │   └── durext.py      ← Duration extension
│   ├── jobs/              ← Job orchestration
│   ├── lyrics/            ← Lyric generation
│   ├── projects/          ← Song projects
│   ├── stream/            ← Audio streaming
│   └── voice/             ← Voice configuration
├── docs/
│   ├── workflow-canciones-personalizadas.md  ← Workflow operativo
│   └── api-reference.md   ← ← ESTE DOCUMENTO
├── openspec/              ← SDD artifacts
├── output/                ← MP3 generados
├── .env                   ← Variables de entorno del proyecto
├── .atl/skill-registry.md ← Skills instalados
└── generate_brenda_suno.py ← Script directo para generar canción
```
