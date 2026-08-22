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

## Test del circuito SIN pagar (scripts/test-circuit.py)

Recorre login → create → ownership → fragments → candado 402 → checkout → **pago SIMULADO** → final → stream, sin gastar un peso ni tocar Mercado Pago de verdad.

```bash
# Circuito completo (necesita el contenedor local arriba, puerto 8001)
python3 scripts/test-circuit.py

# Solo pasos sin generación de música (no consume créditos del provider)
python3 scripts/test-circuit.py --steps login,create,ownership,fragments,gate,checkout,pay

# Contra el backend deployado
python3 scripts/test-circuit.py --base-url https://canciones.enlaceschaco.ar

# Login REAL contra POSBackend (email+password) en vez del JWT de prueba
python3 scripts/test-circuit.py --email x@y.z --password '...'
```

**Cómo funciona el "pago simulado":**
- El candado real del circuito es el webhook `POST /api/webhooks/payment-confirmed` (`app/projects/payment.py`): solo valida el header `X-Webhook-Secret` contra `PAYMENT_WEBHOOK_SECRET` (en `.env`) y marca el proyecto como `paid`. Es **idempotente**.
- El script dispara ese mismo endpoint (el que POSBackend usa en vivo) → el proyecto pasa a `paid` → `/final` (que exige `status == "paid"`, sino `402 payment_required`, `app/projects/router.py`) queda habilitado. Cero plata, cero MP.
- El paso `checkout` es **best-effort**: crea la preference de MP vía POSBackend si está alcanzable, pero si falla no rompe el circuito (el pago igual se simula por webhook).

**Cómo se hace el login:**
- Este backend NO tiene login propio (`app/auth/router.py` solo expone `GET /api/auth/health`). Solo valida JWT HS256 firmado por POSBackend con `JWT_SHARED_SECRET` (`app/config.py`, `app/auth/middleware.py`).
- El `user_id` sale de los claims ASP.NET `http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier` (o el legacy `.../ws/2005/05/identity/claims/nameidentifier`), NO del claim `sub`. El email de `.../claims/emailaddress` (o `email` plano).
- Por defecto el script **acuña un JWT de prueba** con ese claim set (igual al que emite POSBackend). Con `--email/--password` hace login real contra `POST /api/Auth/Login?authType=Interno` de POSBackend y usa ese JWT (el mismo que autentica el front).
- `--steps login` demuestra que el login importa: con token → `GET /api/projects/mine` 200; sin token → 401. `--steps ownership` demuestra que otro usuario recibiría **403** y sin token **401**.

**Dónde ver el ID del proyecto:** el proyecto creado muestra su `Project ID` al final del script + link del front (`/canciones/preview/<id>`). En el front de POSCuentasCorrientes, la página de preview muestra el ID del proyecto (ver `src/app/canciones-personalizadas/preview/preview.component.ts`). El ID también vive en la URL como route param `:id` en `/canciones/preview/:id`, `/canciones/checkout/:id` y `/canciones/download/:id`.

**Notas:**
- El `--steps final` y `--steps stream` **sí consumen créditos** del provider de música (Lyria/Suno), como en producción. El resto no.
- Requiere `JWT_SHARED_SECRET` y `PAYMENT_WEBHOOK_SECRET` en `.env` (el script los lee de ahí, no los imprime).

## Base de clientes — teléfono capturado en el login Google (POSBackend)

Para construir una base de clientes con teléfono (mensajes, promociones), el flujo quedó así (cross-repo):

- **POSBackend** (rama `staging`): el login con Google auto-crea además un `Client` mínimo (mismo email) para que exista un registro de cliente sin sucursal. El teléfono se guarda en `Client.Phone`. Endpoint nuevo `POST /api/Auth/UpdatePhone` (valida y persiste, devuelve JWT fresco con el claim `Phone`). El claim `Phone` se agrega al JWT cuando el Client tiene teléfono. `GET /api/UserManagement/current-user` ya devuelve `PhoneNumber` real.
- **POSFrontReform** (rama `stg`): tras login Google, si el JWT no trae `Phone` claim → muestra un formulario opcional de celular una vez → llama a `Auth/UpdatePhone` → continúa. Hay botón "Omitir".
- **POSCuentasCorrientes** (rama `stg`): la página de preview muestra `Contacto: email · teléfono` leídos del JWT del usuario logueado.

⚠️ El JWT solo tiene el `Phone` claim después de que el usuario lo guarda (o en logins posteriores). Antes, la preview muestra solo el email.

## Superadmin — visibilidad de todos los proyectos

- `SUPERADMIN_USER_IDS` (`.env`/`.env.docker`, coma-separado) lista los IDs (numéricos de POSBackend `User.Id`) o emails que ven **TODOS** los proyectos. En local = `5` (ivanfernandezm99@gmail.com).
- `GET /api/projects/mine` ("Mis canciones"): para superadmin devuelve todos (`list_all_projects`); para usuarios comunes solo los suyos (`user_id`).
- La comprobación de ownership (`_check_project_ownership`, `/api/stream` full) hace bypass para superadmin: puede abrir/reproducir cualquier proyecto.
- Los proyectos creados sin login se **adoptan automáticamente** al ser accedidos por un usuario autenticado (`link_project_to_user`, atómico).

## Persistencia de previews/canciones (NO borrar)

El cleanup TTL (`app/jobs/cleanup.py`, `JOB_TTL_HOURS`) **NUNCA borra jobs con status `complete`** ni sus archivos (los reproduce el panel "Mis canciones"). Solo limpia jobs viejos no completos, y al borrarlos elimina también sus filas de `project_jobs` (evita huérfanas que rompían la serialización). Si algún día se quiere volver a purgar, hay que decidirlo explícitamente.

### Importación manual de canciones (recuperación)

Cuando un mp3 sobrevive pero su fila de `jobs` fue purgada por el TTL (ej. las canciones de `~/Descargas/CancionesPersonalizadas-Audio/`), se re-linkea así: copiá el mp3 a `output/<job_id>/generated.mp3` (job_id tipo `manual-*`), insertá la fila en `jobs` (status `complete`, params con `project_id`) y el link en `project_jobs` (job_type `preview`/`final`). Cuidado: `project_jobs` alimenta el contador de la landing (`/api/projects/stats`), así que al importar/borrar filas el contador cambia. El contador muestra `previews + songs + MANUAL_SONGS_OFFSET(1)`.

### Recuperación hecha (21/08): canciones importadas al panel

- **Mamá ×6** (`manual-mama-*`): 01-FINAL (final, proyecto pago `9db74251`), 02-Preview, 03-PaymentPending, 04-Hijo, 06-Ahora + **05-Pareja recuperada de la papelera** (`~/.local/share/Trash/` → proyecto `63d46bed`, preview importable).
- **Valentina** (`manual-valentina-01`, preview en `48cca1b6`): venía como `voice_message_2026-07-28T0326Z.m4a` que era **base64** de un m4a; decodificado con `base64 -d`, convertido a mp3 con ffmpeg. Le canta el nombre a Valentina.
- ⚠️ **`05-Mama-Pareja` NO es una canción**: es una nota de voz con instrucciones de generación ("canción feliz de cumbia, masculina...") — no se importa como preview.
- Trash del file manager SÍ puede tener archivos borrados manualmente (el TTL del backend usa `unlink` directo, no pasa por papelera).

## Pago (Mercado Pago) — flujo y fixes (21/08)

El circuito completo: front → `POST /api/projects/{id}/checkout` (CP) → proxy a POSBackend `/api/checkout` (sin JWT, credenciales globales `Checkout:MercadoPago` de Railway) → preference MP → el usuario paga → MP notifica POSBackend `/api/integrations/mercadopago/notify` (HMAC) → POSBackend dispara webhook saliente a CP `/api/webhooks/payment-confirmed` con `X-Webhook-Secret` → CP marca `paid` (idempotente).

**Config imprescindible (Railway POSBackend):**
- `Checkout__WebhookSecret` **DEBE ser idéntico** a `PAYMENT_WEBHOOK_SECRET` de CP (hoy ambos = 64 chars, verificados). Si difieren → CP responde `{"error":"invalid_webhook_secret"}` y el proyecto nunca pasa a `paid`.
- `Checkout__WebhookUrl` = `https://canciones.enlaceschaco.ar/api/webhooks/payment-confirmed`.
- `Checkout:MercadoPago:AccessToken/PublicKey` en producción (`APP_USR-...`, `IsSandbox=false`).

**Fixes de redirección (CP, commit `3fc1d9d`):**
- `GET /payment/success` y `GET /payment/failure` son rutas públicas que hacen **307** al frontend (`#/canciones/download/:id` y `#/canciones/checkout/:id`). Antes devolvían `{"error":"unauthorized"}` (401) porque la ruta no existía y no era pública.
- `FRONTEND_BASE_URL` (config, `.env.docker`): el `success_url`/`failure_url` de las preferencias NUEVAS apuntan directo al frontend; fallback a las rutas `/payment/*` solo si no hay front configurado.

## Generación de letras (LLM providers) — fixes 21/08

- **Modelos de razonamiento**: `deepseek-v4-flash` y los modelos Zen (`big-pickle`, `nemotron`) gastan TODO el presupuesto en `reasoning_content` si `max_tokens` es chico → `content` vacío. Los providers OpenAI-compat usan **`max_tokens=8000`** y **fallback a `reasoning_content`** cuando `content` viene vacío. (Un solo call de DeepSeek puede razonar 4-5k tokens antes de escribir.)
- **Parseo tolerante** (`_parse_lyrics_json`): si el modelo envuelve el JSON en prosa, extrae el bloque `{...}` entre el primer `{` y el último `}`.
- **Letras del usuario**: `project_worker` usa VERBATIM los fragments cuando tienen estructura completa (`Estrofa N/Estribillo/Puente` o `[Verse]/[Chorus]`) — es lo que guarda el autodraft del front vía `replaceFragments` — sin regenerar por LLM (`lyrics_provider: custom_fragments`). El set del autodraft exige ≥1 verso + estribillo para considerarlo "completo". Stories libres → LLM.
- **Cascada actual** (el primero que responda gana): `zen-big-pickle` → `zen-nemotron` → `opencode-go` → `deepseek` → `openai` → `gemini` → `openrouter`.
- **Providers config** (keys en `.env`, gitignored; `docker-compose.override.yml` las inyecta):
  - `ZEN_API_KEY` → `https://opencode.ai/zen/v1`
  - `OPENCODE_GO_API_KEY` → **`https://opencode.ai/zen/go/v1`**, modelo `deepseek-v4-flash` SIN prefijo (con `opencode-go/` da `ModelError`). El endpoint salió del registry compilado del binario opencode.
  - `DEEPSEEK_API_KEY` → `https://api.deepseek.com/v1`, `deepseek-v4-flash`
  - `OPENAI_API_KEY` (SIN créditos — 429), `GEMINI_API_KEY` (503), `OPENROUTER_API_KEY`.

## Problemas conocidos / pendientes

- **`/v1/models` 401 cada ~2 min**: algo en el HOST (172.22.0.1) pega a CP `:8001/v1/models` sin auth → ruido en logs. No está en configs de opencode/hermes/gateway/scripts/MCP. Cosmético; falta identificar el consumidor (¿alguna herramienta usa `localhost:8001` como endpoint OpenAI?).
- **`zen-big-pickle` devuelve 500** del lado del server de Zen (flaky) — la cascada lo saltea.
- **`test_jobs_cleanup.py`** tuvo drift de fixture (`no such table: project_jobs`) — corregido con guard defensivo en `cleanup.py` (borra `project_jobs` solo si existe).
- **QA pendiente**: probar con una canción real que la final cante la letra del autodraft (fragments).
- Wedding/QA: contador landing = `previews + songs + MANUAL_SONGS_OFFSET(1)`; hoy = 27 (25 previews + 1 final + 1 offset).
