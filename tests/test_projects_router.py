"""Tests for app/projects/router.py — Project API endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure test settings for router tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr("app.main._active_requests", 0)


class TestCreateProject:
    """Tests for POST /api/projects."""

    @pytest.mark.asyncio
    async def test_create_project_returns_201(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects should return 201 with project ID."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "female",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert data["status"] == "draft"
            assert "endpoints" in data

    @pytest.mark.asyncio
    async def test_create_project_with_reference_song(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with reference_song should include it."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={
                    "recipient": "María",
                    "relationship": "pareja",
                    "genre": "bachata",
                    "mood": "romántica",
                    "voice": "female",
                    "reference_song": "Bachata Rosa - Juan Luis Guerra",
                },
            )

            assert response.status_code == 201
            data = response.json()
            project_id = data["id"]

            # Check it's stored via GET
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            proj = get_resp.json()
            assert proj["reference_song"] == "Bachata Rosa - Juan Luis Guerra"

    @pytest.mark.asyncio
    async def test_create_project_returns_422_on_invalid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with invalid data should return 422."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={"recipient": ""},
            )
            assert response.status_code == 422


class TestGetProject:
    """Tests for GET /api/projects/{id}."""

    @pytest.mark.asyncio
    async def test_get_project_returns_200(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/projects/{id} should return the project."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create first
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

            # Get it
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert data["id"] == project_id
            assert data["recipient"] == "Carlos"
            assert data["relationship"] == "amigo"
            assert data["genre"] == "salsa"
            assert data["mood"] == "festiva"
            assert data["voice"] == "male"
            assert "fragments" in data
            assert "previews" in data

    @pytest.mark.asyncio
    async def test_get_project_missing_returns_404(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/projects/{missing} should return 404."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/projects/nonexistent-id-12345")
            assert response.status_code == 404


class TestPatchProject:
    """Tests for PATCH /api/projects/{id}."""

    @pytest.mark.asyncio
    async def test_patch_updates_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH /api/projects/{id} should update fields and return project."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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

            # Patch genre and mood
            patch_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"genre": "bachata", "mood": "apasionada"},
            )
            assert patch_resp.status_code == 200
            data = patch_resp.json()
            assert data["genre"] == "bachata"
            assert data["mood"] == "apasionada"

    @pytest.mark.asyncio
    async def test_patch_adds_fragment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH /api/projects/{id} with fragment should accumulate story."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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

            # Add first fragment
            await client.patch(
                f"/api/projects/{project_id}",
                json={"fragment": {"text": "Nuestro primer viaje a la playa"}},
            )

            # Add second fragment
            await client.patch(
                f"/api/projects/{project_id}",
                json={"fragment": {"text": "Esa noche de luna llena"}},
            )

            # Verify fragments accumulated
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert len(data["fragments"]) == 2
            texts = [f["text"] for f in data["fragments"]]
            assert "Nuestro primer viaje a la playa" in texts
            assert "Esa noche de luna llena" in texts

    @pytest.mark.asyncio
    async def test_patch_missing_returns_404(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH /api/projects/{missing} should return 404."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/projects/nonexistent",
                json={"genre": "salsa"},
            )
            assert response.status_code == 404


class TestPreviewEndpoint:
    """Tests for POST /api/projects/{id}/preview."""

    @pytest.mark.asyncio
    async def test_preview_returns_202(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects/{id}/preview should return 202 with job_id."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create project with fragment
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
            project_id = create_resp.json()["id"]

            await client.patch(
                f"/api/projects/{project_id}",
                json={"fragment": {"text": "Nuestro primer viaje"}},
            )

            # Mock project_worker so it doesn't actually run
            with patch("app.projects.project_worker", new_callable=AsyncMock):
                preview_resp = await client.post(
                    f"/api/projects/{project_id}/preview",
                )

            assert preview_resp.status_code == 202
            data = preview_resp.json()
            assert "job_id" in data
            assert data["status"] == "queued"
            assert "endpoints" in data

    @pytest.mark.asyncio
    async def test_preview_no_fragments_returns_400(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects/{id}/preview with 0 fragments should return 400."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
            project_id = create_resp.json()["id"]

            # No fragments added — preview should fail
            preview_resp = await client.post(
                f"/api/projects/{project_id}/preview",
            )

            assert preview_resp.status_code == 400
            assert "no_story_fragments" in preview_resp.text


class TestFinalEndpoint:
    """Tests for POST /api/projects/{id}/final."""

    @pytest.mark.asyncio
    async def test_final_returns_202(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects/{id}/final should return 202 with job_id."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
            project_id = create_resp.json()["id"]

            await client.patch(
                f"/api/projects/{project_id}",
                json={"fragment": {"text": "Una historia de amor"}},
            )

            with patch("app.projects.project_worker", new_callable=AsyncMock):
                final_resp = await client.post(
                    f"/api/projects/{project_id}/final",
                )

            assert final_resp.status_code == 202
            data = final_resp.json()
            assert "job_id" in data
            assert data["status"] == "queued"


class TestIntegration:
    """Full integration test for project flow."""

    @pytest.mark.asyncio
    async def test_full_project_flow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Create project → add fragments → preview → check status."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create project
            create_resp = await client.post(
                "/api/projects",
                json={
                    "recipient": "Test",
                    "relationship": "pareja",
                    "genre": "pop",
                    "mood": "feliz",
                    "voice": "female",
                    "reference_song": "Cancion de Ejemplo",
                },
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            # 2. Add fragment
            frag_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"fragment": {"text": "Un día especial"}},
            )
            assert frag_resp.status_code == 200

            # 3. Get project
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            assert len(get_resp.json()["fragments"]) == 1
            assert get_resp.json()["reference_song"] == "Cancion de Ejemplo"

            # 4. Preview
            with patch("app.projects.project_worker", new_callable=AsyncMock):
                preview_resp = await client.post(
                    f"/api/projects/{project_id}/preview",
                )
            assert preview_resp.status_code == 202

            # 5. Final
            with patch("app.projects.project_worker", new_callable=AsyncMock):
                final_resp = await client.post(
                    f"/api/projects/{project_id}/final",
                )
            assert final_resp.status_code == 202

            # 6. Get project should show previews
            get_after = await client.get(f"/api/projects/{project_id}")
            assert get_after.status_code == 200
            assert len(get_after.json()["previews"]) == 2
