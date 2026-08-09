# CancionesPersonalizadas — Agent Context

Backend FastAPI para el generador de canciones personalizadas (API-only, sin UI propia).

## Stack

- **Framework**: Python 3.10 + FastAPI + Uvicorn
- **Persistencia**: SQLite (aiosqlite, `jobs.db`)
- **Música**: Lyria 3 vía OpenClaw gateway, Suno AI Cover, clip chaining
- **Tests**: pytest + pytest-asyncio + respx (strict TDD activo)
- **Lint/format**: ruff, black, mypy (strict)

## Comandos

| Comando | Descripción |
|---------|-------------|
| `uvicorn app.main:app --host 0.0.0.0 --port 8000` | API local |
| `docker compose up -d --build` | API en contenedor (puerto 8001) |
| `pytest` | Tests |
| `ruff check .` / `ruff format .` | Lint / format |

## Frontend (MÓDULO en otro repo)

⚠️ Este backend **NO tiene frontend propio**. La UI es un módulo lazy dentro de **POSCuentasCorrientes** (Angular 21), no una app separada.

- **Repo frontend**: `~/Descargas/POSCuentasCorrientes/`
- **Módulo**: `src/app/canciones-personalizadas/` — rutas lazy montadas en `/canciones`
- **Rutas**: `/canciones/landing` (pública), `/canciones/create`, `/canciones/preview/:id`, `/canciones/checkout/:id`, `/canciones/download/:id` (protegidas por `authGuard`)

### URLs

| Entorno | URL |
|---------|-----|
| **Staging (deployado)** | `https://poscuentascorrientes-stage.up.railway.app/canciones` |
| **Producción** | `https://www.enlaceschaco.ar/canciones` (404 — módulo aún no deployado) |
| **API canciones (local Docker)** | `http://localhost:8001` → docs en `/docs` |

### Arquitectura del front

- El frontend habla con **2 backends**: POSBackend (.NET, `~/Descargas/PosBackend/`) para auth JWT y pagos (Mercado Pago), y este backend para generación/streaming de canciones.
- ⚠️ **POSBackend NO se corre local**: vive deployado en Railway. Staging: `https://posbackend-staging.up.railway.app/api`. El módulo apunta ahí con `apiBase` (ver `src/environments/environment.ts` del frontend). El repo local `~/Descargas/PosBackend/` es solo fuente de código (branch `staging`).
- ⚠️ **Ojo con el mix de entornos**: en dev, `apiBase` apunta a POSBackend staging (Railway) pero `cancionesApiBase` apunta al backend local (`http://localhost:8001/api`). El flujo checkout → pago → download solo cierra completo cuando `cancionesApiBase` también apunta al backend deployado (stage).
- Decisión de arquitectura: no unificar backends; el módulo reusa auth, roles y componentes de pago existentes de POSCuentasCorrientes.

## Deployment

### Variables de entorno en Railway (cross-repo sync)

Este backend valida JWT HS256 firmado por POSBackend. **El secreto debe sincronizarse manualmente entre los dos proyectos de Railway:**

| Proyecto Railway | Variable | Fuente |
|-----------------|----------|--------|
| `posbackend` (staging/prod) | `Jwt__Secret` | Configuración de POSBackend .NET |
| `cancionespersonalizadas` (mismo entorno) | `JWT_SHARED_SECRET` | **Debe ser idéntico a `Jwt__Secret`** |

**Procedimiento de deploy:**
1. Abrí Railway dashboard → proyecto `posbackend` → Variables → copiá `Jwt__Secret`
2. Abrí Railway dashboard → proyecto de este backend → Variables → creá/actualizá `JWT_SHARED_SECRET` con el mismo valor
3. Redeploy (o esperá a que Railway redeploye automáticamente al cambiar la variable)

**Si no coinciden:** todas las rutas protegidas (`/api/projects/*`, `/api/stream/*`, `/api/jobs/*`) devuelven **401 Unauthorized**.

### Webhook de pago (Mercado Pago)

El endpoint `/api/webhooks/payment-confirmed` está **exento de JWT** (usa `X-Webhook-Secret` en su lugar). El webhook NO funciona hasta que POSBackend implemente el dispatch `payment-confirmed` hacia este backend (ver AGENTS.md de POSBackend o crear change `add-mp-webhook-dispatch`).
