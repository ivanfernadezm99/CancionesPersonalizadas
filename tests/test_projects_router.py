"""Tests for app/projects/router.py — Project API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt


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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with reference_song should strip the artist token."""
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

            # Check it's stored sanitized via GET (RQ-PRJ-01 strip-on-store)
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            proj = get_resp.json()
            assert proj["reference_song"] == "Bachata Rosa"

    @pytest.mark.asyncio
    async def test_create_project_artist_only_returns_422(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with artist-only reference_song should return 422."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app
        from app.tag_sanitizer import ARTIST_REJECTION_MESSAGE

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
                    "reference_song": "Los Palmeras",
                },
            )
            assert response.status_code == 422
            assert ARTIST_REJECTION_MESSAGE in response.text

    @pytest.mark.asyncio
    async def test_create_project_empty_reference_song_accepted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects with empty reference_song should stay valid (RQ-PRJ-01)."""
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
                    "reference_song": "",
                },
            )
            assert response.status_code == 201
            data = response.json()
            get_resp = await client.get(f"/api/projects/{data['id']}")
            assert get_resp.json()["reference_song"] == ""

    @pytest.mark.asyncio
    async def test_patch_strips_artist_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH with 'Song de Artist' reference should strip and store the song."""
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

            patch_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"reference_song": "Bailando de Enrique Iglesias"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["reference_song"] == "Bailando"

    @pytest.mark.asyncio
    async def test_patch_artist_only_returns_422_and_keeps_old_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATCH with artist-only reference returns 422 and does not overwrite."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.main import app
        from app.tag_sanitizer import ARTIST_REJECTION_MESSAGE

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
                    "reference_song": "Bachata Rosa",
                },
            )
            project_id = create_resp.json()["id"]

            patch_resp = await client.patch(
                f"/api/projects/{project_id}",
                json={"reference_song": "La Mona Jiménez"},
            )
            assert patch_resp.status_code == 422
            assert ARTIST_REJECTION_MESSAGE in patch_resp.text

            # Stored value unchanged (RQ-PRJ-02: reject without persisting)
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.json()["reference_song"] == "Bachata Rosa"

    @pytest.mark.asyncio
    async def test_create_project_returns_422_on_invalid(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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


class TestListProjects:
    """Tests for GET /api/projects — list the authenticated user's projects."""

    ASPNET_NAMEID = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
    ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
    SECRET = "test-shared-secret-0123456789abcdef"

    def _token(self, user_id: str) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                self.ASPNET_NAMEID: user_id,
                self.ROLE_URI: "Administrador",
                "BusinessId": "1",
                "iss": "http://localhost",
                "aud": "http://localhost",
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            self.SECRET,
            algorithm="HS256",
        )

    def _configure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", True)
        monkeypatch.setattr(settings, "JWT_SHARED_SECRET", self.SECRET)
        monkeypatch.setattr(settings, "JWT_ISSUER", "")
        monkeypatch.setattr(settings, "JWT_AUDIENCE", "")
        monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
        monkeypatch.setattr("app.main._active_requests", 0)

    @pytest.mark.asyncio
    async def test_list_projects_scoped_to_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/projects returns only the authenticated user's projects."""
        self._configure(tmp_path, monkeypatch)

        from app.main import app

        transport = ASGITransport(app=app)
        hdr_a = {"Authorization": f"Bearer {self._token('user-a')}"}
        hdr_b = {"Authorization": f"Bearer {self._token('user-b')}"}

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # User A creates two projects, user B creates one.
            for _ in range(2):
                r = await client.post(
                    "/api/projects",
                    json={"recipient": "María", "relationship": "pareja"},
                    headers=hdr_a,
                )
                assert r.status_code == 201
            r = await client.post(
                "/api/projects",
                json={"recipient": "Juan", "relationship": "amigo"},
                headers=hdr_b,
            )
            assert r.status_code == 201

            # User A lists → sees only their 2 projects.
            r = await client.get("/api/projects", headers=hdr_a)
            assert r.status_code == 200
            projects = r.json()
            assert len(projects) == 2
            assert all(p["recipient"] == "María" for p in projects)

            # User B lists → sees only their 1 project.
            r = await client.get("/api/projects", headers=hdr_b)
            assert r.status_code == 200
            projects = r.json()
            assert len(projects) == 1
            assert projects[0]["recipient"] == "Juan"

    @pytest.mark.asyncio
    async def test_list_projects_returns_empty_for_new_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/projects returns [] for a user with no projects."""
        self._configure(tmp_path, monkeypatch)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                "/api/projects",
                headers={"Authorization": f"Bearer {self._token('user-nobody')}"},
            )
            assert r.status_code == 200
            assert r.json() == []


class TestMigration:
    """Existing databases must be migrated to add the user_id column."""

    @pytest.mark.asyncio
    async def test_init_schema_adds_user_id_to_existing_db(
        self, tmp_path: Path,
    ) -> None:
        """init_schema must add user_id to a db that already has idea (but not user_id).

        Regression: the user_id ALTER was nested inside the `idea` suppress block,
        so it was skipped whenever the `idea` column already existed.
        """
        import aiosqlite

        from app.projects import store

        db_path = str(tmp_path / "old.db")
        conn = await aiosqlite.connect(db_path)
        await conn.executescript(
            """
            CREATE TABLE projects (
                id              TEXT PRIMARY KEY,
                recipient       TEXT NOT NULL,
                relationship    TEXT NOT NULL,
                genre           TEXT NOT NULL DEFAULT 'balada romántica',
                mood            TEXT NOT NULL DEFAULT 'romántico',
                voice           TEXT NOT NULL DEFAULT 'male',
                reference_song  TEXT,
                reference_description TEXT,
                chaining_enabled INTEGER NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'draft'
                                CHECK(status IN ('draft','preview_ready',
                                                 'payment_pending','paid','completed')),
                paid_at         TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                idea            TEXT
            );
            """
        )
        await conn.commit()
        await conn.close()

        await store.init_schema(db_path)

        conn2 = await aiosqlite.connect(db_path)
        cols = [r[1] for r in await (await conn2.execute("PRAGMA table_info(projects)")).fetchall()]
        await conn2.close()
        assert "user_id" in cols


class TestGetProject:
    """Tests for GET /api/projects/{id}."""

    @pytest.mark.asyncio
    async def test_get_project_returns_200(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/projects/{id}/final should return 202 with job_id when paid."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
        monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", False)
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

            # Mark as paid via webhook
            await client.post(
                "/api/webhooks/payment-confirmed",
                json={
                    "project_id": project_id,
                    "payment_id": "mp-test-001",
                    "status": "approved",
                },
                headers={"X-Webhook-Secret": "test-webhook-secret"},
            )

            with patch("app.projects.project_worker", new_callable=AsyncMock):
                final_resp = await client.post(
                    f"/api/projects/{project_id}/final",
                )

            assert final_resp.status_code == 202
            data = final_resp.json()
            assert "job_id" in data
            assert data["status"] == "queued"


class TestReferenceAudioUrl:
    """GET /api/projects/{id} reference_audio_url contract (RQ-REF-AUDIO-01)."""

    @pytest.mark.asyncio
    async def test_get_project_returns_reference_audio_url_when_stored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET project returns reference_audio_url when the ref audio file exists."""
        from app.config import settings

        output_dir = tmp_path / "output"
        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(output_dir))
        monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://example.com")
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

            # Place a reference audio file on disk for this project (Suno Cover mode)
            ref_dir = output_dir / "ref-audio" / project_id
            ref_dir.mkdir(parents=True, exist_ok=True)
            (ref_dir / "reference.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"X" * 100)

            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["reference_audio_url"] == (
                "https://example.com/api/projects/ref-audio/" + project_id
            )

    @pytest.mark.asyncio
    async def test_get_project_reference_audio_url_null_when_not_stored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET project returns null reference_audio_url when no ref audio file exists."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://example.com")
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

            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["reference_audio_url"] is None


class TestIntegration:
    """Full integration test for project flow."""

    @pytest.mark.asyncio
    async def test_full_project_flow(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Create project → add fragments → preview → pay → final."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
        monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", False)
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
                    "reference_song": "Cancion Ejemplo",
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
            assert get_resp.json()["reference_song"] == "Cancion Ejemplo"

            # 4. Preview
            with patch("app.projects.project_worker", new_callable=AsyncMock):
                preview_resp = await client.post(
                    f"/api/projects/{project_id}/preview",
                )
            assert preview_resp.status_code == 202

            # 5. Pay via webhook
            pay_resp = await client.post(
                "/api/webhooks/payment-confirmed",
                json={
                    "project_id": project_id,
                    "payment_id": "mp-int-001",
                    "status": "approved",
                },
                headers={"X-Webhook-Secret": "test-webhook-secret"},
            )
            assert pay_resp.status_code == 200

            # 6. Final
            with patch("app.projects.project_worker", new_callable=AsyncMock):
                final_resp = await client.post(
                    f"/api/projects/{project_id}/final",
                )
            assert final_resp.status_code == 202

            # 7. Get project should show previews (2: one preview + one final)
            get_after = await client.get(f"/api/projects/{project_id}")
            assert get_after.status_code == 200
            assert len(get_after.json()["previews"]) == 2


class TestUsageStats:
    """GET /api/projects/stats — public counter of previews and full songs."""

    @pytest.mark.asyncio
    async def test_stats_counts_completed_previews_and_songs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Seeded DB returns completed previews/final counts, publicly (no JWT)."""
        from app.config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "stats.db"))
        monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
        monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("app.main._active_requests", 0)

        from app.projects.store import _get_conn, get_usage_stats, init_schema

        db = str(tmp_path / "stats.db")
        now = datetime.now(timezone.utc).isoformat()
        conn = await _get_conn(db)
        await init_schema(db, conn=conn)

        # Projects (once each)
        for pid in ("p1", "p2", "p3"):
            await conn.execute(
                "INSERT INTO projects (id, recipient, relationship, status, created_at, updated_at) "
                "VALUES (?, 'X', 'pareja', 'draft', ?, ?)",
                (pid, now, now),
            )

        # 2 previews (complete) + 1 preview (failed) + 2 finals (complete)
        seeds = [
            ("p1", "j1", "preview", "complete"),
            ("p1", "j2", "final", "complete"),
            ("p2", "j3", "preview", "complete"),
            ("p3", "j4", "preview", "failed"),
            ("p3", "j5", "final", "complete"),
        ]
        for pid, jid, jtype, jstatus in seeds:
            await conn.execute(
                "INSERT INTO jobs (job_id, status, params, progress, metadata, created_at, updated_at, completed_at) "
                "VALUES (?, ?, '{}', 0.0, '{}', ?, ?, ?)",
                (jid, jstatus, now, now, now if jstatus == "complete" else None),
            )
            await conn.execute(
                "INSERT INTO project_jobs (project_id, job_id, job_type, created_at) "
                "VALUES (?, ?, ?, ?)",
                (pid, jid, jtype, now),
            )
        await conn.commit()
        await conn.close()

        # Unit: only completed jobs count.
        stats = await get_usage_stats(db_path=db)
        assert stats == {"previews": 2, "songs": 2}

        # Endpoint is public (no token) and returns the same counts.
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/projects/stats")
            assert resp.status_code == 200
            assert resp.json() == {"previews": 2, "songs": 2}
