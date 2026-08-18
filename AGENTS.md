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

### Landing Page — PUERTA DE ENTRADA de este proyecto

⚠️ **La landing pública de "Canciones personalizadas" es la puerta de entrada del proyecto.** Vive en un proyecto Angular aparte (NO en este backend, ni en POSCuentasCorrientes):

- **Proyecto (en esta máquina)**: `~/Descargas/LandingPage/` — landing corporativa de **Enlaces Chaco**
- **Repo**: `github.com/ivanfernadezm99/LandingPage.git` (rama `main`)
- **Sección**: `src/app/app.component.html` → `<section id="canciones">` (muestras reproducibles + efecto de boliche al reproducir)
- **Estilos**: `src/styles.scss` (muestras + boliche) — NO en `app.component.scss` (ya está al límite del budget de 20 kB)
- **Audios de muestra**: `src/assets/canciones-samples/` (copiados desde `~/Descargas/CancionesPersonalizadas-Audio/`)
- **Flujo**: la landing muestra las muestras → su CTA lleva a la app funcional `https://poscuentascorrientes-stage.up.railway.app/#/canciones/landing` (módulo de POSCuentasCorrientes) → checkout/pago en POSBackend.

**Errores a evitar**: NO confundir la landing (LandingPage) con el módulo funcional de canciones (POSCuentasCorrientes). Cambios de la landing se pushean a `LandingPage` (rama `main`); cambios del módulo funcional, a `POSCuentasCorrientes` (rama `stg`).

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

> ⚠️ **Estado actual (IMPORTANTE)**: este backend corre **localmente en Docker** (`docker compose up -d --build`, puerto `8001`), **NO en Railway**. Para desarrollo/testing, las variables viven en `.env` (local, gitignored) y `.env.docker`, y el override (`docker-compose.override.yml`) inyecta los secretos desde `.env` al contenedor. Solo **POSBackend** está deployado en Railway (staging: `https://posbackend-staging.up.railway.app`). La sección de Railway (abajo) aplica **únicamente cuando este backend se deploye a producción**; no setear variables en Railway para este backend por ahora.

### Variables de entorno en Railway (cross-repo sync) — SOLO para deploy futuro

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

El endpoint `/api/webhooks/payment-confirmed` está **exento de JWT** (usa `X-Webhook-Secret`). Flujo completo:

```
CP ──POST /api/checkout──▶ POSBackend (crea preference MP) ──▶ payer paga
   ──▶ MP notifica POSBackend (/api/integrations/mercadopago/notify)
   ──▶ POSBackend despacha POST {Checkout:WebhookUrl} con X-Webhook-Secret
   ──▶ CP marca el proyecto "paid" (idempotente)
```

- El dispatch POSBackend → CP **ya está implementado y deployado** (commit `d21f13ad` de PosBackend, rama `staging`). No hay que escribir código nuevo.
- **Secret compartido**: `PAYMENT_WEBHOOK_SECRET` (este backend) DEBE ser idéntico a `Checkout__WebhookSecret` de POSBackend (Railway). Si no coinciden → 401 silencioso.
- **Falta configurar en Railway (POSBackend)**: `Checkout__MercadoPago__AccessToken` (+ `PublicKey`). Sin eso, `/api/checkout` devuelve 503 `checkout_not_configured`. Las credenciales salen del panel de Mercado Pago (ver abajo).

#### Acceso al contenedor local (VPN)

El contenedor (`cancionespersonalizadas-api`, puerto `8001`) se expone por la red **Tailscale** del usuario (máquina `servidor-MS-7693`, IP tailnet `100.69.147.88`). Para que POSBackend (Railway) pueda disparar el webhook, la `Checkout__WebhookUrl` de POSBackend debe apuntar a una URL alcanzable por VPN/túnel, **NO** a `localhost`.

#### Credenciales Mercado Pago (para POSBackend)

Se obtienen en https://www.mercadopago.com.ar/developers/panel → **Tus integraciones** → elegir/crear la aplicación → **Credenciales**:
- **Credenciales de prueba** (sandbox): `Access Token` (`TEST-...`) + `Public Key` (`TEST-...`).
- **Credenciales de producción**: `Access Token` (`APP_USR-...`) + `Public Key` (`APP_USR-...`).

Para staging/testing usar las de **prueba** (sandbox, `IsSandbox=true` por default). Se setean en Railway → POSBackend → `Checkout__MercadoPago__AccessToken` / `Checkout__MercadoPago__PublicKey`.
