"""OpenClaw HTTP client for Lyria 3 music generation.

Provides invoke, poll, and download methods with retry logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenClawError(Exception):
    """Raised when OpenClaw API calls fail after retries."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class OpenClawClient:
    """Async HTTP client for the OpenClaw music generation gateway."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def invoke(
        self,
        lyrics: str,
        prompt: str,
        model: str = "google/lyria-3-clip-preview",
    ) -> str:
        """Invoke music generation via OpenClaw.

        Posts to /tools/invoke with retry (2 attempts, 10s backoff).

        Args:
            lyrics: Full lyrics text with markers.
            prompt: Style/genre prompt for Lyria 3.
            model: OpenClaw model name (default: google/lyria-3-clip-preview).

        Returns:
            Task ID for polling.

        Raises:
            OpenClawError: If all retry attempts fail.
        """
        payload = {
            "tool": "music_generate",
            "args": {
                "prompt": prompt,
                "lyrics": lyrics,
                "instrumental": False,
                "model": model,
                "format": "mp3",
            },
        }

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    response = await http_client.post(
                        f"{self.base_url}/tools/invoke",
                        headers=self._headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data: dict[str, Any] = response.json()

                    if not data.get("ok"):
                        raise OpenClawError(f"OpenClaw invoke returned ok=false: {data}")

                    result_data: dict[str, Any] = data.get("result", {})
                    details: dict[str, Any] = result_data.get("details", {})
                    task: dict[str, Any] = details.get("task", {})
                    task_id: str | None = task.get("taskId")
                    if not task_id:
                        raise OpenClawError("No taskId in OpenClaw invoke response")

                    logger.info("OpenClaw invoke successful: taskId=%s", task_id)
                    return task_id

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "OpenClaw invoke attempt %d/2 failed: %s", attempt + 1, exc,
                )
                if attempt == 0:
                    await asyncio.sleep(10)

        raise OpenClawError(
            f"OpenClaw invoke failed after 2 attempts: {last_error}",
        )

    async def poll(self, task_id: str, timeout: int = 300) -> str:
        """Poll for task completion.

        Polls every 5s with exponential backoff cap at 30s.

        Args:
            task_id: The task ID from invoke().
            timeout: Maximum seconds to poll before timing out.

        Returns:
            Download URL for the generated MP3.

        Raises:
            OpenClawError: If task fails or polling times out.
        """
        url = f"{self.base_url}/tools/tasks/{task_id}"
        start = asyncio.get_event_loop().time()
        interval = 5.0

        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    response = await http_client.get(url, headers=self._headers)
                    response.raise_for_status()
                    data: dict[str, Any] = response.json()

                    if not data.get("ok"):
                        raise OpenClawError(f"Poll returned ok=false: {data}")

                    result = data.get("result", {})
                    status = result.get("status", "")

                    if status == "completed":
                        result_result: dict[str, Any] = result.get("result", {})
                        download_url: str | None = result_result.get("download_url")
                        if not download_url:
                            raise OpenClawError(
                                "Task completed but no download_url in response",
                            )
                        logger.info(
                            "Task %s completed, download_url available", task_id,
                        )
                        return download_url

                    if status == "failed":
                        error_msg = result.get("error", "Unknown error")
                        raise OpenClawError(f"Task failed: {error_msg}")

                    # Still in progress — wait with capped exponential backoff
                    await asyncio.sleep(interval)
                    interval = min(interval * 1.5, 30.0)

            except OpenClawError:
                raise
            except Exception as exc:
                logger.warning("Poll attempt failed: %s", exc)
                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 30.0)

        raise OpenClawError(f"Task polling timed out after {timeout}s")

    async def download(self, url: str) -> bytes:
        """Download the generated MP3 from the URL.

        Retries up to 3 times with exponential backoff (2/4/8s).

        Args:
            url: The download URL from poll().

        Returns:
            Raw MP3 bytes.

        Raises:
            OpenClawError: If all download attempts fail.
        """
        backoff = 2.0
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=120.0) as http_client:
                    response = await http_client.get(url, headers=self._headers)
                    response.raise_for_status()
                    content = response.content
                    logger.info(
                        "Download successful: %d bytes (attempt %d/3)",
                        len(content), attempt + 1,
                    )
                    return content

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Download attempt %d/3 failed: %s", attempt + 1, exc,
                )
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    backoff *= 2

        raise OpenClawError(
            f"Download failed after 3 attempts: {last_error}",
        )
