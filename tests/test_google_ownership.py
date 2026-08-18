from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt


SECRET = "test-shared-secret-0123456789abcdef"
NAME_ID = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
EMAIL = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"


def token(user_id: str, email: str = "user@example.com", **extra: object) -> str:
    claims: dict[str, object] = {
        NAME_ID: user_id,
        EMAIL: email,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        **extra,
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture
def ownership_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "ownership.db"))
    monkeypatch.setattr(settings, "JWT_SHARED_SECRET", SECRET)
    monkeypatch.setattr(settings, "JWT_AUTH_ENFORCED", True)
    monkeypatch.setattr(settings, "JWT_ISSUER", "")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "")
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("app.main._active_requests", 0)


@pytest.fixture
async def ownership_client(ownership_settings: None) -> AsyncClient:  # noqa: ARG001
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def create_project(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/projects",
        headers=headers,
        json={"recipient": "María", "relationship": "pareja"},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_required_user_dependency_rejects_missing_expired_and_claimless_tokens(
    ownership_client: AsyncClient,
) -> None:
    endpoint = "/api/projects/mine"
    assert (await ownership_client.get(endpoint)).status_code == 401
    expired = token("u1", exp=int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()))
    assert (await ownership_client.get(endpoint, headers={"Authorization": f"Bearer {expired}"})).status_code == 401
    claimless = jwt.encode({"exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}, SECRET, algorithm="HS256")
    assert (await ownership_client.get(endpoint, headers={"Authorization": f"Bearer {claimless}"})).status_code == 401


@pytest.mark.asyncio
async def test_mine_is_newest_first_and_isolated(ownership_client: AsyncClient) -> None:
    u1 = {"Authorization": f"Bearer {token('u1')}"}
    u2 = {"Authorization": f"Bearer {token('u2')}"}
    first = await create_project(ownership_client, u1)
    second = await create_project(ownership_client, u1)
    other = await create_project(ownership_client, u2)

    response = await ownership_client.get("/api/projects/mine", headers=u1)
    assert response.status_code == 200
    assert [project["id"] for project in response.json()] == [second, first]
    assert other not in [project["id"] for project in response.json()]


@pytest.mark.asyncio
async def test_cross_user_project_read_is_forbidden(ownership_client: AsyncClient) -> None:
    owner = {"Authorization": f"Bearer {token('owner')}"}
    stranger = {"Authorization": f"Bearer {token('stranger')}"}
    project_id = await create_project(ownership_client, owner)

    response = await ownership_client.get(f"/api/projects/{project_id}", headers=stranger)
    assert response.status_code == 403
    assert response.json()["error"] == "project_forbidden"


@pytest.mark.asyncio
async def test_checkout_links_unowned_project_and_rejects_email_mismatch(
    ownership_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = {"Authorization": f"Bearer {token('owner', 'owner@example.com')}"}
    project_id = await create_project(ownership_client, owner)
    from app.config import settings
    from app.projects import store
    from app.models import SongProjectUpdate

    await store.update_project(project_id, SongProjectUpdate(user_id=None), db_path=settings.DB_PATH)
    monkeypatch.setattr(settings, "PAYMENT_GATEWAY_URL", "http://gateway")
    monkeypatch.setattr(settings, "SONG_PRICE", 5.0)
    import respx

    with respx.mock(base_url="http://gateway") as mock:
        mock.post("/api/checkout").respond(200, json={"preference_id": "p", "init_point": "https://pay"})
        response = await ownership_client.post(f"/api/projects/{project_id}/checkout", headers=owner)
    assert response.status_code == 200
    project = await store.get_project(project_id, db_path=settings.DB_PATH)
    assert project is not None and project["user_id"] == "owner"

    mismatch = {"Authorization": f"Bearer {token('other', 'other@example.com')}"}
    response = await ownership_client.post(f"/api/projects/{project_id}/checkout", headers=mismatch)
    assert response.status_code == 403
