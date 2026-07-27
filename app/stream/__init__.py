"""Async streaming generator with disconnect detection.

Provides an async generator that reads files in chunks and supports
early termination when a client disconnects.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

logger = logging.getLogger(__name__)


async def stream_generator(
    file_path: Path,
    chunk_size: int = 65536,
    stop_event: asyncio.Event | None = None,
) -> AsyncGenerator[bytes, None]:
    """Read a file in chunks as an async generator.

    Supports client disconnect detection via stop_event.
    When stop_event is set, the generator stops producing chunks.

    Args:
        file_path: Path to the file to stream.
        chunk_size: Size of each chunk in bytes (default 64KB).
        stop_event: Optional event to signal early termination.

    Yields:
        Bytes chunks from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    loop = asyncio.get_event_loop()

    with open(file_path, "rb") as fp:
        try:
            while True:
                # Check for disconnect
                if stop_event is not None and stop_event.is_set():
                    logger.info("Stream generator: stop event set, cleaning up")
                    break

                chunk: bytes | None = await loop.run_in_executor(None, fp.read, chunk_size)
                if not chunk:
                    break

                yield chunk

                # Yield control to event loop between chunks
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info("Stream generator: cancelled, cleaning up")
        except GeneratorExit:
            logger.info("Stream generator: generator exit, cleaning up")
