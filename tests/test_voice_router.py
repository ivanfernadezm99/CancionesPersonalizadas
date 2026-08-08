"""Tests for app/voice/router.py — GET /api/voices endpoint and voice validation.

Covers:
- GET /api/voices returns 7 exact {id,label,gender} entries (RQ-VOICE-01)
- es-latino-male present (RQ-VOICE-01 scenario 2)
- 422 on duo/children/unknown voice in create/update/generate (RQ-VOICE-02)
- es-latino-male accepted (RQ-VOICE-02 scenario 3)
- PATCH without voice does NOT 422 (D5)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure test settings for voice router tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr("app.main._active_requests", 0)


def _client() -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_get_voices_returns_seven_exact_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/voices returns the 7 exact {id,label,gender} entries (RQ-VOICE-01)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.get("/api/voices")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 7
        for entry in data:
            assert set(entry.keys()) == {"id", "label", "gender"}


@pytest.mark.asyncio
async def test_get_voices_includes_es_latino_male(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/voices must include es-latino-male (RQ-VOICE-01 scenario 2)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.get("/api/voices")
        ids = {entry["id"] for entry in resp.json()}
        assert "es-latino-male" in ids


@pytest.mark.asyncio
async def test_get_voices_excludes_legacy_duo_and_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/voices must not include duo or children (RQ-VOICE-02)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.get("/api/voices")
        ids = {entry["id"] for entry in resp.json()}
        assert "duo" not in ids
        assert "children" not in ids


@pytest.mark.asyncio
async def test_get_voices_keeps_female_and_male_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/voices must keep exact 'Voz Femenina'/'Voz Masculina' labels (D1)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.get("/api/voices")
        by_id = {entry["id"]: entry for entry in resp.json()}
        assert by_id["female"]["label"] == "Voz Femenina"
        assert by_id["male"]["label"] == "Voz Masculina"


class TestVoiceValidation:
    """Voice field fail-fast validation (RQ-VOICE-02)."""

    @pytest.mark.asyncio
    async def test_create_project_422_on_unknown_voice(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with voice='celebrity_x' must return 422."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "celebrity_x",
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_422_on_legacy_duo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with voice='duo' must return 422 (RQ-VOICE-02)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "duo",
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_422_on_legacy_children(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with voice='children' must return 422 (RQ-VOICE-02)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "children",
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_accepts_es_latino_male(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with voice='es-latino-male' must be accepted (RQ-VOICE-02)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "es-latino-male",
                },
            )
            assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_patch_without_voice_does_not_422(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH /api/projects/{id} without a voice field must NOT 422 (D5)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            create_resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "Carlos",
                    "relationship": "amigo",
                    "genre": "salsa",
                    "mood": "festiva",
                    "voice": "male",
                },
            )
            project_id = create_resp.json()["id"]

            patch_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"genre": "bachata"},
            )
            assert patch_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_update_voice_rejects_unknown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH /api/projects/{id} with voice='duo' must return 422 (RQ-VOICE-02)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            create_resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "Carlos",
                    "relationship": "amigo",
                    "genre": "salsa",
                    "mood": "festiva",
                    "voice": "male",
                },
            )
            project_id = create_resp.json()["id"]

            patch_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"voice": "duo"},
            )
            assert patch_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_422_on_unknown_voice(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/generate with voice='duo' must return 422 (RQ-VOICE-02)."""
        _setup(tmp_path, monkeypatch)
        async with _client() as client:
            resp = await client.post(
                "/api/generate",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "occasion": "aniversario",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "duo",
                },
            )
            assert resp.status_code == 422
