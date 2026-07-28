# 🎵 Canciones Personalizadas

**Generá canciones románticas personalizadas en español con inteligencia artificial.**

Contás tu historia — elegís el género, el tono y la voz — y el sistema compone
la letra con un LLM, la convierte en música con **Google Lyria 3** y te entrega
un MP3 listo para escuchar y compartir.

> **v0.1.0** — API REST solamente. Sin frontend, sin pagos, sin registro.
> Solo la magia de crear una canción única para alguien especial.

---

## ✨ Cómo funciona

```
Tú contás la historia → LLM escribe la letra → Lyria 3 la canta → Recibís el MP3
```

| Paso | Qué pasa | Tiempo estimado |
|------|----------|-----------------|
| **1. Pedido** | Enviás nombre, ocasión, género, tono y una historia opcional | Instantáneo |
| **2. Letra** | Un LLM (OpenAI, Gemini o OpenRouter) genera 2-3 versos + coro personalizados en español | ~5-10 seg |
| **3. Música** | Google Lyria 3 genera la canción con la letra, el género y la voz que elegiste | ~30-180 seg |
| **4. Post-producción** | Se extiende la duración a ~2:30 min con crossfade natural | ~2 seg |
| **5. Descarga** | Podés escuchar el MP3 via streaming o descargarlo | Listo |

**Pipeline completo:**
```
POST /api/generate
       ↓
  ┌──────────────┐
  │  Job creado   │  ← estado: queued
  │  (UUID v4)    │
  └──────┬───────┘
         ↓
  ┌──────────────┐
  │ LLM escribe   │  ← estado: lyrics_generating
  │ la letra      │     progreso: 20%
  └──────┬───────┘
         ↓
  ┌──────────────┐
  │ Lyria 3       │  ← estado: music_generating
  │ genera música │     progreso: 50%
  └──────┬───────┘
         ↓
  ┌──────────────┐
  │ Post-prod:    │  ← estado: processing
  │ extender      │     progreso: 80%
  │ duración      │
  └──────┬───────┘
         ↓
  ┌──────────────┐
  │ ✅ Completado │  ← estado: complete
  │ MP3 listo     │     progreso: 100%
  └──────────────┘
```

---

## 🚀 Quick Start

### Requisitos

- **Python 3.10+**
- **ffmpeg** (para extensión de duración con pydub)
- **OpenClaw gateway** corriendo en `localhost:18789` (para generación de música)
- **API keys**: al menos un LLM (OpenAI / Gemini / OpenRouter) + token de OpenClaw

### Instalación

```bash
# 1. Clonar
git clone <repo> canciones-personalizadas
cd canciones-personalizadas

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -e ".[dev]"

# 4. Configurar variables de entorno
cp .env.example .env
nano .env
# Completá al menos OPENAI_API_KEY, GEMINI_API_KEY o OPENROUTER_API_KEY
# Y OPENCLAW_TOKEN para generación de música

# 5. Verificar que funciona
python3 -m pytest tests/ -q --tb=short
# ✅ 196 passed

# 6. Iniciar servidor
uvicorn app.main:app --reload --port 8000
```

### Probar con curl

```bash
# Crear una canción
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "María",
    "relationship": "pareja",
    "occasion": "aniversario",
    "genre": "bachata",
    "mood": "romántica",
    "voice": "female",
    "story": "Nos conocimos en una plaza de Buenos Aires un domingo de sol. Ella llevaba un vestido amarillo."
  }'

# Respuesta:
# {
#   "job_id": "abc-123...",
#   "status": "queued",
#   "estimated_total_seconds": 180,
#   "endpoints": {
#     "status": "/api/status/abc-123...",
#     "stream": "/api/stream/abc-123..."
#   }
# }

# Consultar estado
curl http://localhost:8000/api/status/abc-123...

# Escuchar / descargar (cuando esté completo)
curl http://localhost:8000/api/stream/abc-123... --output cancion.mp3
```

---

## 📡 API

### `POST /api/generate`

Creá un nuevo trabajo de generación de canción.

**Request body:**

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `recipient` | string (1-100) | ✅ | Nombre del destinatario de la canción |
| `relationship` | string (1-50) | ✅ | Relación: "pareja", "amigo", "mamá", etc. |
| `occasion` | string (1-100) | ✅ | Ocasión: "aniversario", "cumpleaños", "casamiento", etc. |
| `genre` | string (1-50) | ✅ | Género musical (ver lista abajo) |
| `mood` | string (1-50) | ✅ | Tono emocional (ver lista abajo) |
| `voice` | string (1-50) | No | Voz: `"female"` (default) o `"male"` |
| `story` | string (max 2000) | No | Historia personal, anécdota o recuerdo |

**Géneros disponibles:** `bachata`, `balada`, `reggaeton`, `salsa`, `pop`, `cumbia`, `vallenato`, `trap`

**Tonos:** cualquier descripción como `"romántica"`, `"festiva"`, `"nostálgica"`, `"divertida"`, etc.

**Respuesta `202 Accepted`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "estimated_total_seconds": 180,
  "endpoints": {
    "status": "/api/status/550e8400-e29b-41d4-a716-446655440000",
    "stream": "/api/stream/550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

### `GET /api/status/{job_id}`

Consultá el estado de un trabajo.

**Respuesta:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "music_generating",
  "progress": 0.5,
  "estimated_remaining_seconds": 90,
  "error": null,
  "metadata": {},
  "created_at": "2026-07-27T12:00:00+00:00",
  "updated_at": "2026-07-27T12:00:45+00:00"
}
```

**Estados posibles:** `queued` → `lyrics_generating` → `music_generating` → `processing` → `complete` / `failed`

---

### `GET /api/stream/{job_id}`

Streaming o descarga del MP3 generado. Soporta **HTTP Range** para búsqueda en navegadores.

**Respuesta (`complete`):**
- `200 OK` con `Content-Type: audio/mpeg`
- `X-Freemium-Preview: true` (identifica que es preview gratuito)
- Soporta header `Range: bytes=...` para streaming parcial

**Respuesta (en progreso):**
- `409 Conflict` con `Retry-After` estimado

**Respuesta (no encontrado):**
- `404 Not Found` o `410 Gone` si expiró

---

### `GET /`

Información del servicio:
```json
{
  "name": "Canciones Automáticas",
  "version": "0.1.0",
  "description": "AI-powered personalized romantic song generator in Spanish"
}
```

---

## ⚙️ Configuración

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `OPENAI_API_KEY` | ⚠️ Una de tres | `""` | API key de OpenAI (GPT-4o) |
| `GEMINI_API_KEY` | ⚠️ Una de tres | `""` | API key de Google Gemini |
| `OPENROUTER_API_KEY` | ⚠️ Una de tres | `""` | API key de OpenRouter |
| `OPENCLAW_TOKEN` | ✅ Sí | `""` | Token del gateway OpenClaw |
| `OPENCLAW_BASE_URL` | No | `http://localhost:18789` | URL base de OpenClaw |
| `DB_PATH` | No | `jobs.db` | Ruta a la base SQLite |
| `OUTPUT_DIR` | No | `./output` | Directorio de MP3 |
| `JOB_TTL_HOURS` | No | `24` | TTL de jobs en horas |
| `CLEANUP_INTERVAL_SECONDS` | No | `3600` | Intervalo de limpieza |
| `MAX_CONCURRENT_JOBS` | No | `5` | Generaciones simultáneas máximas |

> Las API keys de LLM se cascaden automáticamente: primero OpenAI, si falla Gemini, si falla OpenRouter.

---

## 📁 Estructura del proyecto

```
canciones-personalizadas/
├── app/                          # Código fuente
│   ├── main.py                   # FastAPI app, endpoints, rate limiting
│   ├── config.py                 # Config vía pydantic-settings / .env
│   ├── models.py                 # Modelos Pydantic compartidos
│   ├── jobs/                     # Sistema de trabajos asíncronos
│   │   ├── __init__.py           # API pública: create/get/update/count
│   │   ├── store.py              # Conexión SQLite + schema
│   │   ├── state.py              # Máquina de estados con validación
│   │   ├── worker.py             # Orquestador: letras → música → post-prod
│   │   └── cleanup.py            # Limpieza periódica por TTL
│   ├── lyrics/                   # Generación de letras con LLM
│   │   ├── __init__.py           # Orquestador multi-provider
│   │   ├── prompts.py            # Prompts en español por género musical
│   │   └── providers.py          # OpenAI, Gemini, OpenRouter + cascade
│   ├── music/                    # Generación de música con Lyria 3
│   │   ├── __init__.py           # API pública generate()
│   │   ├── openclaw.py           # Cliente HTTP para OpenClaw gateway
│   │   └── durext.py             # Extensión de duración con pydub
│   ├── voice/                    # Selección de voz
│   │   ├── __init__.py           # build_prompt() para Lyria 3
│   │   └── registry.py           # Registro de voces (female, male)
│   └── stream/                   # Streaming de audio
│       ├── __init__.py           # Generador asíncrono con chunks
│       └── router.py             # GET /api/stream/{id} con HTTP Range
├── tests/                        # Suite de 196 tests
│   ├── conftest.py               # Fixtures compartidos
│   ├── test_main.py              # Tests del servidor FastAPI
│   ├── test_jobs_api.py          # Tests de endpoints REST
│   ├── test_jobs_store.py        # Tests de persistencia SQLite
│   ├── test_jobs_state.py        # Tests de máquina de estados
│   ├── test_jobs_cleanup.py      # Tests de limpieza TTL
│   ├── test_lyrics_generate.py   # Tests de generación de letras
│   ├── test_lyrics_providers.py  # Tests de providers LLM
│   ├── test_music/               # Tests de generación musical
│   ├── test_stream/              # Tests de streaming
│   ├── test_voice_prompt.py      # Tests de construcción de prompts
│   ├── test_voice_registry.py    # Tests de registro de voces
│   ├── test_worker.py            # Tests del worker pipeline
│   └── test_integration.py       # Tests de integración completos
├── pyproject.toml                # Config del proyecto y dependencias
├── .env.example                  # Template de configuración
└── .gitignore
```

**Stack técnico:**

| Componente | Tecnología |
|-----------|------------|
| Framework web | FastAPI + uvicorn |
| Base de datos | SQLite (aiosqlite async, WAL mode) |
| Letras | LLMs: OpenAI GPT-4o, Gemini 2.0 Flash, OpenRouter |
| Música | Google Lyria 3 via OpenClaw gateway |
| Audio | pydub + ffmpeg (duración extendida a ~2:30min) |
| Validación | Pydantic v2 + pydantic-settings |
| Testing | pytest + pytest-asyncio + respx + coverage 90% |
| Calidad | ruff + black + mypy (strict) |

---

## 🔄 Pipeline interno

### 1. Letras con LLM

- Se construye un **prompt en español** adaptado al género musical (bachata, balada, reggaetón, etc.)
- El prompt incluye: nombre del destinatario, relación, ocasión, tono e historia opcional
- Los providers se prueban en **cascada automática**: OpenAI → Gemini → OpenRouter
- El primer provider que devuelve un JSON válido gana
- El LLM devuelve la letra como JSON estructurado: versos, coro, puente opcional y título sugerido

### 2. Música con Lyria 3

- Se envía la letra formateada (`[Verse 1]`, `[Chorus]`, `[Bridge]`) + un prompt de estilo al gateway OpenClaw
- OpenClaw devuelve un **task ID** para hacer poll asíncrono (cada 5s, backoff hasta 30s, timeout 5min)
- Cuando la tarea se completa, se descarga el MP3 generado

### 3. Post-producción

- Lyria 3 genera ~60-90 segundos; se extiende a ~2:30 minutos
- Primero intenta **crossfade loop**: toma el último 10% como intro y concatena con crossfade de 2s
- Si falla, usa **simple loop** (concatenación directa con fade-out)
- Si no hay ffmpeg/pydub, devuelve el audio original sin extender

### 4. Streaming

- El endpoint `/api/stream/{job_id}` sirve el MP3 con soporte HTTP Range para búsqueda
- Usa un generador asíncrono con chunks de 64KB y detección de desconexión

### 5. Limpieza automática

- Un worker en background elimina jobs y archivos viejos cada hora (configurable)
- Default: 24 horas de TTL

---

## 🧪 Tests

```bash
# Ejecutar toda la suite
python3 -m pytest tests/ -q

# Con cobertura
python3 -m pytest tests/ --cov=app --cov-report=term

# Tests específicos
python3 -m pytest tests/test_lyrics_providers.py -v
python3 -m pytest tests/test_jobs_state.py -v

# Con reporte HTML
python3 -m pytest tests/ --cov=app --cov-report=html
```

**Cobertura actual:** 90% (822 statements, 80 missed)

---

## 🗺️ Roadmap v1 (ideas)

- [ ] Frontend web (SPA o formulario simple)
- [ ] Más voces en el registry
- [ ] Vista previa de letra antes de generar música
- [ ] Corrección de letra por el usuario
- [ ] Historial de canciones
- [ ] Descarga de letra en PDF
- [ ] Modo instrumental
- [ ] Post-producción: ecualización, normalización de volumen

---

## 📄 Licencia

MIT — hacé lo que quieras, pero si creás algo lindo para alguien especial, contá la historia.

---

<p align="center">
  Hecho con ❤️ y mucha música<br>
  <em>"Tú contás la historia — nosotros la convertimos en canción"</em>
</p>
