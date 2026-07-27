"""Tests for app/stream/__init__.py — Async streaming generator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.stream import stream_generator


class TestStreamGenerator:
    """Tests for stream_generator()."""

    @pytest.mark.asyncio
    async def test_yields_chunks_from_file(self, tmp_path: Path) -> None:
        """stream_generator() should yield all data from the file in chunks."""
        content = b"X" * 200000  # 200KB
        file_path = tmp_path / "test.mp3"
        file_path.write_bytes(content)

        chunks = []
        async for chunk in stream_generator(file_path, chunk_size=65536):
            chunks.append(chunk)

        assert len(chunks) >= 3  # 200KB / 64KB = ~3.1 chunks
        assert b"".join(chunks) == content

    @pytest.mark.asyncio
    async def test_custom_chunk_size(self, tmp_path: Path) -> None:
        """stream_generator() should respect custom chunk_size."""
        content = b"Hello World! " * 1000
        file_path = tmp_path / "test.mp3"
        file_path.write_bytes(content)

        chunks = []
        async for chunk in stream_generator(file_path, chunk_size=100):
            chunks.append(chunk)

        # All chunks should be at most 100 bytes (except maybe last)
        for chunk in chunks[:-1]:
            assert len(chunk) == 100
        assert b"".join(chunks) == content

    @pytest.mark.asyncio
    async def test_empty_file(self, tmp_path: Path) -> None:
        """stream_generator() should handle empty files."""
        file_path = tmp_path / "empty.mp3"
        file_path.write_bytes(b"")

        chunks = []
        async for chunk in stream_generator(file_path):
            chunks.append(chunk)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_small_file(self, tmp_path: Path) -> None:
        """stream_generator() should handle files smaller than chunk_size."""
        content = b"small file"
        file_path = tmp_path / "small.mp3"
        file_path.write_bytes(content)

        chunks = []
        async for chunk in stream_generator(file_path, chunk_size=65536):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == content

    @pytest.mark.asyncio
    async def test_detects_disconnect_and_cleans_up(self, tmp_path: Path) -> None:
        """stream_generator() should stop when the stop_event is set."""
        content = b"X" * 100000
        file_path = tmp_path / "test_disconnect.mp3"
        file_path.write_bytes(content)

        stop_event = asyncio.Event()
        received_chunks = []

        async def consumer():
            i = 0
            async for chunk in stream_generator(
                file_path, chunk_size=10000, stop_event=stop_event,
            ):
                received_chunks.append(chunk)
                i += 1
                if i >= 3:
                    stop_event.set()  # Simulate disconnect after 3 chunks

        await consumer()

        # Should have received some chunks but not all
        assert len(received_chunks) >= 3
        assert len(received_chunks) < 10  # We stopped, so fewer than all

    @pytest.mark.asyncio
    async def test_file_not_found(self, tmp_path: Path) -> None:
        """stream_generator() should raise FileNotFoundError for missing file."""
        missing = tmp_path / "nonexistent.mp3"

        with pytest.raises(FileNotFoundError):
            async for _ in stream_generator(missing):
                pass  # pragma: no cover
