"""Shared fixtures for Canciones Automáticas integration tests.

Provides test DB, mock OpenClaw (respx), mock LLM providers, sample MP3,
output directory, and FastAPI TestClient with test configuration.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import respx
from httpx import ASGITransport, AsyncClient

# ── DB Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def test_db_path(tmp_path: Path) -> str:
    """Path to a temporary SQLite database."""
    return str(tmp_path / "test.db")


@pytest.fixture
def test_output_dir(tmp_path: Path) -> str:
    """Path to a temporary output directory."""
    out_dir = tmp_path / "output"
    out_dir.mkdir(exist_ok=True)
    return str(out_dir)


# ── Sample Data ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_generate_request() -> dict[str, str]:
    """Standard valid GenerateRequest for tests."""
    return {
        "recipient": "María",
        "relationship": "pareja",
        "occasion": "aniversario",
        "genre": "bachata",
        "mood": "romántica",
        "voice": "female",
    }


@pytest.fixture
def sample_job_id() -> str:
    """A fake job ID for direct DB manipulation tests."""
    return "test-job-0000-0000-000000000001"


# ── Sample MP3 Fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_mp3(tmp_path: Path) -> Path:
    """Create a tiny valid-looking MP3 file for stream tests.

    The file starts with a valid MP3 frame sync header (0xFF 0xFB)
    followed by padding data. This is sufficient for stream/routing tests
    that don't require actual audio decoding.
    """
    mp3_path = tmp_path / "sample.mp3"
    # MP3 frame sync: 0xFF 0xFB (MPEG1, Layer3, no CRC, 128kbps, 44100Hz)
    mp3_path.write_bytes(b"\xff\xfb\x90\x00" + b"X" * 4092)
    return mp3_path


# ── Mock OpenClaw (respx) — NOT started; caller (test_app) enters the context ────


@pytest.fixture
def mock_openclaw() -> respx.MockRouter:
    """Mock OpenClaw endpoints for deterministic music generation.

    Routes:
    - POST /tools/invoke -> task ID
    - GET  /tools/tasks/{task_id} -> completed with download URL
    - GET  download URL -> MP3 bytes

    Returns an unstarted MockRouter — the caller (test_app fixture)
    starts it via ``with mock_openclaw:``.
    """
    router = respx.mock(base_url="http://localhost:18789", assert_all_called=False)

    router.post("/tools/invoke").respond(
        200,
        json={
            "ok": True,
            "result": {
                "details": {
                    "async": True,
                    "status": "started",
                    "task": {"taskId": "task-test-integration"},
                },
            },
        },
    )

    router.get("/tools/tasks/task-test-integration").respond(
        200,
        json={
            "ok": True,
            "result": {
                "status": "completed",
                "result": {"download_url": "http://download.example.com/song.mp3"},
            },
        },
    )

    router.get("http://download.example.com/song.mp3").respond(
        200,
        content=b"\xff\xfb\x90\x00" + b"MP3 data from OpenClaw for integration tests",
    )

    return router


@pytest.fixture
def mock_openclaw_fail_invoke() -> respx.MockRouter:
    """Mock OpenClaw that fails on invoke — for testing failure paths."""
    router = respx.mock(base_url="http://localhost:18789", assert_all_called=False)

    router.post("/tools/invoke").respond(500)

    return router


# ── Mock LLM Providers ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock LLM providers to return deterministic lyrics immediately.

    Patches app.lyrics._build_providers to return a single mock provider
    that always succeeds with a fixed LyricsResult.
    """
    valid_lyrics_json = json.dumps({
        "verses": [
            {
                "number": 1,
                "lines": [
                    "Verso uno línea uno",
                    "Verso uno línea dos",
                    "Verso uno línea tres",
                    "Verso uno línea cuatro",
                ],
            },
            {
                "number": 2,
                "lines": [
                    "Verso dos línea uno",
                    "Verso dos línea dos",
                    "Verso dos línea tres",
                    "Verso dos línea cuatro",
                ],
            },
        ],
        "chorus": {
            "lines": [
                "Coro línea uno",
                "Coro línea dos",
                "Coro línea tres",
                "Coro línea cuatro",
            ],
        },
        "bridge": {
            "lines": [
                "Puente uno",
                "Puente dos",
            ],
        },
        "title_suggestion": "María, Mi Amor Eterno",
    })

    # Parse into a real LyricsResult using the existing utility
    from app.lyrics.providers import _parse_lyrics_json

    result = _parse_lyrics_json(valid_lyrics_json)

    # The provider name gets set on the result when generate() is called,
    # mimicking how real providers set result.provider = self.name
    result.provider = "test-provider"

    mock_provider: Any = MagicMock()
    mock_provider.name = "test-provider"
    mock_provider.generate = AsyncMock(return_value=result)

    monkeypatch.setattr("app.lyrics._build_providers", lambda: [mock_provider])


# ── Test App (FastAPI TestClient) ────────────────────────────────────────────────


@pytest.fixture
async def test_app(
    test_db_path: str,
    test_output_dir: str,
    mock_openclaw: respx.MockRouter,
    mock_llm_providers: None,  # noqa: ARG001 — fixture dependency (patches LLMs)
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """Create a FastAPI TestClient with test configuration.

    Configures:
    - Temporary SQLite database
    - Temporary output directory
    - Mock LLM API key
    - Mock OpenClaw token
    - Known MAX_CONCURRENT_JOBS (5)
    - Resets rate limit counter

    Activates respx mock routing.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", test_db_path)
    monkeypatch.setattr(settings, "OUTPUT_DIR", test_output_dir)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-key-for-integration")
    monkeypatch.setattr(settings, "OPENCLAW_TOKEN", "test-openclaw-token")
    monkeypatch.setattr(settings, "MAX_CONCURRENT_JOBS", 5)

    # Reset rate-limit counter
    monkeypatch.setattr("app.main._active_requests", 0)

    from app.main import app

    transport = ASGITransport(app=app)
    with mock_openclaw:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
