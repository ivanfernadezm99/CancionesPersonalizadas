"""Multi-provider music generation abstraction.

Provides BaseMusicProvider ABC, OpenClawProvider wrapping the existing
OpenClawClient, and SunoProvider implementing Suno REST API with
text-to-music and Cover modes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


# ── Custom Exceptions ────────────────────────────────────────────────────────


class MusicGenerationError(Exception):
    """Raised when music generation fails at any stage."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class SunoError(MusicGenerationError):
    """Raised when Suno API calls fail."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ── Abstract Base Provider ───────────────────────────────────────────────────


class BaseMusicProvider(ABC):
    """Abstract base for music generation providers."""

    def __init__(self, name: str, api_key: str, base_url: str) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def generate(
        self,
        lyrics: str,
        voice_prompt: str,
        *,
        model: str | None = None,
        reference_audio: str | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Generate music from lyrics and style prompt.

        Args:
            lyrics: Full lyrics text.
            voice_prompt: Style/genre voice prompt.
            model: Optional model override (provider-specific).
            reference_audio: Optional URL to reference audio for cover mode.
            job_id: Optional job ID for output subdirectory.

        Returns:
            Path to the saved MP3 file.

        Raises:
            MusicGenerationError: If generation fails at any stage.
        """


# ── OpenClaw Provider ────────────────────────────────────────────────────────


class OpenClawProvider(BaseMusicProvider):
    """Music generation via OpenClaw/Lyria 3 gateway.

    Wraps the existing OpenClawClient without modifying it.
    """

    def __init__(self, token: str, base_url: str) -> None:
        super().__init__("openclaw", token, base_url)
        # Lazy import to avoid circular dependency with app.music.__init__
        from app.music import OpenClawClient

        self._client = OpenClawClient(base_url=self.base_url, token=self.api_key)

    async def generate(
        self,
        lyrics: str,
        voice_prompt: str,
        *,
        model: str | None = None,
        reference_audio: str | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Generate music via OpenClaw.

        reference_audio is ignored — OpenClaw doesn't support Cover mode.
        """
        from app.config import settings

        if job_id is None:
            job_id = str(uuid.uuid4())
        output_path = Path(settings.OUTPUT_DIR) / job_id / "generated.mp3"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        effective_model = model or "google/lyria-3-clip-preview"

        logger.info("OpenClaw: invoking generation (job_id=%s, model=%s)", job_id, effective_model)
        task_id = await self._client.invoke(
            lyrics=lyrics, prompt=voice_prompt, model=effective_model,
        )

        logger.info("OpenClaw: polling task %s", task_id)
        download_url = await self._client.poll(task_id, timeout=300)

        logger.info("OpenClaw: downloading MP3 from %s", download_url)
        mp3_bytes = await self._client.download(download_url)

        output_path.write_bytes(mp3_bytes)
        logger.info(
            "OpenClaw: generation complete — %d bytes saved to %s",
            len(mp3_bytes), output_path,
        )
        return output_path


# ── Suno Provider ────────────────────────────────────────────────────────────


class SunoProvider(BaseMusicProvider):
    """Music generation via Suno AI REST API.

    Supports text-to-music (generate) and Cover (reference audio + lyrics).
    """

    def __init__(self, api_key: str, base_url: str) -> None:
        super().__init__("suno", api_key, base_url)

    async def generate(
        self,
        lyrics: str,
        voice_prompt: str,
        *,
        model: str | None = None,
        reference_audio: str | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Generate music via Suno API.

        If reference_audio is provided, runs Cover mode (health check → invoke
        with reference_audio_url → poll → download). Otherwise runs standard
        text-to-music (invoke → poll → download).
        """
        from app.config import settings

        if job_id is None:
            job_id = str(uuid.uuid4())
        output_path = Path(settings.OUTPUT_DIR) / job_id / "generated.mp3"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Cover mode: health check reference audio first
        if reference_audio:
            await self._health_check(reference_audio)

        # Invoke
        task_id = await self._invoke(lyrics, voice_prompt, reference_audio)

        # Poll
        audio_url = await self._poll(task_id)

        # Download
        mp3_bytes = await self._download(audio_url)

        output_path.write_bytes(mp3_bytes)
        logger.info(
            "Suno: generation complete — %d bytes saved to %s",
            len(mp3_bytes), output_path,
        )
        return output_path

    async def _invoke(
        self,
        lyrics: str,
        prompt: str,
        reference_audio: str | None = None,
    ) -> str:
        """Invoke Suno text-to-music or Cover generation.

        Text-to-music: POST /api/v1/generate with lyrics + prompt.
        Cover mode:    POST /api/v1/generate/upload-cover with uploadUrl.
        """
        from app.config import settings

        if reference_audio:
            # Cover mode — separate endpoint with uploaded reference audio
            payload: dict[str, object] = {
                "uploadUrl": reference_audio,
                "customMode": True,
                "style": prompt,
                "title": "Para Brenda",
                "prompt": lyrics,
                "model": settings.SUNO_DEFAULT_MODEL,
                "callBackUrl": "https://enlaceschacocloud.duckdns.org/",
                "instrumental": False,
            }
            endpoint = f"{self.base_url}/api/v1/generate/upload-cover"
        else:
            # Text-to-music — standard generation
            payload = {
                "prompt": prompt,
                "customMode": True,
                "style": prompt,
                "title": "",
                "model": settings.SUNO_DEFAULT_MODEL,
                "lyrics": lyrics,
                # API-required fields (sunoapi.org rejects with
                # "instrumental cannot be null" when either is missing)
                "instrumental": False,
                "callBackUrl": "https://enlaceschacocloud.duckdns.org/",
            }
            endpoint = f"{self.base_url}/api/v1/generate"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code != 200:
                raise SunoError(
                    f"Suno invoke failed: HTTP {response.status_code} — {response.text[:200]}",
                )
            data = response.json()
            # Check business code (some Suno APIs return 200 with code=400)
            biz_code = data.get("code", 200)
            if biz_code != 200:
                msg = data.get("msg", data.get("message", "Unknown error"))
                raise SunoError(f"Suno invoke rejected (code={biz_code}): {msg}")
            # Cover mode wraps response in { code, msg, data: { taskId, ... } }
            if reference_audio:
                response_data = data.get("data")
                task_id: str = response_data.get("taskId", "") if response_data else ""
            else:
                # Legacy format: { "id": ... }; sunoapi.org: { code, data: { taskId } }
                task_id = data.get("id") or ""
                if not task_id:
                    response_data = data.get("data")
                    task_id = response_data.get("taskId", "") if response_data else ""
            if not task_id:
                raise SunoError("Suno invoke returned no task ID")
            logger.info("Suno invoke successful: taskId=%s (cover=%s)", task_id, bool(reference_audio))
            return task_id

    async def _poll(self, task_id: str, timeout: int = 300) -> str:
        """Poll for Suno generation completion.

        Polls every 5s with exponential backoff capped at 30s.
        Supports both legacy (direct fields) and sunoapi.org
        ({code, msg, data: {status, response}}) response formats.
        """
        url = f"{self.base_url}/api/v1/generate/record-info?taskId={task_id}"
        start = asyncio.get_event_loop().time()
        interval = 5.0

        while (asyncio.get_event_loop().time() - start) < timeout:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                body = response.json()

                # Unwrap {code, msg, data} envelope (sunoapi.org format)
                payload = body.get("data", body) if body.get("code") is not None else body

                status: str = (
                    payload.get("status", "")
                    if isinstance(payload, dict)
                    else ""
                ).upper()

                if status in ("SUCCESS", "COMPLETE", "complete"):
                    # Try response field first (sunoapi.org: dict or JSON string with sunoData)
                    audio_url = ""
                    resp_raw = payload.get("response", "")
                    resp_data = None
                    if isinstance(resp_raw, dict):
                        resp_data = resp_raw
                    elif isinstance(resp_raw, str) and resp_raw.strip():
                        try:
                            resp_data = json.loads(resp_raw)
                        except (json.decoder.JSONDecodeError, TypeError):
                            pass
                    if resp_data:
                        suno_items = resp_data.get("sunoData", [])
                        if suno_items and isinstance(suno_items, list):
                            audio_url = suno_items[0].get("audioUrl", "")
                    # Fallback: direct audio_url field (legacy)
                    if not audio_url:
                        audio_url = payload.get("audio_url", "")
                    if not audio_url:
                        raise SunoError("Task completed but no audio_url in response")
                    logger.info("Suno task %s completed", task_id)
                    return audio_url

                error_code = payload.get("errorCode", "")
                error_msg = payload.get("errorMessage", "")
                if status in ("FAILED", "ERROR") or error_code:
                    msg = error_msg or payload.get("error", "Unknown error")
                    raise SunoError(f"Suno generation failed: {msg}")

                # Still in progress — wait with capped exponential backoff
                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 30.0)

        raise SunoError(f"Suno generation timed out after {timeout}s")

    async def _download(self, url: str) -> bytes:
        """Download MP3 bytes from the Suno audio URL."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
            logger.info("Suno download: %d bytes", len(content))
            return content

    async def _health_check(self, url: str) -> None:
        """Verify reference audio URL is reachable (HEAD request)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(url)
            if response.status_code != 200:
                raise SunoError(
                    f"reference audio unavailable: HTTP {response.status_code} — {url}",
                )
            logger.info("Suno cover: reference audio reachable at %s", url)
