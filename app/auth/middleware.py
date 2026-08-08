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

# ── ASP.NET claim URIs issued by POSBackend ───────────────────────────────────

NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
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

    The webhook path uses exact string match (no regex/prefix matching).
    """
    return path in PUBLIC_ROUTES or path.startswith("/docs") or path.startswith("/openapi")


async def _verify_token(token: str) -> tuple[dict[str, Any] | None, AuthResult]:
    """Verify a JWT token and return (claims, result).

    Verifies HS256 signature using the configured shared secret, checking
    issuer, audience, and expiry. Returns ``(None, AuthResult.*)`` on failure.
    """
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SHARED_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True, "verify_iat": False},
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
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Skip auth for public routes (includes payment webhook)
        if _is_public_route(request.url.path):
            return await call_next(request)

        # Extract Authorization header
        auth_header: str = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            if settings.JWT_AUTH_ENFORCED:
                return await _reject(request, status.HTTP_401_UNAUTHORIZED, "unauthorized")
            logger.warning("Missing Bearer token (permissive mode)")
            return await call_next(request)

        token = auth_header.removeprefix("Bearer ")

        # Verify token
        claims, result = await _verify_token(token)

        if result == AuthResult.JWKS_UNAVAILABLE:
            return await _reject(
                request,
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "jwks_unavailable",
            )

        if result != AuthResult.OK:
            if settings.JWT_AUTH_ENFORCED:
                return await _reject(request, status.HTTP_401_UNAUTHORIZED, "invalid_token")
            logger.warning("Invalid token (permissive mode)")
            return await call_next(request)

        # Extract claims from ASP.NET URIs
        request.state.user_id = str(claims.get(NAMEID_URI, ""))  # type: ignore[union-attr]
        request.state.role_id = int(claims.get(ROLE_URI, 0))  # type: ignore[union-attr]
        request.state.business_id = str(claims.get(BUSINESS_CLAIM, ""))  # type: ignore[union-attr]

        # Role enforcement
        allowed_roles = settings.JWT_ALLOWED_ROLES
        if allowed_roles and request.state.role_id not in allowed_roles:
            if settings.JWT_AUTH_ENFORCED:
                return await _reject(
                    request,
                    status.HTTP_403_FORBIDDEN,
                    "forbidden_role",
                )
            logger.warning("Role %s not in allowed roles (permissive mode)", request.state.role_id)

        return await call_next(request)
