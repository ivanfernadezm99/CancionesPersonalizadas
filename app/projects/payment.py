"""Payment endpoints: checkout proxy and webhook handler.

Provides:
- create_checkout(project_id) — proxy checkout to POSBackend (called by projects router)
- POST /api/webhooks/payment-confirmed — receive payment confirmation webhook
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings
from app.models import CheckoutResponse, PaymentConfirmRequest, WebhookResponse
from app.projects import store

# Webhook router — standalone, not under /api/projects
webhook_router = APIRouter()


async def create_checkout(project_id: str) -> CheckoutResponse:
    """Create a Mercado Pago checkout preference via POSBackend proxy.

    Builds a payment payload with project info and configured SONG_PRICE,
    sends it to the configured PAYMENT_GATEWAY_URL, and returns the
    Mercado Pago preference_id and init_point to the frontend.

    Returns 503 if the payment gateway is unreachable.
    """
    # Verify project exists
    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": project_id},
        )

    payload = {
        "project_id": project_id,
        "amount": settings.SONG_PRICE,
        "currency": "ARS",
        "description": f"Personalized song for {project.get('recipient', 'unknown')}",
        "success_url": (
            f"{settings.PUBLIC_BASE_URL}/payment/success?project_id={project_id}"
            if settings.PUBLIC_BASE_URL
            else ""
        ),
        "failure_url": (
            f"{settings.PUBLIC_BASE_URL}/payment/failure?project_id={project_id}"
            if settings.PUBLIC_BASE_URL
            else ""
        ),
    }

    gateway_url = settings.PAYMENT_GATEWAY_URL.rstrip("/")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{gateway_url}/api/checkout",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "payment_gateway_unavailable"},
            )

    # Update project status to payment_pending
    await store.update_project_status(
        project_id,
        "payment_pending",
        db_path=settings.DB_PATH,
    )

    return CheckoutResponse(
        preference_id=data.get("preference_id", ""),
        init_point=data.get("init_point", ""),
        project_id=project_id,
        amount=settings.SONG_PRICE,
    )


@webhook_router.post(
    "/api/webhooks/payment-confirmed",
    response_model=WebhookResponse,
)
async def payment_confirmed_webhook(
    body: PaymentConfirmRequest,
    x_webhook_secret: str = Header(...),
) -> WebhookResponse:
    """Handle payment confirmation webhook from POSBackend.

    Requires X-Webhook-Secret header matching PAYMENT_WEBHOOK_SECRET.
    Transitions project status to 'paid' and sets paid_at timestamp.
    Idempotent: returns 200 with message='already_paid' if already paid.
    """
    # Validate shared secret
    if x_webhook_secret != settings.PAYMENT_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_webhook_secret"},
        )

    # Check project exists
    project = await store.get_project(body.project_id, db_path=settings.DB_PATH)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "project_not_found", "project_id": body.project_id},
        )

    # Idempotent: already paid
    if project["status"] == "paid":
        return WebhookResponse(success=True, message="already_paid")

    # Transition to paid
    paid_at = datetime.now(timezone.utc).isoformat()
    await store.update_project_status(
        body.project_id,
        "paid",
        paid_at=paid_at,
        db_path=settings.DB_PATH,
    )

    return WebhookResponse(success=True, message="payment_confirmed")
