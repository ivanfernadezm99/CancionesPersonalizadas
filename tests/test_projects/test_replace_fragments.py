"""Tests for PUT /api/projects/{id}/fragments — replace story fragments.

Covers:
- Replacing the full fragment list on a draft project (200, exact match)
- Replacing fragments on a paid project WITHOUT a final song yet (200)
- Rejecting replacement once a final song exists (409 Conflict)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def replace_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure test settings for replace-fragments tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", False)
    monkeypatch.setattr("app.main._active_requests", 0)


@pytest.fixture
async def replace_client(replace_settings: None) -> AsyncClient:  # noqa: ARG001
    """Create a test client with replace-fragments settings configured."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_project(client: AsyncClient) -> str:
    """Helper: create a basic project. Returns project_id."""
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
    return create_resp.json()["id"]


class TestReplaceFragments:
    """Tests for PUT /api/projects/{id}/fragments."""

    @pytest.mark.asyncio
    async def test_replace_fragments_success(
        self, replace_client: AsyncClient,
    ) -> None:
        """PUT fragment list should return 200 and GET reflects the exact new list."""
        project_id = await _create_project(replace_client)

        # Seed an initial fragment so we prove replacement (not append).
        await replace_client.patch(
            f"/api/projects/{project_id}",
            json={"fragment": {"text": "Fragmento original"}},
        )

        new_fragments = [
            "Primer fragmento nuevo",
            "Segundo fragmento nuevo",
            "Tercer fragmento nuevo",
        ]

        resp = await replace_client.put(
            f"/api/projects/{project_id}/fragments",
            json={"fragments": new_fragments},
        )
        assert resp.status_code == 200, resp.text

        # GET should return exactly the new fragments, in order.
        get_resp = await replace_client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        texts = [f["text"] for f in data["fragments"]]
        assert texts == new_fragments

    @pytest.mark.asyncio
    async def test_replace_fragments_paid_without_final_allowed(
        self, replace_client: AsyncClient,
    ) -> None:
        """PUT fragments on a paid project with no final song yet → 200.

        A paid project that still only has a 30s preview remains editable so
        the user can tweak the lyrics before converting to the full song.
        """
        project_id = await _create_project(replace_client)

        # Mark the project as paid directly via the store.
        from app.config import settings
        from app.projects import store

        found = await store.update_project_status(
            project_id, "paid", db_path=settings.DB_PATH,
        )
        assert found is True

        # Verify status is paid before attempting the replacement.
        get_resp = await replace_client.get(f"/api/projects/{project_id}")
        assert get_resp.json()["status"] == "paid"

        resp = await replace_client.put(
            f"/api/projects/{project_id}/fragments",
            json={"fragments": ["letra ajustada antes de la final"]},
        )
        assert resp.status_code == 200, resp.text

        # New fragments should be persisted.
        get_after = await replace_client.get(f"/api/projects/{project_id}")
        assert get_after.status_code == 200
        texts = [f["text"] for f in get_after.json()["fragments"]]
        assert texts == ["letra ajustada antes de la final"]

    @pytest.mark.asyncio
    async def test_replace_fragments_with_complete_final_409(
        self, replace_client: AsyncClient,
    ) -> None:
        """PUT fragments on a project with a complete final job → 409."""
        project_id = await _create_project(replace_client)

        from app.config import settings
        from app.projects import store
        from app.jobs import create_job, update_status
        from app.models import GenerateRequest

        # Mark the project as paid + link a complete final job.
        found = await store.update_project_status(
            project_id, "paid", db_path=settings.DB_PATH,
        )
        assert found is True

        final_job_id = await create_job(
            GenerateRequest(
                recipient="María",
                relationship="pareja",
                occasion="personalizada",
                genre="bachata",
                mood="romántica",
            ),
            db_path=settings.DB_PATH,
        )
        await store.link_project_job(
            project_id, final_job_id, "final", db_path=settings.DB_PATH,
        )
        # Walk the state machine to reach complete.
        for step in ("lyrics_generating", "music_generating", "processing", "complete"):
            await update_status(final_job_id, step, db_path=settings.DB_PATH)

        resp = await replace_client.put(
            f"/api/projects/{project_id}/fragments",
            json={"fragments": ["no debería poder cambiarse"]},
        )
        assert resp.status_code == 409, resp.text

        # Fragments should remain untouched.
        get_after = await replace_client.get(f"/api/projects/{project_id}")
        assert get_after.status_code == 200
        assert get_after.json()["fragments"] == []
