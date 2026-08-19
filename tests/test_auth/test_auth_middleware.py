"""Tests for JWT authentication middleware (HS256 shared secret).

Tests are organized by scenario:
- Valid token → 200/404 on protected endpoints
- Expired token → 401
- Malformed/tampered token → 401
- No token → 401
- Role forbidden → 403
- Permissive mode → passthrough
- Public endpoints + webhook → 200 without token
- Public prefixes (customer-facing) → bypass auth
- HS256KeyProvider unit tests
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

from app.auth import HS256KeyProvider

NAMEID_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
BUSINESS_CLAIM = "BusinessId"

TEST_SECRET = "test-shared-secret-0123456789abcdef"


def _create_token(
    *,
    user_id: str = "user-abc-123",
    role: str = "Administrador",
    business_id: str = "biz-001",
    issuer: str = "http://localhost",
    audience: str = "http://localhost",
    expire_offset: int = 3600,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed HS256 JWT for testing."""
    now = datetime.now(timezone.utc)

    claims: dict[str, Any] = {
        NAMEID_URI: user_id,
        ROLE_URI: role,
        BUSINESS_CLAIM: business_id,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expire_offset)).timestamp()),
    }
    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(claims, TEST_SECRET, algorithm="HS256")


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    enforced: bool,
) -> None:
    """Apply shared test settings + JWT config for the test app."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "JWT_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "JWT_ISSUER", "http://localhost")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "http://localhost")
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", enforced)
    monkeypatch.setattr(
        settings,
        "JWT_ALLOWED_ROLES",
        {"Administrador", "Cajero", "Supervisor"},
    )
    monkeypatch.setattr("app.main._active_requests", 0)


@pytest.fixture
async def auth_test_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """FastAPI TestClient with enforce-mode auth config (HS256)."""
    _configure(monkeypatch, tmp_path, enforced=True)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def permissive_auth_test_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """FastAPI TestClient with JWT_AUTH_ENFORCED=False (HS256)."""
    _configure(monkeypatch, tmp_path, enforced=False)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for GET /api/auth/health — public, no auth needed."""

    @pytest.mark.asyncio
    async def test_health_returns_200(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Health endpoint should return 200 without any token."""
        response = await auth_test_app.get("/api/auth/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0"
        assert "timestamp" in data


class TestRootEndpoint:
    """Tests for GET / — public, no auth needed."""

    @pytest.mark.asyncio
    async def test_root_returns_200(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Root endpoint should return 200 without any token."""
        response = await auth_test_app.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data


class TestValidToken:
    """Tests with a valid HS256 JWT token."""

    @pytest.mark.asyncio
    async def test_valid_token_on_status(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Protected endpoint with valid token should pass auth (returns 404, not 401)."""
        token = _create_token()
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 404 = auth passed (no such route)
        assert response.status_code == 404, (
            f"Expected 404 (auth passed), got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_valid_token_injects_state(
        self, auth_test_app: AsyncClient,  # noqa: ARG002
    ) -> None:
        """Valid token should inject user_id, role, business_id into request.state."""
        from app.main import app

        captured: dict[str, Any] = {}

        @app.get("/api/_test_state")
        async def _test_state(request: Request) -> dict[str, Any]:
            captured["user_id"] = request.state.user_id
            captured["role"] = request.state.role
            captured["business_id"] = request.state.business_id
            return {"ok": True}

        token = _create_token(user_id="test-user", role="Cajero", business_id="biz-xyz")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/_test_state",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
        assert captured["user_id"] == "test-user"
        assert captured["role"] == "Cajero"
        assert captured["business_id"] == "biz-xyz"

    @pytest.mark.asyncio
    async def test_aspnet_nameid_uri_injects_user_id(
        self, auth_test_app: AsyncClient,  # noqa: ARG002
    ) -> None:
        """POSBackend emits NameIdentifier with the xmlsoap.org URI (not WIF)."""
        from app.main import app

        aspnet_nameid = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
        captured: dict[str, Any] = {}

        @app.get("/api/_test_state_aspnet")
        async def _test_state_aspnet(request: Request) -> dict[str, Any]:
            captured["user_id"] = request.state.user_id
            return {"ok": True}

        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                aspnet_nameid: "user-aspnet-1",
                ROLE_URI: "Administrador",
                BUSINESS_CLAIM: "biz-1",
                "iss": "http://localhost",
                "aud": "http://localhost",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            TEST_SECRET,
            algorithm="HS256",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/_test_state_aspnet",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
        assert captured["user_id"] == "user-aspnet-1"


class TestIssuerAudienceDisabled:
    """Issuer/audience validation must be fully skippable when settings are empty."""

    @pytest.mark.asyncio
    async def test_bogus_issuer_audience_accepted_when_disabled(
        self,
        auth_test_app: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A token with arbitrary iss/aud (valid secret) must pass when empty.

        Regression: python-jose raises "Invalid audience" when the token carries
        an ``aud`` claim but the expected audience is ``None``. Emptying the
        settings must disable the check outright, not just pass ``None``.
        """
        from app.config import settings

        monkeypatch.setattr(settings, "JWT_ISSUER", "")
        monkeypatch.setattr(settings, "JWT_AUDIENCE", "")

        token = _create_token(
            issuer="https://some-other-issuer.example",
            audience="some-other-audience",
        )
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 404 = auth passed (no such route), not 401
        assert response.status_code == 404, (
            f"Expected 404 (auth passed with disabled iss/aud), "
            f"got {response.status_code}: {response.text}"
        )


class TestExpiredToken:
    """Tests with an expired JWT token."""

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Expired token should return 401 in enforced mode."""
        token = _create_token(expire_offset=-3600)  # Expired 1 hour ago
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401, response.text


class TestMalformedToken:
    """Tests with malformed/invalid tokens."""

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Malformed token should return 401."""
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": "Bearer this.is.not.a.jwt"},
        )
        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_tampered_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Tampered token (bad sig) should return 401."""
        token = _create_token()
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".badsignature"
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token signed with a different secret should return 401."""
        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            NAMEID_URI: "user-1",
            ROLE_URI: "Administrador",
            "iss": "http://localhost",
            "aud": "http://localhost",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        bad_token = jwt.encode(claims, "a-different-secret", algorithm="HS256")
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert response.status_code == 401, response.text


class TestNoToken:
    """Tests with no Authorization header."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Missing Bearer header should return 401 in enforced mode."""
        response = await auth_test_app.get("/api/admin/test")
        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_wrong_auth_scheme_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Non-Bearer auth scheme should return 401."""
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": "Basic dGVzdDp0ZXN0"},
        )
        assert response.status_code == 401, response.text


class TestRoleForbidden:
    """Tests for role-based access control."""

    @pytest.mark.asyncio
    async def test_forbidden_role_returns_403(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token with a role not in ALLOWED_ROLES should return 403 in enforced mode."""
        token = _create_token(role="RolNoExistente")
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_allowed_role_passes(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token with an allowed role should pass through middleware."""
        token = _create_token(role="Cajero")
        response = await auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, response.text


class TestPermissiveMode:
    """Tests with JWT_AUTH_ENFORCED=False."""

    @pytest.mark.asyncio
    async def test_invalid_token_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, expired tokens should still pass through."""
        token = _create_token(expire_offset=-3600)
        response = await permissive_auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_no_token_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, missing Bearer header should still pass."""
        response = await permissive_auth_test_app.get("/api/admin/test")
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_malformed_token_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, malformed tokens should still pass."""
        response = await permissive_auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_role_forbidden_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, forbidden roles should still pass."""
        token = _create_token(role="RolNoExistente")
        response = await permissive_auth_test_app.get(
            "/api/admin/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, response.text


class TestPublicEndpoints:
    """Public endpoints should always return 200 without a token."""

    @pytest.mark.asyncio
    async def test_health_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """GET /api/auth/health should work without token even in enforced mode."""
        response = await auth_test_app.get("/api/auth/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """GET / should work without token even in enforced mode."""
        response = await auth_test_app.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_voices_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """GET /api/voices is a static registry and must not require a JWT.

        Previously this route 401'd with ``invalid_token`` when the caller held
        an invalid/expired token, spamming the console — the registry is public
        data mirrored in the frontend fallback.
        """
        response = await auth_test_app.get("/api/voices")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert len(payload) > 0



class TestPublicPrefixes:
    """Customer-facing route prefixes bypass JWT auth entirely."""

    @pytest.mark.asyncio
    async def test_projects_list_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """GET /api/projects should return 200 without token (customer flow)."""
        response = await auth_test_app.get("/api/projects")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_projects_create_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """POST /api/projects should work without token (customer creates project)."""
        response = await auth_test_app.post(
            "/api/projects",
            json={
                "recipient": "María",
                "relationship": "esposa",
                "genre": "pop",
                "mood": "romántico",
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_projects_get_by_id_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """GET /api/projects/{id} should work without token (customer preview)."""
        # Create a project first
        create_resp = await auth_test_app.post(
            "/api/projects",
            json={"recipient": "Ana", "relationship": "amiga", "genre": "rock", "mood": "alegre"},
        )
        project_id = create_resp.json()["id"]
        response = await auth_test_app.get(f"/api/projects/{project_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_generate_public(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """POST /api/generate should bypass auth (customer generation flow)."""
        # This will fail with validation (no music provider), but the point is
        # it doesn't return 401
        response = await auth_test_app.post(
            "/api/generate",
            json={"recipient": "Test", "relationship": "amigo", "genre": "pop", "mood": "alegre"},
        )
        assert response.status_code != 401


class TestWebhookExempt:
    """The payment webhook is exempt from JWT auth (uses its own secret)."""

    @pytest.mark.asyncio
    async def test_webhook_requires_no_bearer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Webhook with valid X-Webhook-Secret and no Bearer reaches the handler."""
        from app.config import settings

        _configure(monkeypatch, tmp_path, enforced=True)
        monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/webhooks/payment-confirmed",
                json={"project_id": "missing", "payment_id": "p1", "status": "approved"},
                headers={"X-Webhook-Secret": "test-webhook-secret"},
            )
            # 404 project_not_found proves auth was bypassed (reached handler)
            assert response.status_code == 404, response.text
            assert response.json()["error"] == "project_not_found"

    @pytest.mark.asyncio
    async def test_webhook_invalid_secret_returns_401(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Webhook with wrong X-Webhook-Secret returns 401 invalid_webhook_secret."""
        from app.config import settings

        _configure(monkeypatch, tmp_path, enforced=True)
        monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/webhooks/payment-confirmed",
                json={"project_id": "missing", "payment_id": "p1", "status": "approved"},
                headers={"X-Webhook-Secret": "wrong-secret"},
            )
            assert response.status_code == 401, response.text
            assert response.json()["error"] == "invalid_webhook_secret"


class TestHS256KeyProviderUnit:
    """Unit tests for the HS256KeyProvider class."""

    def test_secret_returns_configured_secret(self) -> None:
        """secret should return the configured shared secret."""
        provider = HS256KeyProvider(secret="abc")
        assert provider.secret == "abc"

    def test_healthy_true_when_secret_configured(self) -> None:
        """healthy should be True when a secret is configured."""
        provider = HS256KeyProvider(secret="abc")
        assert provider.healthy is True

    def test_healthy_false_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """healthy should be False when no secret configured."""
        from app.config import settings

        monkeypatch.setattr(settings, "JWT_SHARED_SECRET", "")
        provider = HS256KeyProvider()
        assert provider.healthy is False
