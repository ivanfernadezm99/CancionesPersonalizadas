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

from app.auth import JWKSFetcher, get_jwks_fetcher
from app.config import settings

logger = logging.getLogger(__name__)

# ── Public routes that don't require authentication ───────────────────────────

PUBLIC_ROUTES: set[str] = {"/", "/api/auth/health"}


class AuthResult(Enum):
    """Result of token validation."""
    OK = "ok"
    MISSING_TOKEN = "missing_token"
    MALFORMED = "malformed"
    EXPIRED = "expired"  # not used separately — JWTError covers all
    BAD_SIGNATURE = "bad_signature"
    JWKS_UNAVAILABLE = "jwks_unavailable"
    FORBIDDEN_ROLE = "forbidden_role"


def _is_public_route(path: str) -> bool:
    """Check if a route is publicly accessible without auth."""
    return path in PUBLIC_ROUTES or path.startswith("/docs") or path.startswith("/openapi")


async def _verify_token(token: str) -> tuple[dict[str, Any] | None, AuthResult]:
    """Verify a JWT token and return (claims, result).

    Returns ``(None, AuthResult.*)`` when validation fails.
    """
    fetcher: JWKSFetcher = get_jwks_fetcher()

    # Decode without verification first to get the kid header
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        logger.warning("Failed to decode JWT header — malformed token")
        return None, AuthResult.MALFORMED

    kid: str | None = unverified_header.get("kid")
    if not kid:
        logger.warning("JWT missing 'kid' header")
        return None, AuthResult.MALFORMED

    # Get the public key from JWKS
    try:
        key = await fetcher.get_public_key(kid)
    except Exception:
        logger.exception("JWKS endpoint unreachable")
        return None, AuthResult.JWKS_UNAVAILABLE

    if key is None:
        logger.warning("No JWKS key found for kid=%s", kid)
        # If JWKS endpoint had an error trying to fetch, report it
        if fetcher._fetch_error:  # type: ignore[attr-defined]  # noqa: SLF001
            return None, AuthResult.JWKS_UNAVAILABLE
        return None, AuthResult.BAD_SIGNATURE

    # Verify signature, expiration, issuer, audience
    try:
        claims = jwt.decode(
            token,
            key,
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
        # Skip auth for public routes
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
            # JWKS endpoint was unreachable — 503 regardless of mode
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

        # Extract claims
        request.state.user_id = str(claims.get("sub", ""))  # type: ignore[union-attr]
        request.state.role_id = int(claims.get("role", 0))  # type: ignore[union-attr]
        request.state.business_id = str(claims.get("business_id", ""))  # type: ignore[union-attr]

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
