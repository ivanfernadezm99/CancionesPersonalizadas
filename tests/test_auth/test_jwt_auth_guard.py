"""Tests for the HS256 JWT auth guard (enable-jwt-auth-guard).

Covers the new symmetric (HS256) verification with shared secret, ASP.NET
long claim-URI mapping, default enforcement, and the payment webhook
exemption.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.config import settings

NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
BUSINESS_CLAIM = "BusinessId"

TEST_SECRET = "test-shared-secret-0123456789abcdef"
TEST_ISSUER = "http://localhost"
TEST_AUDIENCE = "http://localhost"


def make_hs256_token(payload: dict[str, Any], secret: str = TEST_SECRET) -> str:
    """Create an HS256 JWT signed with the shared test secret."""
    claims: dict[str, Any] = {
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        **payload,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
async def guard_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """TestClient with auth enforced and HS256 shared secret configured."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr(settings, "JWT_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", True)
    monkeypatch.setattr(
        settings,
        "JWT_ALLOWED_ROLES",
        {"Administrador", "Cajero", "Supervisor", "Vendedor", "Almacén"},
    )
    monkeypatch.setattr("app.main._active_requests", 0)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _default_claims() -> dict[str, Any]:
    """Standard POSBackend-style claims using ASP.NET URIs."""
    return {
        NAMEID_URI: "user-abc-123",
        ROLE_URI: "Administrador",
        BUSINESS_CLAIM: "biz-001",
    }


async def test_valid_hs256_token_allows_request(
    guard_client: AsyncClient,  # noqa: ARG001
) -> None:
    """A valid HS256 token passes auth and populates request.state."""
    from app.main import app

    captured: dict[str, Any] = {}

    @app.get("/api/_guard_state")
    async def _guard_state(request: Request) -> dict[str, Any]:
        captured["user_id"] = request.state.user_id
        captured["role"] = request.state.role
        captured["business_id"] = request.state.business_id
        return {"ok": True}

    token = make_hs256_token(_default_claims())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/_guard_state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

    assert captured["user_id"] == "user-abc-123"
    assert captured["role"] == "Administrador"
    assert captured["business_id"] == "biz-001"


async def test_missing_token_blocked_when_enforced(
    guard_client: AsyncClient,
) -> None:
    """A protected request without a Bearer token returns 401 when enforced."""
    response = await guard_client.get("/api/admin/test")
    assert response.status_code == 401, response.text
    assert response.json()["error"] == "unauthorized"


async def test_webhook_exempt_from_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/webhooks/payment-confirmed needs no Bearer, only the webhook secret."""
    from app.config import settings as s

    monkeypatch.setattr(s, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setattr(s, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(s, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(s, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(s, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(s, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr(s, "JWT_AUTH_ENFORCED", True)
    monkeypatch.setattr(s, "JWT_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.main._active_requests", 0)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Nonexistent project: 404 project_not_found proves the request reached
        # the webhook handler (auth was bypassed) rather than returning 401.
        response = await client.post(
            "/api/webhooks/payment-confirmed",
            json={"project_id": "missing-project", "payment_id": "p1", "status": "approved"},
            headers={"X-Webhook-Secret": "test-webhook-secret"},
        )
        assert response.status_code == 404, response.text
        assert response.json()["error"] == "project_not_found"


async def test_role_enforcement(
    guard_client: AsyncClient,
) -> None:
    """A token whose role is not allowed returns 403 forbidden_role."""
    claims = _default_claims()
    claims[ROLE_URI] = "RolNoExistente"
    token = make_hs256_token(claims)
    response = await guard_client.get(
        "/api/admin/test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "forbidden_role"
