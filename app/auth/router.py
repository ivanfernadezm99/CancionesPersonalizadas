"""Auth-related API endpoints: health check."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.auth import get_jwks_fetcher

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    """Public health check endpoint.

    Returns service status, version, and JWKS connectivity health.
    No authentication required.
    """
    fetcher = get_jwks_fetcher()
    return {
        "status": "ok",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "jwks_healthy": fetcher.healthy,
    }
