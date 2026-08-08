"""Tests for POST /api/projects/{id}/lyrics-draft (RQ-DRAFT-01..03).

Covers:
- Happy path: mock lyrics_generate, occasion='personalizada', story+idea combined
- 404 on unknown project id
- 503 when all LLM providers fail (LyricsGenerationError from generate)
- 503 when the draft has < 10 lines (LyricsGenerationError from normalize_draft)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.lyrics.providers import LyricsGenerationError
from app.models import LyricsResult


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


def _valid_result() -> LyricsResult:
    return LyricsResult(
        verses=[
            {"number": 1, "lines": ["v1 a", "v1 b", "v1 c", "v1 d"]},
            {"number": 2, "lines": ["v2 a", "v2 b", "v2 c", "v2 d"]},
        ],
        chorus={"lines": ["c1", "c2", "c3", "c4"]},
        bridge={"lines": ["b1", "b2"]},
        language="es",
        title_suggestion="Gracias por Todo",
        provider="mock",
    )


def _short_result() -> LyricsResult:
    return LyricsResult(
        verses=[{"number": 1, "lines": ["a", "b", "c"]}],
        chorus={"lines": ["x", "y"]},
        bridge=None,
        language="es",
        title_suggestion="Corta",
        provider="mock",
    )


@pytest.mark.asyncio
async def test_lyrics_draft_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST lyrics-draft should call lyrics_generate with occasion='personalizada'
    and combine story + idea, returning the structured draft (RQ-DRAFT-01/02)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        create_resp = await client.post(
            "/api/projects",
            json={
                "recipient": "María",
                "relationship": "pareja",
                "genre": "bachata",
                "mood": "romántica",
                "voice": "female",
                "idea": "canción de agradecimiento por mi hija",
            },
        )
        project_id = create_resp.json()["id"]
        await client.patch(
            f"/api/projects/{project_id}",
            json={"fragment": {"text": "Un recuerdo especial en la playa"}},
        )

        with patch(
            "app.projects.router.lyrics_generate",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = _valid_result()

            draft_resp = await client.post(
                f"/api/projects/{project_id}/lyrics-draft",
            )

        assert draft_resp.status_code == 200
        data = draft_resp.json()
        assert data["language"] == "es"
        assert len(data["verses"]) == 2
        assert "chorus" in data

        # Verify the generate call mapping (D8/D9)
        _, kwargs = mock_gen.call_args
        assert kwargs["recipient"] == "María"
        assert kwargs["relationship"] == "pareja"
        assert kwargs["occasion"] == "personalizada"
        assert kwargs["genre"] == "bachata"
        assert kwargs["mood"] == "romántica"
        assert "recuerdo especial" in kwargs["story"]
        assert kwargs["idea"] == "canción de agradecimiento por mi hija"


@pytest.mark.asyncio
async def test_lyrics_draft_unknown_project_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST lyrics-draft for a non-existent project should return 404 (RQ-DRAFT-01)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
        resp = await client.post(
            "/api/projects/nonexistent-id/lyrics-draft",
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lyrics_draft_all_providers_fail_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST lyrics-draft when all LLM providers fail should return 503 (RQ-DRAFT-01)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
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

        with patch(
            "app.projects.router.lyrics_generate",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.side_effect = LyricsGenerationError("All LLM providers unavailable")
            resp = await client.post(
                f"/api/projects/{project_id}/lyrics-draft",
            )

        assert resp.status_code == 503
        assert "all llm providers unavailable" in resp.text.lower()


@pytest.mark.asyncio
async def test_lyrics_draft_short_draft_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST lyrics-draft with a <10-line draft should return 503 (RQ-DRAFT-03)."""
    _setup(tmp_path, monkeypatch)
    async with _client() as client:
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

        with patch(
            "app.projects.router.lyrics_generate",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = _short_result()
            resp = await client.post(
                f"/api/projects/{project_id}/lyrics-draft",
            )

        assert resp.status_code == 503
