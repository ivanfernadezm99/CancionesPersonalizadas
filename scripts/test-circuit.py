#!/usr/bin/env python3
"""test-circuit.py — Recorre el circuito completo de CancionesPersonalizadas SIN pagar.

Demo de que el login funciona, crea un proyecto, le carga la historia, simula el
pago por webhook (cero plata), genera la canción final y verifica el stream.

Pasos (--steps, por defecto todos):
  login       Acuña un JWT HS256 de prueba (o usa login real contra POSBackend) y
              demuestra que el backend lo acepta (GET /api/projects/mine).
  create      Crea un proyecto con el token (queda asociado al usuario).
  ownership   Demuestra que el login importa: otro usuario -> 403, sin token -> 401.
  fragments   Carga los story fragments de la canción.
  gate        Demuestra el candado: /final antes de pagar -> 402 Payment Required.
  checkout    Crea la preference de Mercado Pago vía POSBackend (best-effort,
              no fatal: el pago se simula igual por webhook).
  pay         SIMULA el pago disparando el webhook con X-Webhook-Secret -> "paid".
  final       Genera la canción final (CONSUME créditos del provider de música).
  stream      Verifica la descarga/stream del audio final (200 y 206 con preview).

Uso:
  python3 scripts/test-circuit.py                      # circuito completo
  python3 scripts/test-circuit.py --steps login,create,pay
  python3 scripts/test-circuit.py --base-url https://canciones.enlaceschaco.ar
  python3 scripts/test-circuit.py --email x@y.z --password '...'   # login real POSBackend

Lee los secretos del .env del repo (JWT_SHARED_SECRET, PAYMENT_WEBHOOK_SECRET,
PAYMENT_GATEWAY_URL). No imprime secretos.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
EMAIL_URI = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"

ALL_STEPS = ["login", "create", "ownership", "fragments", "gate", "checkout", "pay", "final", "stream"]
PASS, FAIL = "✅", "❌"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def mint_jwt(secret: str, user_id: str, email: str = "test@enlaceschaco.ar", ttl: int = 3600) -> str:
    """Acuña un JWT HS256 con los claims ASP.NET que el middleware de CP espera.

    Es exactamente lo que emite POSBackend para este backend (misma firma y
    mismos claims de nameidentifier/role/email).
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": "http://localhost",
        "aud": "http://localhost",
        "iat": now,
        "exp": now + ttl,
        NAMEID_URI: user_id,
        ROLE_URI: "Administrador",
        EMAIL_URI: email,
        "BusinessId": "biz-test",
    }
    h = b64url(json.dumps(header, separators=(",", ":")).encode())
    p = b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64url(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def extract_jwt(value) -> str | None:
    """Busca recursivamente un string que parezca un JWT (3 partes, empieza eyJ)."""
    if isinstance(value, str) and value.count(".") == 2 and value.startswith("eyJ"):
        return value
    if isinstance(value, dict):
        for v in value.values():
            found = extract_jwt(v)
            if found:
                return found
    if isinstance(value, list):
        for v in value:
            found = extract_jwt(v)
            if found:
                return found
    return None


def request(base: str, method: str, path: str, token: str | None = None,
            body=None, headers: dict | None = None, timeout: int = 30):
    """HTTP helper con stdlib. Devuelve (status, headers, parsed_body)."""
    url = base.rstrip("/") + path
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if "json" in resp.headers.get("Content-Type", ""):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
            else:
                parsed = raw
            return resp.status, resp.headers, parsed
    except urllib.error.HTTPError as e:
        raw = e.read()
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.decode(errors="replace")
        return e.code, e.headers, parsed
    except urllib.error.URLError as e:
        raise RuntimeError(f"no se pudo conectar a {url}: {e.reason}") from e


def poll_job(base: str, token: str, job_id: str, timeout_s: int, label: str) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st, _, data = request(base, "GET", f"/api/status/{job_id}", token=token)
        if st != 200 or not isinstance(data, dict):
            raise RuntimeError(f"status endpoint devolvió {st}: {data}")
        status = data.get("status")
        print(f"    [{label}] job {job_id}: {status}")
        if status == "complete":
            return
        if status == "failed":
            raise RuntimeError(f"job {job_id} falló: {data.get('error', data)}")
        time.sleep(3)
    raise RuntimeError(f"timeout ({timeout_s}s) esperando job {job_id}")


def step_run(name: str, fn) -> None:
    print(f"\n▶ PASO {name}")
    try:
        fn()
        print(f"  {PASS} {name} OK")
    except Exception as e:  # noqa: BLE001 — el script reporta y sale
        print(f"  {FAIL} {name}: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pasos
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Recorre el circuito de CancionesPersonalizadas sin pagar.")
    ap.add_argument("--base-url", default=None, help="Base URL del backend CP (default: localhost:8001)")
    ap.add_argument("--steps", default=",".join(ALL_STEPS),
                    help="Pasos a correr separados por coma. Todos: " + ",".join(ALL_STEPS))
    ap.add_argument("--recipient", default="Cliente de Prueba", help="Nombre del destinatario de la canción")
    ap.add_argument("--user-id", default="user-test-1", help="user_id para el JWT de prueba acuñado")
    ap.add_argument("--email", default=None, help="Login real POSBackend: email")
    ap.add_argument("--password", default=None, help="Login real POSBackend: password")
    ap.add_argument("--token", default=None, help="Usar un JWT existente en vez de acuñar/login")
    ap.add_argument("--front-url", default="https://poscuentascorrientes-stage.up.railway.app",
                    help="URL del front para el link de preview (default: staging)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    env = load_env(repo_root / ".env")

    secret = env.get("JWT_SHARED_SECRET", "")
    webhook_secret = env.get("PAYMENT_WEBHOOK_SECRET", "")
    if not secret:
        print("❌ Falta JWT_SHARED_SECRET en .env — el token de prueba no se puede acuñar.")
        sys.exit(1)
    if not webhook_secret:
        print("❌ Falta PAYMENT_WEBHOOK_SECRET en .env — el webhook de pago no se puede simular.")
        sys.exit(1)

    base = args.base_url or "http://localhost:8001"
    gateway = env.get("PAYMENT_GATEWAY_URL", "https://posbackend-staging.up.railway.app")

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        print(f"❌ Pasos desconocidos: {unknown}. Válidos: {ALL_STEPS}")
        sys.exit(1)

    token = args.token
    project_id: str | None = None
    final_job_id: str | None = None

    print(f"Backend CP : {base}")
    print(f"POSBackend : {gateway}")

    # ---- login ------------------------------------------------------------
    if "login" in steps:
        def do_login() -> None:
            nonlocal token
            if args.email and args.password:
                print(f"  Login real contra POSBackend ({args.email})...")
                st, _, data = request(gateway, "POST", "/api/Auth/Login?authType=Interno",
                                      body={"email": args.email, "password": args.password})
                token = extract_jwt(data)
                if not token:
                    raise RuntimeError(f"POSBackend no devolvió JWT ({st}): {data}")
                print("  JWT real obtenido de POSBackend.")
            else:
                if args.token:
                    raise RuntimeError("--token ya viene dado; no acuñar.")
                token = mint_jwt(secret, args.user_id)
                print(f"  JWT de prueba acuñado (user_id={args.user_id}) — simula el token de POSBackend.")
            # Prueba: el backend acepta el token
            st, _, data = request(base, "GET", "/api/projects/mine", token=token)
            if st != 200:
                raise RuntimeError(f"el backend rechazó el token ({st}): {data}")
            count = len(data) if isinstance(data, list) else "?"
            print(f"  GET /api/projects/mine con token -> 200 ({count} proyectos del usuario).")
            # Prueba: sin token -> 401
            st, _, _ = request(base, "GET", "/api/projects/mine")
            if st != 401:
                raise RuntimeError(f"esperaba 401 sin token, obtuve {st}")
            print("  GET /api/projects/mine sin token -> 401 (el token es la puerta).")

        step_run("login", do_login)

    # ---- create -----------------------------------------------------------
    if "create" in steps:
        def do_create() -> None:
            nonlocal project_id
            body = {
                "recipient": args.recipient,
                "relationship": "pareja",
                "genre": "balada romántica",
                "mood": "romántico",
                "voice": "female",
            }
            st, _, data = request(base, "POST", "/api/projects", token=token, body=body)
            if st != 201:
                raise RuntimeError(f"create devolvió {st}: {data}")
            project_id = data.get("id")
            print(f"  Proyecto creado: id={project_id} status={data.get('status')} (linkeado al user {args.user_id})")

        step_run("create", do_create)

    # ---- ownership --------------------------------------------------------
    if "ownership" in steps and project_id:
        def do_ownership() -> None:
            st, _, data = request(base, "GET", f"/api/projects/{project_id}", token=token)
            if st != 200:
                raise RuntimeError(f"owner con su token devolvió {st}: {data}")
            print(f"  GET proyecto con token del dueño -> 200 ({data.get('recipient')}).")
            other = mint_jwt(secret, "user-test-2")
            st, _, _ = request(base, "GET", f"/api/projects/{project_id}", token=other)
            if st != 403:
                raise RuntimeError(f"esperaba 403 con otro usuario, obtuve {st}")
            print("  GET proyecto con OTRO usuario -> 403 project_forbidden.")
            st, _, _ = request(base, "GET", f"/api/projects/{project_id}")
            if st != 401:
                raise RuntimeError(f"esperaba 401 sin token, obtuve {st}")
            print("  GET proyecto SIN token -> 401 unauthorized.")

        step_run("ownership", do_ownership)

    # ---- fragments --------------------------------------------------------
    if "fragments" in steps and project_id:
        def do_fragments() -> None:
            body = {"fragments": [
                "Nos conocimos un verano en la costa y no paramos de reír.",
                "Cada viaje que hicimos se convirtió en nuestra canción.",
                "Este tema es para recordar que siempre vamos a elegirnos.",
            ]}
            st, _, data = request(base, "PUT", f"/api/projects/{project_id}/fragments",
                                  token=token, body=body)
            if st != 200:
                raise RuntimeError(f"fragments devolvió {st}: {data}")
            print(f"  3 fragments cargados (n={len(data.get('fragments', []))}).")

        step_run("fragments", do_fragments)

    # ---- gate -------------------------------------------------------------
    if "gate" in steps and project_id:
        def do_gate() -> None:
            st, _, data = request(base, "POST", f"/api/projects/{project_id}/final", token=token)
            if st != 402:
                raise RuntimeError(f"esperaba 402 sin pago, obtuve {st}: {data}")
            print(f"  POST /final sin pagar -> 402 payment_required (current_status={data.get('current_status')}).")

        step_run("gate", do_gate)

    # ---- checkout ---------------------------------------------------------
    if "checkout" in steps and project_id:
        def do_checkout() -> None:
            try:
                st, _, data = request(base, "POST", f"/api/projects/{project_id}/checkout", token=token)
            except RuntimeError as e:
                print(f"  ⚠️  checkout no se pudo ejecutar ({e}) — seguimos, el pago se simula por webhook.")
                return
            if st != 200:
                print(f"  ⚠️  checkout devolvió {st} ({data}) — seguimos igual (no es fatal).")
                return
            print(f"  Preference MP creada: preference_id={data.get('preference_id')}")
            print(f"  init_point={data.get('init_point')}")
            print("  (Solo creó la preference — NO se cobró nada.)")

        step_run("checkout", do_checkout)

    # ---- pay --------------------------------------------------------------
    if "pay" in steps and project_id:
        def do_pay() -> None:
            body = {
                "project_id": project_id,
                "payment_id": f"test-payment-{int(time.time())}",
                "status": "approved",
                "metadata": {"simulated": "true"},
            }
            st, _, data = request(base, "POST", "/api/webhooks/payment-confirmed",
                                  headers={"X-Webhook-Secret": webhook_secret}, body=body)
            if st != 200:
                raise RuntimeError(f"webhook devolvió {st}: {data}")
            print(f"  Webhook de pago disparado -> {data.get('message')}.")
            print("  💸 PAGO SIMULADO — no se pagó nada.")

        step_run("pay", do_pay)

    # ---- final ------------------------------------------------------------
    if "final" in steps and project_id:
        def do_final() -> None:
            nonlocal final_job_id
            st, _, data = request(base, "POST", f"/api/projects/{project_id}/final", token=token)
            if st != 202:
                raise RuntimeError(f"final devolvió {st}: {data}")
            final_job_id = data.get("job_id")
            print(f"  Job final creado: {final_job_id} (est. {data.get('estimated_total_seconds')}s)")
            poll_job(base, token, final_job_id, timeout_s=600, label="final")

        step_run("final", do_final)

    # ---- stream -----------------------------------------------------------
    if "stream" in steps and final_job_id:
        def do_stream() -> None:
            st, headers, raw = request(base, "GET", f"/api/stream/{final_job_id}", token=token, timeout=60)
            if st != 200:
                raise RuntimeError(f"stream completo devolvió {st}")
            size = len(raw)
            print(f"  GET /api/stream/{final_job_id} -> 200 audio/mpeg ({size} bytes) "
                  f"X-Paid-Content={headers.get('X-Paid-Content')}")
            st, headers, raw = request(base, "GET", f"/api/stream/{final_job_id}?preview=true",
                                       token=token, timeout=60)
            if st != 206:
                raise RuntimeError(f"stream preview devolvió {st}")
            print(f"  GET /api/stream/{final_job_id}?preview=true -> 206 ({len(raw)} bytes) "
                  f"X-Freemium-Preview={headers.get('X-Freemium-Preview')}")

        step_run("stream", do_stream)

    # ---- resumen ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("CIRCUITO COMPLETADO (pago simulado, sin cobro)")
    print("=" * 60)
    if project_id:
        print(f"Project ID : {project_id}")
        print(f"Front      : {args.front_url.rstrip('/')}/#/canciones/preview/{project_id}")
        if final_job_id:
            print(f"Stream full: {base}/api/stream/{final_job_id}")
            print(f"Stream prev: {base}/api/stream/{final_job_id}?preview=true")


if __name__ == "__main__":
    main()
