"""Tests for Cloudflare Turnstile verification."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.auth.turnstile import verify_turnstile


@pytest.fixture()
def app_with_turnstile():
    """App with Turnstile-protected endpoint."""
    app = FastAPI()

    @app.post("/test-preview")
    async def test_preview(request: Request):
        token = await verify_turnstile(request)
        return {"token": token, "verified": True}

    return app


@pytest.fixture()
def client(app_with_turnstile):
    return TestClient(app_with_turnstile)


class TestTurnstileVerification:
    """Tests for verify_turnstile dependency."""

    @patch("app.auth.turnstile.settings")
    def test_disabled_when_no_secret(self, mock_settings, client):
        """When TURNSTILE_SECRET_KEY is empty, skip verification entirely."""
        mock_settings.TURNSTILE_SECRET_KEY = ""
        response = client.post(
            "/test-preview",
            json={"some_field": "value"},
        )
        assert response.status_code == 200
        assert response.json()["token"] is None
        assert response.json()["verified"] is True

    @patch("app.auth.turnstile.settings")
    def test_missing_token_returns_400(self, mock_settings, client):
        """When Turnstile is configured but no token sent, return 400."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        response = client.post(
            "/test-preview",
            json={"some_field": "value"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "turnstile_required"

    @patch("app.auth.turnstile.settings")
    def test_invalid_json_body_returns_400(self, mock_settings, client):
        """Non-JSON body returns 400."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        response = client.post(
            "/test-preview",
            content="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 400

    @patch("app.auth.turnstile.settings")
    def test_empty_body_returns_400(self, mock_settings, client):
        """Empty JSON body (no turnstile_token field) returns 400."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        response = client.post("/test-preview", json={})
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "turnstile_required"

    @patch("app.auth.turnstile.httpx.AsyncClient")
    @patch("app.auth.turnstile.settings")
    def test_successful_verification(self, mock_settings, mock_client_cls, client):
        """Valid token is verified successfully with Cloudflare."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        mock_settings.TURNSTILE_SITE_KEY = "test-site-key"

        # Mock Cloudflare response — httpx .json() is sync
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        response = client.post(
            "/test-preview",
            json={"turnstile_token": "valid-token-abc"},
        )
        assert response.status_code == 200
        assert response.json()["token"] == "valid-token-abc"

    @patch("app.auth.turnstile.httpx.AsyncClient")
    @patch("app.auth.turnstile.settings")
    def test_cloudflare_rejects_token(self, mock_settings, mock_client_cls, client):
        """Cloudflare returns success:false for invalid token."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        mock_settings.TURNSTILE_SITE_KEY = "test-site-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error-codes": ["invalid-input-response"],
        }
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        response = client.post(
            "/test-preview",
            json={"turnstile_token": "bad-token"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "turnstile_invalid"

    @patch("app.auth.turnstile.httpx.AsyncClient")
    @patch("app.auth.turnstile.settings")
    def test_cloudflare_request_fails(self, mock_settings, mock_client_cls, client):
        """Network failure during Cloudflare verification returns 502."""
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret-key"
        mock_settings.TURNSTILE_SITE_KEY = "test-site-key"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = Exception("Connection timeout")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        response = client.post(
            "/test-preview",
            json={"turnstile_token": "token-abc"},
        )
        assert response.status_code == 502
        assert response.json()["detail"]["error"] == "turnstile_verification_failed"
