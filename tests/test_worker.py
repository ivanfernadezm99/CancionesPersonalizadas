"""Tests for app/jobs/worker.py — Job worker orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.jobs import create_job, get_job
from app.jobs.worker import _format_lyrics_for_music, job_worker
from app.models import GenerateRequest


@pytest.fixture
def sample_request() -> GenerateRequest:
    return GenerateRequest(
        recipient="María",
        relationship="pareja",
        occasion="aniversario",
        genre="bachata",
        mood="romántica",
        voice="female",
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "jobs.db")


class TestJobWorker:
    """Tests for job_worker()."""

    @pytest.mark.asyncio
    async def test_worker_completes_successfully(
        self, db_path: str, sample_request: GenerateRequest, tmp_path: Path,
    ) -> None:
        """job_worker() should run the full pipeline and mark job complete."""
        from app.config import settings

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = db_path
            settings.OUTPUT_DIR = str(tmp_path / "output")

            job_id = await create_job(sample_request, db_path=db_path)

            # Create output directory upfront
            out_dir = Path(settings.OUTPUT_DIR) / job_id
            out_dir.mkdir(parents=True, exist_ok=True)

            with patch("app.jobs.worker.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.jobs.worker.build_prompt", return_value="test prompt"), \
                 patch("app.jobs.worker.music_generate", new_callable=AsyncMock) as mock_music, \
                 patch("app.jobs.worker.extend_duration") as mock_extend:

                from app.models import LyricsResult

                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Mi Amor",
                    provider="openai",
                )
                mock_music.return_value = out_dir / "generated.mp3"
                # Create the file so extend_duration has something
                (out_dir / "generated.mp3").write_bytes(b"MP3 content")

                from app.music.durext import ExtendResult

                mock_extend.return_value = ExtendResult(
                    path=out_dir / "final.mp3",
                    extended=True,
                )

                await job_worker(job_id)

                # Verify
                job = await get_job(job_id, db_path=db_path)
                assert job is not None
                assert job["status"] == "complete"
                assert job["progress"] == 1.0

                meta = json.loads(job["metadata"])
                assert meta["recipient"] == "María"
                assert meta["duration_extended"] is True
                assert meta["lyrics_provider"] == "openai"
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_sets_failed_on_error(
        self, db_path: str, sample_request: GenerateRequest,
    ) -> None:
        """job_worker() should mark job as failed on any error."""
        from app.config import settings

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = db_path

            job_id = await create_job(sample_request, db_path=db_path)

            with patch("app.jobs.worker.lyrics_generate", new_callable=AsyncMock) as mock_lyrics:
                mock_lyrics.side_effect = ValueError("LLM API error")

                await job_worker(job_id)

            job = await get_job(job_id, db_path=db_path)
            assert job is not None
            assert job["status"] == "failed"
            assert "LLM API error" in (job.get("error") or "")
        finally:
            settings.DB_PATH = original_db

    @pytest.mark.asyncio
    async def test_worker_nonexistent_job_does_not_error(
        self, db_path: str,
    ) -> None:
        """job_worker() should handle non-existent job gracefully."""
        from app.config import settings

        original_db = settings.DB_PATH
        try:
            settings.DB_PATH = db_path
            await job_worker("nonexistent-id")
            # Should not raise — just log and return
        finally:
            settings.DB_PATH = original_db


class TestFormatLyricsForMusic:
    """Tests for _format_lyrics_for_music()."""

    def test_formats_verses_and_chorus(self) -> None:
        """Should format verses and chorus with markers."""
        from app.models import Chorus, LyricsResult, Verse

        result = LyricsResult(
            verses=[Verse(number=1, lines=["L1", "L2", "L3", "L4"])],
            chorus=Chorus(lines=["C1", "C2", "C3", "C4"]),
            title_suggestion="Test",
            provider="mock",
        )

        text = _format_lyrics_for_music(result)
        assert "[Verse 1]" in text
        assert "L1" in text
        assert "L4" in text
        assert "[Chorus]" in text
        assert "C1" in text

    def test_includes_bridge_when_present(self) -> None:
        """Should include [Bridge] marker when bridge exists."""
        from app.models import Bridge, Chorus, LyricsResult, Verse

        result = LyricsResult(
            verses=[Verse(number=1, lines=["V1", "V2", "V3", "V4"])],
            chorus=Chorus(lines=["C1", "C2", "C3", "C4"]),
            bridge=Bridge(lines=["B1", "B2"]),
            title_suggestion="Test",
            provider="mock",
        )

        text = _format_lyrics_for_music(result)
        assert "[Bridge]" in text
        assert "B1" in text

    def test_omits_bridge_when_none(self) -> None:
        """Should not include [Bridge] when bridge is None."""
        from app.models import Chorus, LyricsResult, Verse

        result = LyricsResult(
            verses=[Verse(number=1, lines=["V1", "V2", "V3", "V4"])],
            chorus=Chorus(lines=["C1", "C2", "C3", "C4"]),
            title_suggestion="Test",
            provider="mock",
        )
        result.bridge = None

        text = _format_lyrics_for_music(result)
        assert "[Bridge]" not in text

    def test_multiple_verses(self) -> None:
        """Should handle multiple verses."""
        from app.models import Chorus, LyricsResult, Verse

        result = LyricsResult(
            verses=[
                Verse(number=1, lines=["V1a", "V1b", "V1c", "V1d"]),
                Verse(number=2, lines=["V2a", "V2b", "V2c", "V2d"]),
            ],
            chorus=Chorus(lines=["C1", "C2", "C3", "C4"]),
            title_suggestion="Test",
            provider="mock",
        )

        text = _format_lyrics_for_music(result)
        assert "[Verse 1]" in text
        assert "[Verse 2]" in text
        assert "V1a" in text
        assert "V2d" in text
