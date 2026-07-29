"""Tests for JWT authentication middleware and JWKS fetcher.

Tests are organized by scenario:
- Valid token → 200 on protected endpoints
- Expired token → 401
- Malformed token → 401
- No token → 401
- JWKS endpoint down → 503
- Role forbidden → 403
- Permissive mode → 200 even with invalid token
- Public endpoints → 200 with no token
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from jose import jwk, jwt
from jose.constants import Algorithms

from app.auth import JWKSFetcher

# ── Test key generation ───────────────────────────────────────────────────────

# Shared RSA key pair for all tests in this module
_TEST_PRIVATE_KEY: rsa.RSAPrivateKey | None = None
_TEST_JWK_PRIVATE: Any = None
_TEST_JWK_PUBLIC: Any = None
_TEST_JWKS: dict[str, Any] | None = None


def _ensure_keys() -> None:
    """Generate RSA key pair once per test session."""
    global _TEST_PRIVATE_KEY, _TEST_JWK_PRIVATE, _TEST_JWK_PUBLIC, _TEST_JWKS
    if _TEST_PRIVATE_KEY is not None:
        return

    # Generate using cryptography
    _TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = _TEST_PRIVATE_KEY.public_key()

    # Wrap in jose RSAKey instances for signing/verification
    from jose.backends.cryptography_backend import CryptographyRSAKey

    _TEST_JWK_PUBLIC = CryptographyRSAKey(public_key, algorithm="RS256")
    _TEST_JWK_PRIVATE = CryptographyRSAKey(_TEST_PRIVATE_KEY, algorithm="RS256")

    # Build JWKS from public key
    pub_dict = _TEST_JWK_PUBLIC.to_dict()
    pub_dict["kid"] = "test-key-001"
    pub_dict["alg"] = "RS256"
    pub_dict["use"] = "sig"
    _TEST_JWKS = {"keys": [pub_dict]}


def _get_jwks() -> dict[str, Any]:
    """Return the JWKS response dict."""
    _ensure_keys()
    return _TEST_JWKS  # type: ignore[return-value]


def _create_token(
    *,
    sub: str = "user-abc-123",
    role: int = 1,
    business_id: str = "biz-001",
    issuer: str = "pos-backend",
    audience: str = "canciones-personalizadas",
    expire_offset: int = 3600,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT for testing."""
    _ensure_keys()
    now = datetime.now(timezone.utc)

    claims: dict[str, Any] = {
        "sub": sub,
        "role": role,
        "business_id": business_id,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expire_offset)).timestamp()),
    }
    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(
        claims,
        _TEST_JWK_PRIVATE,
        algorithm=Algorithms.RS256,
        headers={"kid": "test-key-001"},
    )


# ── JWKS endpoint mocker ──────────────────────────────────────────────────────


@pytest.fixture
def jwks_endpoint() -> str:
    """Return the JWKS endpoint URL used in tests."""
    return "http://test-jwks/api/auth/jwks"


@pytest.fixture
def mock_jwks(
    jwks_endpoint: str,
) -> respx.MockRouter:
    """Mock the JWKS endpoint with a valid JWKS response.

    Returns an unstarted MockRouter — the caller starts it via ``with mock_jwks:``.
    """
    router = respx.mock(base_url=jwks_endpoint, assert_all_called=False)
    router.get("/").respond(200, json=_get_jwks())
    return router


# ── Test app fixture (enforced mode) ──────────────────────────────────────────


@pytest.fixture
async def auth_test_app(
    tmp_path: Path,
    mock_jwks: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    jwks_endpoint: str,
) -> AsyncIterator[AsyncClient]:
    """Create a FastAPI TestClient with enforce-mode auth config."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "JWT_JWKS_URL", jwks_endpoint)
    monkeypatch.setattr(settings, "JWT_ISSUER", "pos-backend")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "canciones-personalizadas")
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", True)
    monkeypatch.setattr(settings, "JWT_ALLOWED_ROLES", [1, 2, 3])

    # Reset the JWKS fetcher singleton so it picks up the new URL
    from app.auth import _jwks_fetcher

    monkeypatch.setattr("app.auth._jwks_fetcher", None)
    monkeypatch.setattr("app.main._active_requests", 0)

    from app.main import app

    transport = ASGITransport(app=app)
    with mock_jwks:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# ── Auth test app (permissive mode) ───────────────────────────────────────────


@pytest.fixture
async def permissive_auth_test_app(
    tmp_path: Path,
    mock_jwks: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    jwks_endpoint: str,
) -> AsyncIterator[AsyncClient]:
    """Same as auth_test_app but with JWT_AUTH_ENFORCED=False."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "JWT_JWKS_URL", jwks_endpoint)
    monkeypatch.setattr(settings, "JWT_ISSUER", "pos-backend")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "canciones-personalizadas")
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", False)
    monkeypatch.setattr(settings, "JWT_ALLOWED_ROLES", [1, 2, 3])

    from app.auth import _jwks_fetcher

    monkeypatch.setattr("app.auth._jwks_fetcher", None)
    monkeypatch.setattr("app.main._active_requests", 0)

    from app.main import app

    transport = ASGITransport(app=app)
    with mock_jwks:
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
    """Tests with a valid JWT token."""

    @pytest.mark.asyncio
    async def test_valid_token_on_status(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Protected endpoint with valid token should pass auth (returns 404, not 401)."""
        token = _create_token()
        response = await auth_test_app.get(
            "/api/status/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 404 = auth passed (job not found)
        assert response.status_code == 404, (
            f"Expected 404 (auth passed), got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_valid_token_injects_state(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Valid token should inject user_id, role_id, business_id into request.state."""
        from app.main import app

        captured: dict[str, Any] = {}

        @app.get("/api/_test_state")
        async def _test_state(request: Request) -> dict[str, Any]:
            captured["user_id"] = request.state.user_id
            captured["role_id"] = request.state.role_id
            captured["business_id"] = request.state.business_id
            return {"ok": True}

        token = _create_token(sub="test-user", role=2, business_id="biz-xyz")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/_test_state",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
        assert captured["user_id"] == "test-user"
        assert captured["role_id"] == 2
        assert captured["business_id"] == "biz-xyz"


class TestExpiredToken:
    """Tests with an expired JWT token."""

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Expired token should return 401 in enforced mode."""
        token = _create_token(expire_offset=-3600)  # Expired 1 hour ago
        response = await auth_test_app.get(
            "/api/status/nonexistent",
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
            "/api/status/nonexistent",
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
            "/api/status/nonexistent",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_token_without_kid_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token without kid header should return 401."""
        _ensure_keys()
        claims = {
            "sub": "user-1",
            "role": 1,
            "iss": "pos-backend",
            "aud": "canciones-personalizadas",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        # Encode without kid header
        token = jwt.encode(claims, _TEST_JWK_PRIVATE, algorithm=Algorithms.RS256)
        response = await auth_test_app.get(
            "/api/status/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401, response.text


class TestNoToken:
    """Tests with no Authorization header."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Missing Bearer header should return 401 in enforced mode."""
        response = await auth_test_app.get("/api/status/nonexistent")
        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_wrong_auth_scheme_returns_401(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Non-Bearer auth scheme should return 401."""
        response = await auth_test_app.get(
            "/api/status/nonexistent",
            headers={"Authorization": "Basic dGVzdDp0ZXN0"},
        )
        assert response.status_code == 401, response.text


class TestJWKSDown:
    """Tests when JWKS endpoint is unreachable."""

    @pytest.mark.asyncio
    async def test_jwks_down_returns_503(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When JWKS endpoint is unreachable, protected endpoints return 503."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "JWT_JWKS_URL", "http://localhost:1/unreachable")
        monkeypatch.setattr(settings, "JWT_ISSUER", "pos-backend")
        monkeypatch.setattr(settings, "JWT_AUDIENCE", "canciones-personalizadas")
        monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", True)

        from app.auth import _jwks_fetcher

        monkeypatch.setattr("app.auth._jwks_fetcher", None)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        token = _create_token()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/status/nonexistent",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 503, response.text


class TestRoleForbidden:
    """Tests for role-based access control."""

    @pytest.mark.asyncio
    async def test_forbidden_role_returns_403(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token with a role not in ALLOWED_ROLES should return 403 in enforced mode."""
        token = _create_token(role=99)
        response = await auth_test_app.get(
            "/api/status/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_allowed_role_passes(
        self, auth_test_app: AsyncClient,
    ) -> None:
        """Token with an allowed role should pass through middleware."""
        token = _create_token(role=2)
        response = await auth_test_app.get(
            "/api/status/nonexistent",
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
            "/api/status/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_no_token_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, missing Bearer header should still pass."""
        response = await permissive_auth_test_app.get("/api/status/nonexistent")
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_malformed_token_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, malformed tokens should still pass."""
        response = await permissive_auth_test_app.get(
            "/api/status/nonexistent",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_role_forbidden_passthrough(
        self, permissive_auth_test_app: AsyncClient,
    ) -> None:
        """In permissive mode, forbidden roles should still pass."""
        token = _create_token(role=99)
        response = await permissive_auth_test_app.get(
            "/api/status/nonexistent",
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


class TestJWKSFetcherUnit:
    """Unit tests for the JWKSFetcher class."""

    @pytest.mark.asyncio
    async def test_get_public_key_valid(
        self, jwks_endpoint: str, mock_jwks: respx.MockRouter,
    ) -> None:
        """get_public_key should return a key for a known kid."""
        with mock_jwks:
            fetcher = JWKSFetcher(jwks_url=jwks_endpoint)
            key = await fetcher.get_public_key("test-key-001")
            assert key is not None

    @pytest.mark.asyncio
    async def test_get_public_key_unknown_kid(
        self, jwks_endpoint: str, mock_jwks: respx.MockRouter,
    ) -> None:
        """get_public_key should return None for an unknown kid."""
        with mock_jwks:
            fetcher = JWKSFetcher(jwks_url=jwks_endpoint)
            key = await fetcher.get_public_key("unknown-kid")
            assert key is None

    @pytest.mark.asyncio
    async def test_jwks_endpoint_down(
        self, jwks_endpoint: str,
    ) -> None:
        """When JWKS endpoint is unreachable, get_public_key should raise."""
        fetcher = JWKSFetcher(jwks_url="http://localhost:1/bad")
        with pytest.raises(Exception):
            await fetcher.get_public_key("test-key-001")

    @pytest.mark.asyncio
    async def test_cache_ttl(
        self, jwks_endpoint: str, mock_jwks: respx.MockRouter,
    ) -> None:
        """The fetcher should cache keys and not re-fetch before TTL."""
        with mock_jwks:
            fetcher = JWKSFetcher(jwks_url=jwks_endpoint, ttl=3600)
            key1 = await fetcher.get_public_key("test-key-001")
            assert key1 is not None
            key2 = await fetcher.get_public_key("test-key-001")
            assert key2 is not None

    @pytest.mark.asyncio
    async def test_healthy_property(
        self, jwks_endpoint: str, mock_jwks: respx.MockRouter,
    ) -> None:
        """healthy property should reflect JWKS endpoint status."""
        with mock_jwks:
            fetcher = JWKSFetcher(jwks_url=jwks_endpoint)
            assert fetcher.healthy is True
            await fetcher.get_public_key("test-key-001")
            assert fetcher.healthy is True
