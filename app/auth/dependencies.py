"""FastAPI dependencies for role-based access control."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def requires_role(*allowed_roles: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that restricts endpoint access to specific roles.

    Usage::

        @router.get("/api/admin")
        @requires_role(1, 2)
        async def admin_endpoint(request: Request):
            ...

    The decorator checks ``request.state.role_id`` (set by the JWT middleware)
    and raises 403 if the role is not in ``allowed_roles``.

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

            role_id = getattr(request.state, "role_id", 0)
            if role_id not in allowed_roles:
                logger.warning(
                    "Role %s not in allowed roles %s for %s",
                    role_id,
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
