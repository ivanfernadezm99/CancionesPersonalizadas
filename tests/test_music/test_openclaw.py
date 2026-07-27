"""Tests for app/music/openclaw.py — OpenClaw HTTP client."""

from __future__ import annotations

import pytest
import respx

from app.music.openclaw import OpenClawClient, OpenClawError


@pytest.fixture
def client() -> OpenClawClient:
    return OpenClawClient(base_url="http://localhost:18789", token="test-token-123")


class TestOpenClawClientInit:
    """Tests for OpenClawClient initialization."""

    def test_init_sets_base_url(self) -> None:
        client = OpenClawClient(base_url="http://example.com:8080", token="abc")
        assert client.base_url == "http://example.com:8080"

    def test_init_sets_token(self) -> None:
        client = OpenClawClient(base_url="http://example.com", token="secret-456")
        assert client.token == "secret-456"

    def test_strips_trailing_slash(self) -> None:
        client = OpenClawClient(base_url="http://example.com/", token="x")
        assert client.base_url == "http://example.com"


class TestOpenClawClientInvoke:
    """Tests for OpenClawClient.invoke()."""

    @pytest.mark.asyncio
    async def test_invoke_returns_task_id(self, client: OpenClawClient) -> None:
        """invoke() should return a task ID on success."""
        async with respx.mock:
            respx.post("http://localhost:18789/tools/invoke").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "details": {
                            "async": True,
                            "status": "started",
                            "task": {"taskId": "task-abc-123"},
                        },
                    },
                },
            )

            task_id = await client.invoke(lyrics="[Verse 1]\nHola", prompt="romántica")
            assert task_id == "task-abc-123"

    @pytest.mark.asyncio
    async def test_invoke_uses_bearer_token(self, client: OpenClawClient) -> None:
        """invoke() should send the token as Bearer auth."""
        async with respx.mock:
            route = respx.post("http://localhost:18789/tools/invoke").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "details": {
                            "async": True,
                            "status": "started",
                            "task": {"taskId": "task-1"},
                        },
                    },
                },
            )

            await client.invoke(lyrics="Test", prompt="Test")

            request = route.calls[0].request
            assert request.headers.get("Authorization") == "Bearer test-token-123"

    @pytest.mark.asyncio
    async def test_invoke_sends_correct_payload(self, client: OpenClawClient) -> None:
        """invoke() should send the correct JSON payload."""
        async with respx.mock:
            route = respx.post("http://localhost:18789/tools/invoke").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "details": {
                            "async": True,
                            "status": "started",
                            "task": {"taskId": "task-xyz"},
                        },
                    },
                },
            )

            await client.invoke(lyrics="Mi letra aquí", prompt="romántica bachata")

            sent = route.calls[0].request.content
            import json

            payload = json.loads(sent)
            assert payload["tool"] == "music_generate"
            assert payload["args"]["prompt"] == "romántica bachata"
            assert payload["args"]["lyrics"] == "Mi letra aquí"
            assert payload["args"]["instrumental"] is False
            assert payload["args"]["model"] == "google/lyria-3-clip-preview"
            assert payload["args"]["format"] == "mp3"

    @pytest.mark.asyncio
    async def test_invoke_retries_on_failure(self, client: OpenClawClient) -> None:
        """invoke() should retry once on failure (2 attempts, 10s backoff)."""
        async with respx.mock:
            # First 500, then success
            respx.post("http://localhost:18789/tools/invoke").respond(500)
            respx.post("http://localhost:18789/tools/invoke").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "details": {
                            "async": True,
                            "status": "started",
                            "task": {"taskId": "task-retry"},
                        },
                    },
                },
            )

            task_id = await client.invoke(lyrics="Test", prompt="Test")
            assert task_id == "task-retry"

    @pytest.mark.asyncio
    async def test_invoke_raises_on_all_retries_fail(self, client: OpenClawClient) -> None:
        """invoke() should raise OpenClawError if all retries fail."""
        async with respx.mock:
            respx.post("http://localhost:18789/tools/invoke").respond(500)

            with pytest.raises(OpenClawError, match="OpenClaw invoke failed after 2 attempts"):
                await client.invoke(lyrics="Test", prompt="Test")


class TestOpenClawClientPoll:
    """Tests for OpenClawClient.poll()."""

    @pytest.mark.asyncio
    async def test_poll_returns_download_url_on_completion(
        self, client: OpenClawClient,
    ) -> None:
        """poll() should return the download URL when task completes."""
        async with respx.mock:
            respx.get("http://localhost:18789/tools/tasks/task-complete-1").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "status": "completed",
                        "result": {"download_url": "http://download.example.com/song.mp3"},
                    },
                },
            )

            url = await client.poll("task-complete-1", timeout=10)
            assert url == "http://download.example.com/song.mp3"

    @pytest.mark.asyncio
    async def test_poll_polls_until_completed(self, client: OpenClawClient) -> None:
        """poll() should poll multiple times until status becomes completed."""
        async with respx.mock:
            respx.get("http://localhost:18789/tools/tasks/task-polling").respond(
                200,
                json={"ok": True, "result": {"status": "started"}},
            )
            respx.get("http://localhost:18789/tools/tasks/task-polling").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "status": "completed",
                        "result": {"download_url": "http://dl.example.com/song.mp3"},
                    },
                },
            )

            url = await client.poll("task-polling", timeout=10)
            assert url == "http://dl.example.com/song.mp3"

    @pytest.mark.asyncio
    async def test_poll_failed_status_raises_error(self, client: OpenClawClient) -> None:
        """poll() should raise OpenClawError if task status is 'failed'."""
        async with respx.mock:
            respx.get("http://localhost:18789/tools/tasks/task-failed").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "status": "failed",
                        "error": "Generation crashed: OOM",
                    },
                },
            )

            with pytest.raises(OpenClawError, match="Task failed: Generation crashed: OOM"):
                await client.poll("task-failed", timeout=10)

    @pytest.mark.asyncio
    async def test_poll_timeout_raises_error(self, client: OpenClawClient) -> None:
        """poll() should raise OpenClawError if task doesn't complete within timeout."""
        async with respx.mock:
            respx.get("http://localhost:18789/tools/tasks/task-timeout").respond(
                200,
                json={"ok": True, "result": {"status": "started"}},
            )

            with pytest.raises(OpenClawError, match="Task polling timed out after 1s"):
                await client.poll("task-timeout", timeout=1)

    @pytest.mark.asyncio
    async def test_poll_uses_bearer_token(self, client: OpenClawClient) -> None:
        """poll() should use Bearer auth in requests."""
        async with respx.mock:
            route = respx.get("http://localhost:18789/tools/tasks/task-auth").respond(
                200,
                json={
                    "ok": True,
                    "result": {
                        "status": "completed",
                        "result": {"download_url": "http://dl.example.com/song.mp3"},
                    },
                },
            )

            await client.poll("task-auth", timeout=5)

            request = route.calls[0].request
            assert request.headers.get("Authorization") == "Bearer test-token-123"


class TestOpenClawClientDownload:
    """Tests for OpenClawClient.download()."""

    @pytest.mark.asyncio
    async def test_download_returns_bytes(self, client: OpenClawClient) -> None:
        """download() should return the raw bytes of the MP3."""
        async with respx.mock:
            respx.get("http://download.example.com/song.mp3").respond(
                200,
                content=b"MP3\x00\x01\x02\x03",
            )

            data = await client.download("http://download.example.com/song.mp3")
            assert data == b"MP3\x00\x01\x02\x03"
            assert len(data) == 7

    @pytest.mark.asyncio
    async def test_download_retries_on_failure(self, client: OpenClawClient) -> None:
        """download() should retry up to 3 times with exponential backoff."""
        async with respx.mock:
            respx.get("http://dl.example.com/retry-test.mp3").respond(502)
            respx.get("http://dl.example.com/retry-test.mp3").respond(502)
            respx.get("http://dl.example.com/retry-test.mp3").respond(
                200,
                content=b"MP3 content after retry",
            )

            data = await client.download("http://dl.example.com/retry-test.mp3")
            assert data == b"MP3 content after retry"

    @pytest.mark.asyncio
    async def test_download_raises_on_all_retries_fail(self, client: OpenClawClient) -> None:
        """download() should raise OpenClawError if all download retries fail."""
        async with respx.mock:
            respx.get("http://dl.example.com/gone.mp3").respond(404)

            with pytest.raises(OpenClawError, match="Download failed after 3 attempts"):
                await client.download("http://dl.example.com/gone.mp3")
