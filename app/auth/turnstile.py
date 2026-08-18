"""Cloudflare Turnstile verification for anti-bot protection."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(request: Request) -> str | None:
    """Verify a Cloudflare Turnstile token from the request body.

    Extracts `turnstile_token` from the JSON body, sends it to Cloudflare
    for verification, and returns the token on success.

    Returns None if TURNSTILE_SECRET_KEY is not configured (disabled mode).

    Raises:
        HTTPException: 400 if token is missing or invalid.
        HTTPException: 502 if Cloudflare verification fails.
    """
    # Skip verification if Turnstile is not configured
    if not settings.TURNSTILE_SECRET_KEY:
        return None

    # Extract token from request body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "message": "Request body must be JSON"},
        ) from None

    token = body.get("turnstile_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "turnstile_required",
                "message": "Cloudflare Turnstile token is required",
            },
        )

    # Verify with Cloudflare
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TURNSTILE_VERIFY_URL,
                data={
                    "secret": settings.TURNSTILE_SECRET_KEY,
                    "response": token,
                    "remoteip": request.client.host if request.client else "",
                },
            )
            result: dict[str, Any] = response.json()
    except Exception as exc:
        logger.error("Turnstile verification request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "turnstile_verification_failed",
                "message": "Could not verify Turnstile token",
            },
        ) from exc

    if not result.get("success"):
        error_codes = result.get("error-codes", [])
        logger.warning("Turnstile verification failed: %s", error_codes)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "turnstile_invalid",
                "message": "Invalid or expired Turnstile token",
                "error_codes": error_codes,
            },
        )

    return token
