"""Tests for reference_song/reference_description propagation in job_worker.

TDD for SDD change reference-song-style (RQ-RS-02, RQ-RS-03, RQ-RS-04).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.jobs import create_job, get_job
from app.jobs.worker import job_worker
from app.models import GenerateRequest

REF_DESC = "Uplifting pop with warm piano"
REF_SONG = "Coldplay - Yellow"


def make_request(**overrides: Any) -> GenerateRequest:
    """Build a GenerateRequest with default legacy params plus overrides."""
    params = {
        "recipient": "María",
        "relationship": "pareja",
        "occasion": "aniversario",
        "genre": "bachata",
        "mood": "romántica",
        "voice": "female",
        "reference_song": None,
        "reference_description": None,
    }
    params.update(overrides)
    return GenerateRequest(**params)


async def capture_metadata(job_id: str, db_path: str) -> dict[str, Any]:
    """Return the persisted job metadata as a dict."""
    job = await get_job(job_id, db_path=db_path)
    assert job is not None
    return json.loads(job["metadata"])


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "jobs.db")


@pytest.mark.asyncio
async def test_reference_description_propagates_to_lyrics_and_voice(
    db_path: str,
    tmp_path: Path,
) -> None:
    """reference_description should reach lyrics_generate, build_prompt and metadata."""
    from app.config import settings

    original_db = settings.DB_PATH
    original_output = settings.OUTPUT_DIR
    try:
        settings.DB_PATH = db_path
        settings.OUTPUT_DIR = str(tmp_path / "output")

        request = make_request(reference_description=REF_DESC)
        job_id = await create_job(request, db_path=db_path)

        out_dir = Path(settings.OUTPUT_DIR) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.jobs.worker.lyrics_generate", new_callable=AsyncMock) as mock_lyrics,
            patch("app.jobs.worker.build_prompt", return_value="test prompt") as mock_prompt,
            patch("app.jobs.worker.music_generate", new_callable=AsyncMock) as mock_music,
            patch("app.jobs.worker.extend_duration") as mock_extend,
        ):
            from app.models import LyricsResult
            from app.music.durext import ExtendResult

            mock_lyrics.return_value = LyricsResult(
                verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                chorus={"lines": ["e", "f", "g", "h"]},
                title_suggestion="Mi Amor",
                provider="openai",
            )
            mock_music.return_value = out_dir / "generated.mp3"
            (out_dir / "generated.mp3").write_bytes(b"MP3 content")
            mock_extend.return_value = ExtendResult(
                path=out_dir / "final.mp3",
                extended=True,
            )

            await job_worker(job_id)

            _, kwargs = mock_lyrics.call_args
            assert kwargs["reference_description"] == REF_DESC
            # reference_song is None so lyrics fall back to the description
            assert kwargs["reference_song"] == REF_DESC

            _, prompt_kwargs = mock_prompt.call_args
            assert prompt_kwargs["reference_description"] == REF_DESC

            meta = await capture_metadata(job_id, db_path)
            assert meta["reference_description"] == REF_DESC
            assert meta["reference_song"] is None
    finally:
        settings.DB_PATH = original_db
        settings.OUTPUT_DIR = original_output


@pytest.mark.asyncio
async def test_reference_song_only_propagates_to_lyrics_and_metadata(
    db_path: str,
    tmp_path: Path,
) -> None:
    """reference_song (no description) should reach lyrics and metadata only."""
    from app.config import settings

    original_db = settings.DB_PATH
    original_output = settings.OUTPUT_DIR
    try:
        settings.DB_PATH = db_path
        settings.OUTPUT_DIR = str(tmp_path / "output")

        request = make_request(reference_song=REF_SONG)
        job_id = await create_job(request, db_path=db_path)

        out_dir = Path(settings.OUTPUT_DIR) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.jobs.worker.lyrics_generate", new_callable=AsyncMock) as mock_lyrics,
            patch("app.jobs.worker.build_prompt", return_value="test prompt") as mock_prompt,
            patch("app.jobs.worker.music_generate", new_callable=AsyncMock) as mock_music,
            patch("app.jobs.worker.extend_duration") as mock_extend,
        ):
            from app.models import LyricsResult
            from app.music.durext import ExtendResult

            mock_lyrics.return_value = LyricsResult(
                verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                chorus={"lines": ["e", "f", "g", "h"]},
                title_suggestion="Mi Amor",
                provider="openai",
            )
            mock_music.return_value = out_dir / "generated.mp3"
            (out_dir / "generated.mp3").write_bytes(b"MP3 content")
            mock_extend.return_value = ExtendResult(
                path=out_dir / "final.mp3",
                extended=True,
            )

            await job_worker(job_id)

            _, kwargs = mock_lyrics.call_args
            assert kwargs["reference_song"] == REF_SONG
            assert kwargs["reference_description"] is None

            _, prompt_kwargs = mock_prompt.call_args
            assert prompt_kwargs["reference_description"] is None
            assert prompt_kwargs["reference_song"] == REF_SONG

            meta = await capture_metadata(job_id, db_path)
            assert meta["reference_song"] == REF_SONG
            assert meta["reference_description"] is None
    finally:
        settings.DB_PATH = original_db
        settings.OUTPUT_DIR = original_output


@pytest.mark.asyncio
async def test_legacy_request_without_reference_is_backward_compatible(
    db_path: str,
    tmp_path: Path,
) -> None:
    """Legacy request (both None) should behave identically to before the change."""
    from app.config import settings

    original_db = settings.DB_PATH
    original_output = settings.OUTPUT_DIR
    try:
        settings.DB_PATH = db_path
        settings.OUTPUT_DIR = str(tmp_path / "output")

        request = make_request()
        job_id = await create_job(request, db_path=db_path)

        out_dir = Path(settings.OUTPUT_DIR) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.jobs.worker.lyrics_generate", new_callable=AsyncMock) as mock_lyrics,
            patch("app.jobs.worker.build_prompt", return_value="test prompt") as mock_prompt,
            patch("app.jobs.worker.music_generate", new_callable=AsyncMock) as mock_music,
            patch("app.jobs.worker.extend_duration") as mock_extend,
        ):
            from app.models import LyricsResult
            from app.music.durext import ExtendResult

            mock_lyrics.return_value = LyricsResult(
                verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                chorus={"lines": ["e", "f", "g", "h"]},
                title_suggestion="Mi Amor",
                provider="openai",
            )
            mock_music.return_value = out_dir / "generated.mp3"
            (out_dir / "generated.mp3").write_bytes(b"MP3 content")
            mock_extend.return_value = ExtendResult(
                path=out_dir / "final.mp3",
                extended=True,
            )

            await job_worker(job_id)

            _, kwargs = mock_lyrics.call_args
            assert kwargs["reference_song"] is None
            assert kwargs["reference_description"] is None

            _, prompt_kwargs = mock_prompt.call_args
            assert prompt_kwargs["reference_song"] is None
            assert prompt_kwargs["reference_description"] is None

            meta = await capture_metadata(job_id, db_path)
            assert meta["reference_song"] is None
            assert meta["reference_description"] is None
    finally:
        settings.DB_PATH = original_db
        settings.OUTPUT_DIR = original_output
