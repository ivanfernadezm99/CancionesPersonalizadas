"""FastAPI dependencies for role-based access control."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from app.auth.middleware import EMAIL_URI, NAMEID_URI, NAMEID_URI_ASPNET, _verify_token

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> dict[str, str]:
    """Return the validated JWT identity required by ownership-sensitive routes."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    claims, result = await _verify_token(header.removeprefix("Bearer "))
    if claims is None or result.value != "ok":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    user_id = str(claims.get(NAMEID_URI, "") or claims.get(NAMEID_URI_ASPNET, ""))
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_id_required")
    email = str(claims.get(EMAIL_URI, "") or claims.get("email", ""))
    return {"user_id": user_id, "email": email}


def requires_role(*allowed_roles: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that restricts endpoint access to specific roles.

    Usage::

        @router.get("/api/admin")
        @requires_role("Administrador", "Cajero")
        async def admin_endpoint(request: Request):
            ...

    The decorator checks ``request.state.role`` (set by the JWT middleware)
    and raises 403 if the role is not in ``allowed_roles``.

    Roles are DESCRIPTION strings as emitted by POSBackend (e.g. "Administrador"),
    NOT numeric IDs.

    This is a SECONDARY check on top of the base middleware role filtering.
    """

    def decorator(endpoint: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(endpoint)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find the Request in args or kwargs
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")
            if request is None:
                for value in kwargs.values():
                    if isinstance(value, Request):
                        request = value
                        break

            if request is None:
                logger.error("requires_role: no Request found in endpoint arguments")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="internal_error",
                )

            role = getattr(request.state, "role", "")
            if allowed_roles and role not in allowed_roles:
                logger.warning(
                    "Role %s not in allowed roles %s for %s",
                    role,
                    allowed_roles,
                    request.url.path,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="forbidden_role",
                )

            return await endpoint(*args, **kwargs)

        return wrapper

    return decorator
