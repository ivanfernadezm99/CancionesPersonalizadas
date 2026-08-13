"""Tests for app/projects/__init__.py — Project orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import SongProjectCreate


@pytest.fixture
def sample_project_create() -> SongProjectCreate:
    return SongProjectCreate(
        recipient="María",
        relationship="pareja",
        genre="bachata",
        mood="romántica",
        voice="female",
        reference_song="Bachata Rosa - Juan Luis Guerra",
    )


@pytest.fixture
def sample_story_fragments() -> list[dict]:
    return [
        {"id": 1, "fragment": "Nuestro primer viaje a la playa", "sort_order": 0},
        {"id": 2, "fragment": "Esa noche de luna llena", "sort_order": 1},
    ]


@pytest.fixture
def sample_project_dict(sample_story_fragments: list[dict]) -> dict:
    return {
        "id": "test-project-001",
        "recipient": "María",
        "relationship": "pareja",
        "genre": "bachata",
        "mood": "romántica",
        "voice": "female",
        "reference_song": "Bachata Rosa - Juan Luis Guerra",
        "status": "draft",
        "fragments": [
            {**f, "created_at": "2024-01-01T00:00:00"}
            for f in sample_story_fragments
        ],
        "previews": [],
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }


class TestProjectCreate:
    """Tests for create_project()."""

    @pytest.mark.asyncio
    async def test_create_project_returns_id(
        self, sample_project_create: SongProjectCreate,
    ) -> None:
        """create_project() should call store and return a project ID."""
        with patch("app.projects.store.create_project", new_callable=AsyncMock) as mock_store:
            from app.projects import create_project

            mock_store.return_value = "new-project-id-999"

            result = await create_project(sample_project_create)

            assert result == "new-project-id-999"
            mock_store.assert_called_once()


class TestCreatePreviewJob:
    """Tests for create_preview_job()."""

    @pytest.mark.asyncio
    async def test_preview_with_fragments_creates_job(
        self, sample_project_dict: dict, tmp_path: Path,
    ) -> None:
        """create_preview_job() should create job and link it."""
        from app.projects import create_preview_job

        mock_settings = MagicMock()
        mock_settings.DB_PATH = str(tmp_path / "test.db")
        mock_settings.PREVIEW_TARGET_SECONDS = 30

        with (
            patch("app.projects.store.get_project", new_callable=AsyncMock) as mock_get,
            patch(
                "app.projects.store.get_accumulated_story",
                new_callable=AsyncMock,
            ) as mock_story,
            patch("app.projects.create_job_record", new_callable=AsyncMock) as mock_create_job,
            patch("app.projects.store.link_project_job", new_callable=AsyncMock) as mock_link,
            patch("app.projects.project_worker", new_callable=AsyncMock) as mock_worker,
            patch("app.projects.settings", mock_settings),
        ):

            mock_get.return_value = sample_project_dict
            mock_story.return_value = "Nuestro primer viaje a la playa Esa noche de luna llena"
            mock_create_job.return_value = "preview-job-123"

            result = await create_preview_job("test-project-001")

            assert result.job_id == "preview-job-123"
            assert result.status == "queued"
            mock_get.assert_called_once()
            mock_story.assert_called_once()
            mock_create_job.assert_called_once()
            # Verify initial_metadata was passed to create_job_record
            call_kwargs = mock_create_job.call_args[1]
            assert "initial_metadata" in call_kwargs
            assert call_kwargs["initial_metadata"] is not None
            mock_link.assert_called_once()
            call_args = mock_link.call_args
            assert call_args[0] == ("test-project-001", "preview-job-123", "preview")
            assert call_args[1]["db_path"] is not None
            mock_worker.assert_called_once_with("preview-job-123")

    @pytest.mark.asyncio
    async def test_preview_without_fragments_raises(
        self, sample_project_dict: dict,
    ) -> None:
        """create_preview_job() should raise ValueError with no fragments."""
        from app.projects import create_preview_job

        sample_project_dict["fragments"] = []

        with patch("app.projects.store.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_project_dict

            with pytest.raises(ValueError, match="no_story_fragments"):
                await create_preview_job("test-project-001")


class TestCreateFinalJob:
    """Tests for create_final_job()."""

    @pytest.mark.asyncio
    async def test_final_creates_job(
        self, sample_project_dict: dict, tmp_path: Path,
    ) -> None:
        """create_final_job() should create job with final model."""
        from app.projects import create_final_job

        mock_settings = MagicMock()
        mock_settings.DB_PATH = str(tmp_path / "test.db")
        mock_settings.FINAL_TARGET_SECONDS = 150

        with (
            patch("app.projects.store.get_project", new_callable=AsyncMock) as mock_get,
            patch(
                "app.projects.store.get_accumulated_story",
                new_callable=AsyncMock,
            ) as mock_story,
            patch("app.projects.create_job_record", new_callable=AsyncMock) as mock_create_job,
            patch("app.projects.update_status", new_callable=AsyncMock),
            patch("app.projects.store.link_project_job", new_callable=AsyncMock),
            patch("app.projects.project_worker", new_callable=AsyncMock),
            patch("app.projects.settings", mock_settings),
        ):

            mock_get.return_value = sample_project_dict
            mock_story.return_value = "Story text"
            mock_create_job.return_value = "final-job-456"

            result = await create_final_job("test-project-001")

            assert result.job_id == "final-job-456"
            assert result.status == "queued"


class TestProjectWorker:
    """Tests for project_worker()."""

    @pytest.mark.asyncio
    async def test_worker_dispatches_preview_model(
        self, tmp_path: Path,
    ) -> None:
        """project_worker() should use lyria-3-clip-preview for preview jobs."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            # Create a fake job record directly in DB
            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "worker-test-job",
                    json.dumps({
                        "recipient": "María", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántica", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-1",
                        "model": "google/lyria-3-clip-preview",
                        "duration_target": 30,
                        "reference_song": None,
                        "job_type": "preview",
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            # Mock the pipeline steps
            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.music_generate", new_callable=AsyncMock) as mock_music, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"), \
                 patch("app.projects.extend_duration") as mock_extend:

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Test",
                    provider="openai",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "worker-test-job"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "generated.mp3").write_bytes(b"MP3")
                mock_music.return_value = out_dir / "generated.mp3"

                await project_worker("worker-test-job")

                # Verify preview model was used for music generation
                mock_music.assert_called_once()
                call_kwargs = mock_music.call_args[1]
                assert call_kwargs.get("model") == "google/lyria-3-clip-preview"

                # Preview should NOT call extend_duration
                mock_extend.assert_not_called()
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_preview_reaches_complete(
        self, tmp_path: Path,
    ) -> None:
        """Preview jobs must reach 'complete' (regression: standard path skipped
        the 'processing' status transition, so the state machine rejected
        music_generating → complete and the job silently failed)."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "worker-preview-complete",
                    json.dumps({
                        "recipient": "María", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántica", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-1",
                        "model": "google/lyria-3-clip-preview",
                        "duration_target": 30,
                        "reference_song": None,
                        "job_type": "preview",
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.music_generate", new_callable=AsyncMock) as mock_music, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"), \
                 patch("app.projects.extend_duration") as mock_extend:

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Test",
                    provider="openai",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "worker-preview-complete"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "generated.mp3").write_bytes(b"MP3")
                mock_music.return_value = out_dir / "generated.mp3"

                await project_worker("worker-preview-complete")

                # Preview must still emit the processing transition (state machine
                # requires it before complete) but must NOT extend duration.
                mock_extend.assert_not_called()

            conn = await get_connection(settings.DB_PATH)
            cursor = await conn.execute(
                "SELECT status, error FROM jobs WHERE job_id = 'worker-preview-complete'",
            )
            row = await cursor.fetchone()
            await conn.close()

            assert row is not None
            assert row["status"] == "complete", (
                f"preview job should complete, got status={row['status']!r} "
                f"error={row['error']!r}"
            )
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_dispatches_final_model_with_duration_extension(
        self, tmp_path: Path,
    ) -> None:
        """project_worker() should use final model and extend duration for final jobs."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "worker-final-test",
                    json.dumps({
                        "recipient": "María", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántica", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-2",
                        "model": "google/lyria-3-pro-preview",
                        "duration_target": 150,
                        "reference_song": None,
                        "job_type": "final",
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.music_generate", new_callable=AsyncMock) as mock_music, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"), \
                 patch("app.projects.extend_duration") as mock_extend:

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Test",
                    provider="openai",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "worker-final-test"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "generated.mp3").write_bytes(b"MP3")
                mock_music.return_value = out_dir / "generated.mp3"

                from app.music.durext import ExtendResult
                mock_extend.return_value = ExtendResult(
                    path=out_dir / "final.mp3", extended=True,
                )

                await project_worker("worker-final-test")

                # Verify final model was used
                mock_music.assert_called_once()
                call_kwargs = mock_music.call_args[1]
                assert call_kwargs.get("model") == "google/lyria-3-pro-preview"

                # Final should call extend_duration with 150s target
                mock_extend.assert_called_once()
                extend_args = mock_extend.call_args[1]
                assert extend_args.get("target_seconds") == 150
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_passes_reference_song(
        self, tmp_path: Path,
    ) -> None:
        """project_worker() should pass reference_song to lyrics and voice."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "worker-ref-song",
                    json.dumps({
                        "recipient": "María", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántica", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-3",
                        "model": "google/lyria-3-clip-preview",
                        "duration_target": 30,
                        "reference_song": "Bachata Rosa - Juan Luis Guerra",
                        "job_type": "preview",
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with (
                patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics,
                patch(
                    "app.projects.build_prompt",
                    return_value="voice prompt",
                ) as mock_build_prompt,
                patch("app.projects.music_generate", new_callable=AsyncMock) as mock_music,
                patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"),
            ):

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Test",
                    provider="openai",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "worker-ref-song"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "generated.mp3").write_bytes(b"MP3")
                mock_music.return_value = out_dir / "generated.mp3"

                await project_worker("worker-ref-song")

                # RQ-RS-06: "Bachata Rosa - Juan Luis Guerra" is sanitized to
                # "Bachata Rosa" before reaching lyrics and the voice prompt.
                mock_lyrics.assert_called_once()
                lyrics_kwargs = mock_lyrics.call_args[1]
                assert lyrics_kwargs.get("reference_song") == "Bachata Rosa"

                # Verify reference_song passed to build_prompt (sanitized)
                mock_build_prompt.assert_called_once()
                prompt_kwargs = mock_build_prompt.call_args[1]
                assert prompt_kwargs.get("reference_song") == "Bachata Rosa"
        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output


class TestProjectWorkerChaining:
    """Tests for chaining-enabled project_worker paths."""

    @pytest.mark.asyncio
    async def test_worker_calls_generate_stitched_when_chaining_enabled(
        self, tmp_path: Path,
    ) -> None:
        from app.config import settings as app_settings
        app_settings.MUSIC_PROVIDER = "openclaw"
        """project_worker() should use generate_stitched when chaining_enabled in metadata."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "chain-test-job",
                    json.dumps({
                        "recipient": "Brenda", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántico", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-chain",
                        "model": "google/lyria-3-clip-preview",
                        "duration_target": 150,
                        "reference_song": None,
                        "job_type": "final",
                        "chaining_enabled": True,
                        "num_clips": 6,
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.generate_stitched", new_callable=AsyncMock) as mock_stitch, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"):

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Canción para Brenda",
                    provider="test",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "chain-test-job"
                out_dir.mkdir(parents=True, exist_ok=True)
                mock_stitch.return_value = out_dir / "final.mp3"
                (out_dir / "final.mp3").write_bytes(b"STITCHED MP3 DATA")

                await project_worker("chain-test-job")

                # Should have called generate_stitched (not music_generate)
                mock_stitch.assert_called_once()
                stitch_kwargs = mock_stitch.call_args[1]
                assert stitch_kwargs.get("job_id") == "chain-test-job"
                assert "voice_prompt" in stitch_kwargs

        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_music_generate_when_chaining_disabled(
        self, tmp_path: Path,
    ) -> None:
        """project_worker() should use music_generate when chaining_enabled is false."""
        from app.config import settings
        from app.jobs.store import get_connection, init_db
        from app.music.durext import ExtendResult
        from app.projects import project_worker

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "nochain-test-job",
                    json.dumps({
                        "recipient": "María", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántico", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-nochain",
                        "model": "google/lyria-3-pro-preview",
                        "duration_target": 150,
                        "reference_song": None,
                        "job_type": "final",
                        "chaining_enabled": False,
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.music_generate", new_callable=AsyncMock) as mock_music, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"), \
                 patch("app.projects.extend_duration") as mock_extend:

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Test",
                    provider="openai",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "nochain-test-job"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "generated.mp3").write_bytes(b"MP3")
                mock_music.return_value = out_dir / "generated.mp3"
                mock_extend.return_value = ExtendResult(
                    path=out_dir / "final.mp3", extended=True,
                )

                await project_worker("nochain-test-job")

                # Should have called music_generate (not generate_stitched)
                mock_music.assert_called_once()
                mock_extend.assert_called_once()

        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output

    @pytest.mark.asyncio
    async def test_worker_chaining_sets_stitching_used_metadata(
        self, tmp_path: Path,
    ) -> None:
        from app.config import settings
        from app.jobs import get_job
        from app.jobs.store import get_connection, init_db
        from app.projects import project_worker
        settings.MUSIC_PROVIDER = "openclaw"

        original_db = settings.DB_PATH
        original_output = settings.OUTPUT_DIR
        try:
            settings.DB_PATH = str(tmp_path / "jobs.db")
            settings.OUTPUT_DIR = str(tmp_path / "output")

            conn = await get_connection(settings.DB_PATH)
            await init_db(conn)
            now = "2024-01-01T00:00:00"
            await conn.execute(
                """INSERT INTO jobs (job_id, status, params, progress, metadata,
                                     created_at, updated_at)
                   VALUES (?, 'queued', ?, 0.0, ?, ?, ?)""",
                (
                    "chain-meta-test",
                    json.dumps({
                        "recipient": "Brenda", "relationship": "pareja",
                        "occasion": "personalizada", "genre": "bachata",
                        "mood": "romántico", "voice": "female",
                    }),
                    json.dumps({
                        "project_id": "proj-meta",
                        "model": "google/lyria-3-clip-preview",
                        "duration_target": 150,
                        "reference_song": None,
                        "job_type": "final",
                        "chaining_enabled": True,
                        "num_clips": 6,
                    }),
                    now, now,
                ),
            )
            await conn.commit()
            await conn.close()

            with patch("app.projects.lyrics_generate", new_callable=AsyncMock) as mock_lyrics, \
                 patch("app.projects.build_prompt", return_value="voice prompt"), \
                 patch("app.projects.generate_stitched", new_callable=AsyncMock) as mock_stitch, \
                 patch("app.projects._format_lyrics_for_music", return_value="[Verse 1]\nlyrics"):

                from app.models import LyricsResult
                mock_lyrics.return_value = LyricsResult(
                    verses=[{"number": 1, "lines": ["a", "b", "c", "d"]}],
                    chorus={"lines": ["e", "f", "g", "h"]},
                    title_suggestion="Canción para Brenda",
                    provider="test",
                )

                out_dir = Path(settings.OUTPUT_DIR) / "chain-meta-test"
                out_dir.mkdir(parents=True, exist_ok=True)
                mock_stitch.return_value = out_dir / "final.mp3"
                (out_dir / "final.mp3").write_bytes(b"STITCHED")

                await project_worker("chain-meta-test")

                # Verify completion metadata contains stitching_used: true
                job = await get_job("chain-meta-test", db_path=settings.DB_PATH)
                assert job is not None
                meta = json.loads(job.get("metadata") or "{}")
                assert meta.get("stitching_used") is True
                assert meta.get("chaining_enabled") is True

        finally:
            settings.DB_PATH = original_db
            settings.OUTPUT_DIR = original_output
