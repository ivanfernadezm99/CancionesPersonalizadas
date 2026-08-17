"""JWT authentication middleware for FastAPI."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from fastapi import Request, Response, status
from jose import jwt
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# ── Public routes that don't require authentication ───────────────────────────

PUBLIC_ROUTES: set[str] = {
    "/",
    "/api/auth/health",
    "/api/webhooks/payment-confirmed",
}

# Customer-facing routes — no POS JWT required
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/projects",
    "/api/generate",
    "/api/status",
    "/api/stream",
)

# ── ASP.NET claim URIs issued by POSBackend ───────────────────────────────────
# POSBackend (ASP.NET Core) emits NameIdentifier with the xmlsoap.org URI
# (ClaimTypes.NameIdentifier). The schemas.microsoft.com URI is the legacy WIF
# form kept for backward compatibility.

NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
NAMEID_URI_ASPNET = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
BUSINESS_CLAIM = "BusinessId"


class AuthResult(Enum):
    """Result of token validation."""

    OK = "ok"
    MISSING_TOKEN = "missing_token"
    MALFORMED = "malformed"
    EXPIRED = "expired"  # not used separately — JWTError covers all
    BAD_SIGNATURE = "bad_signature"
    JWKS_UNAVAILABLE = "jwks_unavailable"  # deprecated — kept for compat
    FORBIDDEN_ROLE = "forbidden_role"


def _is_public_route(path: str) -> bool:
    """Check if a route is publicly accessible without auth.

    Exact matches for webhooks and health, prefix matches for customer-facing
    endpoints (projects, generation, streaming, Lyria model endpoints).
    """
    return (
        path in PUBLIC_ROUTES
        or path.startswith("/docs")
        or path.startswith("/openapi")
        or any(path.startswith(p) for p in PUBLIC_PREFIXES)
    )


async def _verify_token(token: str) -> tuple[dict[str, Any] | None, AuthResult]:
    """Verify a JWT token and return (claims, result).

    Verifies HS256 signature using the configured shared secret, checking
    issuer, audience, and expiry. Returns ``(None, AuthResult.*)`` on failure.

    When ``JWT_ISSUER``/``JWT_AUDIENCE`` are empty, issuer/audience validation
    is skipped entirely (``verify_iss``/``verify_aud`` off). This is required
    because python-jose rejects any token carrying an ``iss``/``aud`` claim
    when the expected value is ``None`` (e.g. "Invalid audience").
    """
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SHARED_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iat": False,
                "verify_iss": bool(settings.JWT_ISSUER),
                "verify_aud": bool(settings.JWT_AUDIENCE),
            },
            issuer=settings.JWT_ISSUER if settings.JWT_ISSUER else None,
            audience=settings.JWT_AUDIENCE if settings.JWT_AUDIENCE else None,
        )
        return claims, AuthResult.OK
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        return None, AuthResult.BAD_SIGNATURE


async def _reject(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Build a JSON rejection response."""
    logger.warning(
        "Auth rejection: status=%d path=%s detail=%s",
        status_code,
        request.url.path,
        detail,
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": detail},
    )


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that validates JWT Bearer tokens.

    In permissive mode (``JWT_AUTH_ENFORCED=False``), invalid tokens are logged
    but the request is allowed through. In enforced mode, invalid tokens return 401.
    Public routes are never blocked.

    Customer-facing public prefixes (``PUBLIC_PREFIXES``) skip rejection but
    still extract claims when a valid token is present — so logged-in POS
    users retain their identity on those routes while anonymous customers
    can access them freely.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        # Fully public routes — no auth at all (webhook, health, docs)
        if path in PUBLIC_ROUTES or path.startswith("/docs") or path.startswith("/openapi"):
            return await call_next(request)

        # Customer-facing public prefixes — skip rejection, extract claims if present
        is_public_prefix = any(path.startswith(p) for p in PUBLIC_PREFIXES)

        # Extract Authorization header
        auth_header: str = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            if is_public_prefix:
                return await call_next(request)
            if settings.JWT_AUTH_ENFORCED:
                return await _reject(request, status.HTTP_401_UNAUTHORIZED, "unauthorized")
            logger.warning("Missing Bearer token (permissive mode)")
            return await call_next(request)

        token = auth_header.removeprefix("Bearer ")

        # Verify token
        claims, result = await _verify_token(token)

        if result == AuthResult.JWKS_UNAVAILABLE:
            if is_public_prefix:
                return await call_next(request)
            return await _reject(
                request,
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "jwks_unavailable",
            )

        if result != AuthResult.OK:
            if is_public_prefix:
                return await call_next(request)
            if settings.JWT_AUTH_ENFORCED:
                return await _reject(request, status.HTTP_401_UNAUTHORIZED, "invalid_token")
            logger.warning("Invalid token (permissive mode)")
            return await call_next(request)

        # Token valid — extract claims into request.state (always, including public prefixes)
        user_id = str(claims.get(NAMEID_URI, "") or claims.get(NAMEID_URI_ASPNET, "") or "")  # type: ignore[union-attr]
        request.state.user_id = user_id
        request.state.role = str(claims.get(ROLE_URI, ""))  # type: ignore[union-attr]
        request.state.business_id = str(claims.get(BUSINESS_CLAIM, ""))  # type: ignore[union-attr]

        # Role enforcement — only on protected (non-public-prefix) routes
        if not is_public_prefix:
            allowed_roles = settings.JWT_ALLOWED_ROLES
            if allowed_roles and request.state.role not in allowed_roles:
                if settings.JWT_AUTH_ENFORCED:
                    return await _reject(
                        request,
                        status.HTTP_403_FORBIDDEN,
                        "forbidden_role",
                    )
                logger.warning("Role %s not in allowed roles (permissive mode)", request.state.role)

        return await call_next(request)
