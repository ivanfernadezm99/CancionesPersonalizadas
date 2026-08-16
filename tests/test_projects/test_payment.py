"""Tests for Phase 3 payment: checkout, webhook, and project gating.

Tests are organized by endpoint/feature:
- Checkout: success (mocked POSBackend), gateway down → 503
- Webhook: valid secret, invalid secret, duplicate (idempotent), project not found
- Final gate: 402 before payment, 202 after payment
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import ASGITransport, AsyncClient

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def payment_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure test settings for payment tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr(settings, "SONG_PRICE", 5.00)
    monkeypatch.setattr(settings, "PAYMENT_GATEWAY_URL", "http://test-gateway")
    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret-123")
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", False)
    monkeypatch.setattr("app.main._active_requests", 0)

    # Reset JWKS fetcher to avoid stale state

    monkeypatch.setattr("app.auth._jwks_fetcher", None)


@pytest.fixture
async def payment_client(payment_settings: None) -> AsyncClient:  # noqa: ARG001
    """Create a test client with payment settings configured."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_project(client: AsyncClient) -> str:
    """Helper: create a basic project and add one story fragment. Returns project_id."""
    create_resp = await client.post(
        "/api/projects",
        json={
            "recipient": "María",
            "relationship": "pareja",
            "genre": "bachata",
            "mood": "romántica",
            "voice": "female",
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Add a story fragment
    await client.patch(
        f"/api/projects/{project_id}",
        json={"fragment": {"text": "Nuestro primer viaje a la playa"}},
    )
    return project_id


# ── Checkout Tests ─────────────────────────────────────────────────────────────


class TestCheckout:
    """Tests for POST /api/projects/{id}/checkout."""

    @pytest.mark.asyncio
    async def test_checkout_success(self, payment_client: AsyncClient) -> None:
        """Checkout should return preference_id and init_point when POSBackend responds."""
        project_id = await _create_project(payment_client)

        with respx.mock(base_url="http://test-gateway") as mock:
            mock.post("/api/checkout").respond(
                200,
                json={
                    "isSuccess": True,
                    "data": {
                        "preference_id": "mp-test-123",
                        "init_point": "https://mercadopago.com/checkout/test",
                    },
                    "totalRecords": None,
                    "message": "Consulta exitosa.",
                    "errors": None,
                },
            )

            resp = await payment_client.post(f"/api/projects/{project_id}/checkout")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["preference_id"] == "mp-test-123"
            assert data["init_point"] == "https://mercadopago.com/checkout/test"
            assert data["project_id"] == project_id
            assert data["amount"] == 5.00

    @pytest.mark.asyncio
    async def test_checkout_success_flat_shape_backward_compat(
        self, payment_client: AsyncClient,
    ) -> None:
        """Checkout should tolerate the flat POSBackend shape for backward compat."""
        project_id = await _create_project(payment_client)

        with respx.mock(base_url="http://test-gateway") as mock:
            mock.post("/api/checkout").respond(
                200,
                json={
                    "preference_id": "mp-flat-456",
                    "init_point": "https://mercadopago.com/checkout/flat",
                },
            )

            resp = await payment_client.post(f"/api/projects/{project_id}/checkout")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["preference_id"] == "mp-flat-456"
            assert data["init_point"] == "https://mercadopago.com/checkout/flat"

    @pytest.mark.asyncio
    async def test_checkout_gateway_down(self, payment_client: AsyncClient) -> None:
        """Checkout should return 503 when POSBackend is unreachable."""
        project_id = await _create_project(payment_client)

        with respx.mock(base_url="http://test-gateway") as mock:
            mock.post("/api/checkout").respond(503)

            resp = await payment_client.post(f"/api/projects/{project_id}/checkout")
            assert resp.status_code == 503, resp.text

    @pytest.mark.asyncio
    async def test_checkout_project_not_found(
        self, payment_client: AsyncClient,
    ) -> None:
        """Checkout should return 404 for unknown project."""
        resp = await payment_client.post("/api/projects/nonexistent/checkout")
        assert resp.status_code == 404, resp.text


# ── Webhook Tests ──────────────────────────────────────────────────────────────


class TestPaymentWebhook:
    """Tests for POST /api/webhooks/payment-confirmed."""

    @pytest.mark.asyncio
    async def test_webhook_valid_secret(self, payment_client: AsyncClient) -> None:
        """Valid webhook should transition project to paid."""
        project_id = await _create_project(payment_client)

        # Check initial status
        get_resp = await payment_client.get(f"/api/projects/{project_id}")
        assert get_resp.json()["status"] == "draft"

        # Send valid webhook
        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret-123"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "payment_confirmed"

        # Verify project status changed to paid
        get_resp = await payment_client.get(f"/api/projects/{project_id}")
        assert get_resp.json()["status"] == "paid"

    @pytest.mark.asyncio
    async def test_webhook_invalid_secret(
        self, payment_client: AsyncClient,
    ) -> None:
        """Webhook with wrong secret should return 401."""
        project_id = await _create_project(payment_client)

        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_webhook_duplicate(self, payment_client: AsyncClient) -> None:
        """Duplicate webhook for already-paid project should return 200 (idempotent)."""
        project_id = await _create_project(payment_client)

        # Pay first
        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret-123"},
        )
        assert resp.status_code == 200

        # Send again
        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-002",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret-123"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "already_paid"

    @pytest.mark.asyncio
    async def test_webhook_project_not_found(
        self, payment_client: AsyncClient,
    ) -> None:
        """Webhook for non-existent project should return 404."""
        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": "nonexistent-id",
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret-123"},
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_webhook_no_secret_header(
        self, payment_client: AsyncClient,
    ) -> None:
        """Webhook without secret header should return 422 (FastAPI validation)."""
        project_id = await _create_project(payment_client)

        resp = await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
        )
        assert resp.status_code == 422, resp.text


# ── Final Gate Tests ───────────────────────────────────────────────────────────


class TestFinalGate:
    """Tests for POST /api/projects/{id}/final payment gating."""

    @pytest.mark.asyncio
    async def test_final_before_payment(self, payment_client: AsyncClient) -> None:
        """Final generation should return 402 if project is not paid."""
        project_id = await _create_project(payment_client)

        with patch("app.projects.project_worker", new_callable=AsyncMock):
            resp = await payment_client.post(f"/api/projects/{project_id}/final")

        assert resp.status_code == 402, resp.text
        data = resp.json()
        assert "payment_required" in str(data.get("error", "")) or "payment" in str(
            data,
        ).lower()

    @pytest.mark.asyncio
    async def test_final_after_payment(self, payment_client: AsyncClient) -> None:
        """Final generation should proceed with 202 if project is paid."""
        project_id = await _create_project(payment_client)

        # Mark as paid via webhook
        await payment_client.post(
            "/api/webhooks/payment-confirmed",
            json={
                "project_id": project_id,
                "payment_id": "mp-pay-001",
                "status": "approved",
            },
            headers={"X-Webhook-Secret": "test-webhook-secret-123"},
        )

        # Verify paid status
        get_resp = await payment_client.get(f"/api/projects/{project_id}")
        assert get_resp.json()["status"] == "paid"

        # Now final should succeed
        with patch("app.projects.project_worker", new_callable=AsyncMock):
            resp = await payment_client.post(f"/api/projects/{project_id}/final")

        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "job_id" in data
