"""Tests for the optional `idea` field on song projects (RQ-IDEA-01).

Covers:
- Create with idea persists and is returned by GET (201 + stored)
- Create without idea stores null by default
- PATCH updates idea (200 + GET returns updated)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_create_with_idea_persists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/projects with idea should store and return it (RQ-IDEA-01)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.post(
            "/api/projects",
            json={
                "recipient": "María",
                "relationship": "pareja",
                "genre": "bachata",
                "mood": "romántica",
                "voice": "female",
                "idea": "canción para mi esposa",
            },
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["idea"] == "canción para mi esposa"


@pytest.mark.asyncio
async def test_create_without_idea_stores_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/projects without idea should store null (RQ-IDEA-01 scenario)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.post(
            "/api/projects",
            json={
                "recipient": "Carlos",
                "relationship": "amigo",
                "genre": "salsa",
                "mood": "festiva",
                "voice": "male",
            },
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["idea"] is None


@pytest.mark.asyncio
async def test_patch_updates_idea(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /api/projects/{id} with idea should update and return it (RQ-IDEA-01)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        create_resp = await client.post(
            "/api/projects",
            json={
                "recipient": "Lucía",
                "relationship": "pareja",
                "genre": "balada",
                "mood": "romántica",
                "voice": "female",
            },
        )
        project_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/projects/{project_id}",
            json={"idea": "nueva idea de agradecimiento"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["idea"] == "nueva idea de agradecimiento"

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["idea"] == "nueva idea de agradecimiento"
