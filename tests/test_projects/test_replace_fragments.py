"""Tests for PUT /api/projects/{id}/fragments — replace story fragments.

Covers:
- Replacing the full fragment list on a draft project (200, exact match)
- Rejecting replacement once a project is paid (409 Conflict)
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
    async def test_replace_fragments_paid_project_409(
        self, replace_client: AsyncClient,
    ) -> None:
        """PUT fragments on a paid project should return 409 Conflict."""
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
            json={"fragments": ["no debería poder cambiarse"]},
        )
        assert resp.status_code == 409, resp.text

        # Fragments should remain untouched.
        get_after = await replace_client.get(f"/api/projects/{project_id}")
        assert get_after.status_code == 200
        assert get_after.json()["fragments"] == []
