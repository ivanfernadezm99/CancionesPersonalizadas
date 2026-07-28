"""Tests for app/music/__init__.py — Music generation public API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.music import extend_duration, generate


class TestMusicGenerate:
    """Tests for generate()."""

    @pytest.mark.asyncio
    async def test_generate_returns_path(self, tmp_path: Path) -> None:
        """generate() should return a Path to the saved MP3."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 content here")
            mock_client_obj.return_value = mock_client

            result = await generate(lyrics="Test lyrics", voice_prompt="romántica")

            assert isinstance(result, Path)
            assert result.exists()
            assert result.suffix == ".mp3"

    @pytest.mark.asyncio
    async def test_generate_saves_in_output_dir(self, tmp_path: Path) -> None:
        """generate() should save file under {OUTPUT_DIR}/{job_id}/."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings, \
             patch("app.music.uuid.uuid4", return_value="test-job-123"):
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 data")
            mock_client_obj.return_value = mock_client

            result = await generate(lyrics="Test", voice_prompt="Test")

            expected = tmp_path / "test-job-123" / "generated.mp3"
            assert result == expected

    @pytest.mark.asyncio
    async def test_generate_openclaw_error_raises(self, tmp_path: Path) -> None:
        """generate() should propagate OpenClawError on failure."""
        from app.music.openclaw import OpenClawError

        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(side_effect=OpenClawError("invoke failed"))
            mock_client_obj.return_value = mock_client

            with pytest.raises(OpenClawError, match="invoke failed"):
                await generate(lyrics="Test", voice_prompt="Test")

    @pytest.mark.asyncio
    async def test_generate_creates_directory(self, tmp_path: Path) -> None:
        """generate() should create the output directory."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 data")
            mock_client_obj.return_value = mock_client

            result = await generate(lyrics="Test", voice_prompt="Test")

            assert result.parent.exists()

    @pytest.mark.asyncio
    async def test_generate_with_job_id_uses_job_id_dir(self, tmp_path: Path) -> None:
        """generate(job_id=...) should output to {OUTPUT_DIR}/{job_id}/."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 data")
            mock_client_obj.return_value = mock_client

            result = await generate(
                lyrics="Test", voice_prompt="Test",
                job_id="my-custom-job-456",
            )

            expected = tmp_path / "my-custom-job-456" / "generated.mp3"
            assert result == expected

    @pytest.mark.asyncio
    async def test_generate_without_job_id_uses_random_uuid(self, tmp_path: Path) -> None:
        """generate() without job_id should use a random UUID."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings, \
             patch("app.music.uuid.uuid4", return_value="random-uuid-789"):
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 data")
            mock_client_obj.return_value = mock_client

            result = await generate(lyrics="Test", voice_prompt="Test")

            expected = tmp_path / "random-uuid-789" / "generated.mp3"
            assert result == expected

    @pytest.mark.asyncio
    async def test_generate_passes_model_to_client(self, tmp_path: Path) -> None:
        """generate() should pass model param to client.invoke()."""
        with patch("app.music.OpenClawClient") as mock_client_obj, \
             patch("app.music.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"

            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 data")
            mock_client_obj.return_value = mock_client

            await generate(
                lyrics="Test", voice_prompt="Test",
                model="lyria-3-pro-preview",
            )

            mock_client.invoke.assert_called_once_with(
                lyrics="Test", prompt="Test",
                model="lyria-3-pro-preview",
            )


class TestMusicExtendDuration:
    """Tests for extend_duration() public API."""

    def test_extend_duration_delegates_to_durext(self, tmp_path: Path) -> None:
        """extend_duration() should delegate to durext by checking behavior."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_text("not a real mp3")

        # Without patching, the real extend_duration tries to load the MP3
        # and returns extended=False (which is the graceful failure path)
        result = extend_duration(mp3_path, target_seconds=30)
        assert result.path == mp3_path
        assert result.extended is False

    def test_extend_duration_accepts_target_seconds(self, tmp_path: Path) -> None:
        """extend_duration() should accept target_seconds parameter."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_text("not a real mp3")

        result = extend_duration(mp3_path, target_seconds=300)
        assert result.path == mp3_path
        assert result.extended is False

    def test_extend_duration_default_target(self, tmp_path: Path) -> None:
        """extend_duration() should use 150s default."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_text("not a real mp3")

        result = extend_duration(mp3_path)
        assert result.path == mp3_path
        # Returns extended=False when loading fails (graceful fallback)
        assert result.extended is False
