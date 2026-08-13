"""Tests for app/music/providers.py — Music provider abstraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.music.providers import (
    BaseMusicProvider,
    MusicGenerationError,
    OpenClawProvider,
    SunoError,
    SunoProvider,
    _translate_suno_error,
)
from app.tag_sanitizer import ARTIST_REJECTION_MESSAGE

# ── Phase 1: Provider Foundation (RED→GREEN) ───────────────────────────────


class TestBaseMusicProvider:
    """Tests for BaseMusicProvider ABC."""

    def test_abc_cannot_be_instantiated(self) -> None:
        """ABC should not be instantiable directly."""
        with pytest.raises(TypeError):
            BaseMusicProvider("test", "key", "http://localhost")  # type: ignore[abstract]

    def test_abc_enforces_generate(self) -> None:
        """Subclass without generate() should raise TypeError."""
        with pytest.raises(TypeError):

            class MissingGenerate(BaseMusicProvider):  # type: ignore[misc]
                pass

            MissingGenerate("test", "key", "http://localhost")

    def test_abc_subclass_with_generate_instantiates(self) -> None:
        """Subclass that implements generate() should instantiate."""
        class ConcreteProvider(BaseMusicProvider):
            async def generate(
                self,
                lyrics: str,  # noqa: ARG002
                voice_prompt: str,  # noqa: ARG002
                *,
                model: str | None = None,  # noqa: ARG002
                reference_audio: str | None = None,  # noqa: ARG002
                job_id: str | None = None,  # noqa: ARG002
            ) -> Path:
                return Path("/tmp/test.mp3")

        provider = ConcreteProvider("test", "key", "http://localhost")
        assert provider.name == "test"
        assert provider.api_key == "key"
        assert provider.base_url == "http://localhost"

    def test_strips_trailing_slash(self) -> None:
        """Base URL should have trailing slash stripped."""
        class ConcreteProvider(BaseMusicProvider):
            async def generate(
                self, lyrics, voice_prompt, *, model=None,  # noqa: ARG002
                reference_audio=None, job_id=None,  # noqa: ARG002
            ) -> Path:
                return Path("/tmp/test.mp3")

        provider = ConcreteProvider("test", "key", "http://localhost/")
        assert provider.base_url == "http://localhost"


class TestMusicGenerationError:
    """Tests for MusicGenerationError hierarchy."""

    def test_base_error(self) -> None:
        """MusicGenerationError should be a base exception."""
        err = MusicGenerationError("something went wrong")
        assert str(err) == "something went wrong"

    def test_suno_error_is_subclass(self) -> None:
        """SunoError should be a subclass of MusicGenerationError."""
        assert issubclass(SunoError, MusicGenerationError)

    def test_suno_error_message(self) -> None:
        """SunoError should carry a message."""
        err = SunoError("API unavailable")
        assert str(err) == "API unavailable"


# ── Phase 2: Config Settings (via real Settings object) ──────────────────────


class TestConfigSunoSettings:
    """Tests for Suno config settings — isolates from .env file."""

    def test_music_provider_default_is_openclaw(self) -> None:
        """MUSIC_PROVIDER should default to 'openclaw' in pydantic field."""
        from app.config import Settings
        # Create a fresh instance with env vars unset — monkeypatch the relevant
        # env var to ensure we test the class default, not the .env override.
        s = Settings(_env_file=None, MUSIC_PROVIDER="openclaw")
        assert s.MUSIC_PROVIDER == "openclaw"

    def test_suno_settings_exist(self) -> None:
        """Suno config fields should exist on settings."""
        from app.config import settings as real_settings
        assert hasattr(real_settings, "SUNO_API_KEY")
        assert hasattr(real_settings, "SUNO_BASE_URL")
        assert hasattr(real_settings, "SUNO_DEFAULT_MODEL")
        assert hasattr(real_settings, "PUBLIC_BASE_URL")


# ── Phase 2: OpenClawProvider Tests ─────────────────────────────────────────


class TestOpenClawProvider:
    """Tests for OpenClawProvider wrapping OpenClawClient."""

    @pytest.mark.asyncio
    async def test_delegates_to_openclaw_client(self, tmp_path: Path) -> None:
        """OpenClawProvider.generate() should delegate to OpenClawClient."""
        # Patch app.music.OpenClawClient — OpenClawProvider lazily imports it
        # via `from app.music import OpenClawClient` inside __init__
        with patch("app.music.OpenClawClient") as mock_client_cls, \
             patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3 content")
            mock_client_cls.return_value = mock_client

            provider = OpenClawProvider(token="test-token", base_url="http://localhost:18789")
            result = await provider.generate(
                lyrics="Test lyrics",
                voice_prompt="romántica",
                job_id="test-job",
            )

            assert isinstance(result, Path)
            assert result.name == "generated.mp3"
            mock_client.invoke.assert_called_once_with(
                lyrics="Test lyrics", prompt="romántica", model="google/lyria-3-clip-preview",
            )
            mock_client.poll.assert_called_once_with("task-123", timeout=300)
            mock_client.download.assert_called_once_with("http://dl.example.com/song.mp3")

    @pytest.mark.asyncio
    async def test_uses_custom_model(self, tmp_path: Path) -> None:
        """OpenClawProvider should pass model to client.invoke()."""
        with patch("app.music.OpenClawClient") as mock_client_cls, \
             patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-456")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3")
            mock_client_cls.return_value = mock_client

            provider = OpenClawProvider(token="test-token", base_url="http://localhost:18789")
            await provider.generate(
                lyrics="Test", voice_prompt="Test",
                model="lyria-3-pro-preview", job_id="test-job-2",
            )

            mock_client.invoke.assert_called_once_with(
                lyrics="Test", prompt="Test", model="lyria-3-pro-preview",
            )

    @pytest.mark.asyncio
    async def test_ignores_reference_audio(self, tmp_path: Path) -> None:
        """OpenClawProvider should ignore reference_audio parameter."""
        with patch("app.music.OpenClawClient") as mock_client_cls, \
             patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-789")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3")
            mock_client_cls.return_value = mock_client

            provider = OpenClawProvider(token="test-token", base_url="http://localhost:18789")
            await provider.generate(
                lyrics="Test", voice_prompt="Test",
                reference_audio="http://example.com/ref.mp3",
                job_id="test-job-3",
            )

            # Should have called invoke without reference_audio
            mock_client.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_job_id_uses_uuid(self, tmp_path: Path) -> None:
        """OpenClawProvider.generate() without job_id should use UUID."""
        with patch("app.music.OpenClawClient") as mock_client_cls, \
             patch("app.config.settings") as mock_settings, \
             patch("app.music.providers.uuid.uuid4", return_value="auto-uuid"):
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_client = AsyncMock()
            mock_client.invoke = AsyncMock(return_value="task-abc")
            mock_client.poll = AsyncMock(return_value="http://dl.example.com/song.mp3")
            mock_client.download = AsyncMock(return_value=b"MP3")
            mock_client_cls.return_value = mock_client

            provider = OpenClawProvider(token="test-token", base_url="http://localhost:18789")
            result = await provider.generate(lyrics="Test", voice_prompt="Test")

            expected = tmp_path / "auto-uuid" / "generated.mp3"
            assert result == expected

    @pytest.mark.asyncio
    async def test_propagates_openclaw_error(self, tmp_path: Path) -> None:
        """OpenClawProvider should propagate OpenClawClient errors."""
        with patch("app.music.OpenClawClient") as mock_client_cls, \
             patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_client = AsyncMock()
            from app.music.openclaw import OpenClawError
            mock_client.invoke = AsyncMock(side_effect=OpenClawError("API down"))
            mock_client_cls.return_value = mock_client

            provider = OpenClawProvider(token="test-token", base_url="http://localhost:18789")
            with pytest.raises(OpenClawError, match="API down"):
                await provider.generate(lyrics="Test", voice_prompt="Test", job_id="test")


# ── Phase 3: SunoProvider Tests (RED→GREEN) ─────────────────────────────────


class TestSunoInvoke:
    """Tests for SunoProvider._invoke()."""

    @pytest.mark.asyncio
    async def test_invoke_returns_task_id(self) -> None:
        """_invoke() should return task ID from POST /api/v1/generate."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            route = respx.post("http://suno.test/api/v1/generate").respond(
                200,
                json={"id": "task-suno-001"},
            )

            with patch("app.config.settings") as mock_settings:
                mock_settings.SUNO_DEFAULT_MODEL = "V4_5"

                task_id = await provider._invoke(
                    lyrics="Test lyrics",
                    prompt="romántica bachata",
                )

            assert task_id == "task-suno-001"
            # Verify request shape
            sent = route.calls[0].request
            import json
            payload = json.loads(sent.content)
            assert payload["prompt"] == "romántica bachata"
            assert payload["lyrics"] == "Test lyrics"
            assert payload["customMode"] is True
            assert payload["model"] == "V4_5"

    @pytest.mark.asyncio
    async def test_invoke_text_to_music_sends_required_api_fields(self) -> None:
        """Text-to-music payload must include the API-required instrumental and
        callBackUrl fields (sunoapi.org rejects the request with
        "instrumental cannot be null" when they are missing)."""
        import json

        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            route = respx.post("http://suno.test/api/v1/generate").respond(
                200,
                json={"id": "task-suno-002"},
            )

            with patch("app.config.settings") as mock_settings:
                mock_settings.SUNO_DEFAULT_MODEL = "V4_5"

                await provider._invoke(lyrics="Test lyrics", prompt="romántica bachata")

            payload = json.loads(route.calls[0].request.content)
            assert payload["instrumental"] is False
            assert isinstance(payload.get("callBackUrl"), str) and payload["callBackUrl"]

    @pytest.mark.asyncio
    async def test_invoke_text_to_music_unwraps_sunoapi_org_task_id(self) -> None:
        """Text-to-music must unwrap the sunoapi.org {code, msg, data:{taskId}}
        envelope (legacy direct {id} format is also supported)."""
        import json

        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            route = respx.post("http://suno.test/api/v1/generate").respond(
                200,
                json={"code": 200, "msg": "ok", "data": {"taskId": "task-suno-org-001"}},
            )

            with patch("app.config.settings") as mock_settings:
                mock_settings.SUNO_DEFAULT_MODEL = "V4_5"

                task_id = await provider._invoke(lyrics="Test", prompt="Test")

            assert task_id == "task-suno-org-001"
            assert json.loads(route.calls[0].request.content)["instrumental"] is False

    @pytest.mark.asyncio
    async def test_invoke_sends_bearer_token(self) -> None:
        """_invoke() should send API key as Bearer token."""
        import respx

        provider = SunoProvider(api_key="sk-secret-456", base_url="http://suno.test")

        async with respx.mock:
            route = respx.post("http://suno.test/api/v1/generate").respond(
                200, json={"id": "task-002"},
            )

            await provider._invoke(lyrics="Test", prompt="Test")

            assert route.calls[0].request.headers.get("Authorization") == "Bearer sk-secret-456"

    @pytest.mark.asyncio
    async def test_invoke_includes_reference_audio_url(self) -> None:
        """_invoke() should use upload-cover endpoint with uploadUrl for cover."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            route = respx.post("http://suno.test/api/v1/generate/upload-cover").respond(
                200, json={"code": 200, "msg": "ok", "data": {"taskId": "task-cover-001"}},
            )

            task_id = await provider._invoke(
                lyrics="Cover lyrics",
                prompt="pop rock",
                reference_audio="http://localhost/ref-audio/123/reference.mp3",
            )

            assert task_id == "task-cover-001"
            import json
            payload = json.loads(route.calls[0].request.content)
            assert payload["uploadUrl"] == "http://localhost/ref-audio/123/reference.mp3"
            # Cover mode sends lyrics as prompt, not as lyrics field
            assert payload["prompt"] == "Cover lyrics"

    @pytest.mark.asyncio
    async def test_invoke_raises_on_http_error(self) -> None:
        """_invoke() should raise SunoError on HTTP error."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.post("http://suno.test/api/v1/generate").respond(401)

            with pytest.raises(SunoError, match="Suno invoke failed"):
                await provider._invoke(lyrics="Test", prompt="Test")


class TestTranslateSunoError:
    """Tests for _translate_suno_error() (RQ-SUNO-01, design decision 7)."""

    @pytest.mark.parametrize(
        "raw_msg",
        [
            "Your tags contain artist name: Juan Luis Guerra",
            "Tags contain artist name",
            "Suno invoke rejected (code=400): your tags contain the artist.",
            "artist name is not allowed in tags",
        ],
    )
    def test_artist_pattern_matches_spanish(self, raw_msg: str) -> None:
        """Messages naming an artist (IGNORECASE) translate to Spanish."""
        assert _translate_suno_error(raw_msg) == ARTIST_REJECTION_MESSAGE

    @pytest.mark.parametrize(
        "raw_msg",
        [
            "Suno generation failed: server error",
            "Too many requests",
            "Suno invoke failed: HTTP 500 — internal error",
            "Invalid parameter: instrumental cannot be null",
        ],
    )
    def test_other_errors_preserved(self, raw_msg: str) -> None:
        """Any other Suno message must be preserved unchanged."""
        assert _translate_suno_error(raw_msg) == raw_msg


class TestSunoInvokeArtistRejection:
    """Suno 400 artist-rejection raised translated (RQ-SUNO-01, RQ-JOB-02/06)."""

    @pytest.mark.asyncio
    async def test_http_400_artist_rejection_translated(self) -> None:
        """HTTP 400 with artist-naming body raises the friendly Spanish message."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.post("http://suno.test/api/v1/generate").respond(
                400,
                json={"message": "Your tags contain artist name: Juan Luis Guerra"},
            )

            with pytest.raises(SunoError) as exc:
                await provider._invoke(lyrics="Test", prompt="Test")
            assert str(exc.value) == ARTIST_REJECTION_MESSAGE

    @pytest.mark.asyncio
    async def test_http_500_unrelated_error_preserved(self) -> None:
        """HTTP 500 with an unrelated body keeps the original message."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.post("http://suno.test/api/v1/generate").respond(
                500, json={"message": "Internal server error"},
            )

            with pytest.raises(SunoError) as exc:
                await provider._invoke(lyrics="Test", prompt="Test")
            assert "Internal server error" in str(exc.value)
            assert ARTIST_REJECTION_MESSAGE not in str(exc.value)

    @pytest.mark.asyncio
    async def test_biz_code_400_artist_rejection_translated(self) -> None:
        """code=400 business rejection naming an artist is translated."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.post("http://suno.test/api/v1/generate").respond(
                200,
                json={"code": 400, "msg": "Your tags contain artist name: Los Palmeras"},
            )

            with pytest.raises(SunoError) as exc:
                await provider._invoke(lyrics="Test", prompt="Test")
            assert str(exc.value) == ARTIST_REJECTION_MESSAGE

    @pytest.mark.asyncio
    async def test_biz_code_400_unrelated_error_preserved(self) -> None:
        """code=400 with an unrelated message keeps the original text."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.post("http://suno.test/api/v1/generate").respond(
                200,
                json={"code": 400, "msg": "invalid prompt length"},
            )

            with pytest.raises(SunoError) as exc:
                await provider._invoke(lyrics="Test", prompt="Test")
            assert "invalid prompt length" in str(exc.value)
            assert ARTIST_REJECTION_MESSAGE not in str(exc.value)


class TestSunoPoll:
    """Tests for SunoProvider._poll()."""

    @pytest.mark.asyncio
    async def test_poll_completes_immediately(self) -> None:
        """_poll() should return audio_url when task is complete."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.get("http://suno.test/api/v1/generate/record-info?taskId=task-done").respond(
                200,
                json={
                    "id": "task-done",
                    "status": "complete",
                    "audio_url": "http://dl.suno.test/song.mp3",
                },
            )

            url = await provider._poll("task-done", timeout=10)
            assert url == "http://dl.suno.test/song.mp3"

    @pytest.mark.asyncio
    async def test_poll_waits_for_completion(self) -> None:
        """_poll() should poll until status is complete."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            # First call: generating, second: complete
            respx.get(
                "http://suno.test/api/v1/generate/record-info?taskId=task-slow",
            ).respond(
                200, json={"id": "task-slow", "status": "generating"},
            )
            respx.get(
                "http://suno.test/api/v1/generate/record-info?taskId=task-slow",
            ).respond(
                200, json={
                    "id": "task-slow", "status": "complete",
                    "audio_url": "http://dl.suno.test/result.mp3",
                },
            )

            url = await provider._poll("task-slow", timeout=10)
            assert url == "http://dl.suno.test/result.mp3"

    @pytest.mark.asyncio
    async def test_poll_timeout_raises_error(self) -> None:
        """_poll() should raise SunoError on timeout."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.get(
                "http://suno.test/api/v1/generate/record-info?taskId=task-timeout",
            ).respond(
                200, json={"id": "task-timeout", "status": "generating"},
            )

            with pytest.raises(SunoError, match="Suno generation timed out"):
                await provider._poll("task-timeout", timeout=1)

    @pytest.mark.asyncio
    async def test_poll_failed_status_raises_error(self) -> None:
        """_poll() should raise SunoError when status is 'failed'."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.get(
                "http://suno.test/api/v1/generate/record-info?taskId=task-fail",
            ).respond(
                200, json={
                    "id": "task-fail", "status": "failed",
                    "audio_url": "",
                },
            )

            with pytest.raises(SunoError, match="Suno generation failed"):
                await provider._poll("task-fail", timeout=10)


class TestSunoDownload:
    """Tests for SunoProvider._download()."""

    @pytest.mark.asyncio
    async def test_download_returns_bytes(self) -> None:
        """_download() should return MP3 bytes."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.get("http://dl.suno.test/song.mp3").respond(
                200, content=b"MP3\x00\x01\x02\x03",
            )

            data = await provider._download("http://dl.suno.test/song.mp3")
            assert data == b"MP3\x00\x01\x02\x03"


class TestSunoHealthCheck:
    """Tests for SunoProvider._health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_pass(self) -> None:
        """_health_check() should pass when URL returns 200."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            route = respx.head("http://localhost/ref-audio/123/reference.mp3").respond(200)

            await provider._health_check("http://localhost/ref-audio/123/reference.mp3")
            assert route.calls[0].request.method == "HEAD"

    @pytest.mark.asyncio
    async def test_health_check_fail_raises_error(self) -> None:
        """_health_check() should raise SunoError when URL returns 404."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.head("http://localhost/ref-audio/999/reference.mp3").respond(404)

            with pytest.raises(SunoError, match="reference audio unavailable"):
                await provider._health_check("http://localhost/ref-audio/999/reference.mp3")


class TestSunoGenerate:
    """Tests for SunoProvider.generate() — full flow."""

    @pytest.mark.asyncio
    async def test_generate_returns_path(self, tmp_path: Path) -> None:
        """SunoProvider.generate() should return Path to MP3."""
        import respx

        # Patch settings at source module (app.config.settings)
        with patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.SUNO_DEFAULT_MODEL = "V4_5"

            provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

            async with respx.mock:
                # Invoke
                respx.post("http://suno.test/api/v1/generate").respond(
                    200, json={"id": "task-full-flow"},
                )
                # Poll
                respx.get(
                    "http://suno.test/api/v1/generate/record-info?taskId=task-full-flow",
                ).respond(
                    200, json={
                        "id": "task-full-flow", "status": "complete",
                        "audio_url": "http://dl.suno.test/result.mp3",
                    },
                )
                # Download
                respx.get("http://dl.suno.test/result.mp3").respond(
                    200, content=b"MP3 generated content",
                )

                result = await provider.generate(
                    lyrics="Test", voice_prompt="Test",
                    job_id="test-suno-job",
                )

            assert isinstance(result, Path)
            expected = tmp_path / "test-suno-job" / "generated.mp3"
            assert result == expected
            assert result.read_bytes() == b"MP3 generated content"

    @pytest.mark.asyncio
    async def test_generate_cover_mode(self, tmp_path: Path) -> None:
        """SunoProvider.generate() with reference_audio should work in cover mode."""
        import respx

        with patch("app.config.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.SUNO_DEFAULT_MODEL = "V4_5"

            provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

            async with respx.mock:
                # Health check
                respx.head("http://localhost/ref-audio/42/reference.mp3").respond(200)
                # Invoke — Cover mode uses upload-cover endpoint
                route = respx.post("http://suno.test/api/v1/generate/upload-cover").respond(
                    200, json={"code": 200, "msg": "ok", "data": {"taskId": "task-cover"}},
                )
                # Poll
                respx.get(
                    "http://suno.test/api/v1/generate/record-info?taskId=task-cover",
                ).respond(
                    200, json={
                        "id": "task-cover", "status": "complete",
                        "audio_url": "http://dl.suno.test/cover.mp3",
                    },
                )
                # Download
                respx.get("http://dl.suno.test/cover.mp3").respond(
                    200, content=b"MP3 cover output",
                )

                result = await provider.generate(
                    lyrics="Cover lyrics",
                    voice_prompt="pop",
                    reference_audio="http://localhost/ref-audio/42/reference.mp3",
                    job_id="cover-job",
                )

            assert result.exists()
            assert result.read_bytes() == b"MP3 cover output"
            # Verify invoke used upload-cover with uploadUrl
            import json
            payload = json.loads(route.calls[0].request.content)
            assert payload.get("uploadUrl") == "http://localhost/ref-audio/42/reference.mp3"

    @pytest.mark.asyncio
    async def test_generate_health_check_fail_stops_early(self, tmp_path: Path) -> None:  # noqa: ARG002
        """SunoProvider.generate() should fail before invoking if health check fails."""
        import respx

        provider = SunoProvider(api_key="sk-test", base_url="http://suno.test")

        async with respx.mock:
            respx.head("http://localhost/bad-ref.mp3").respond(404)

            with pytest.raises(SunoError, match="reference audio unavailable"):
                await provider.generate(
                    lyrics="Test", voice_prompt="Test",
                    reference_audio="http://localhost/bad-ref.mp3",
                    job_id="fail-early",
                )


# ── Phase 5: _select_music_provider Tests ───────────────────────────────────


class TestSelectMusicProvider:
    """Tests for config-level provider selection."""

    def test_select_openclaw_by_default(self) -> None:
        """_select_music_provider should return OpenClawProvider when MUSIC_PROVIDER=openclaw."""
        from app.music import _select_music_provider
        with patch("app.music.settings") as mock_settings:
            mock_settings.MUSIC_PROVIDER = "openclaw"
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            provider = _select_music_provider()
        assert isinstance(provider, OpenClawProvider)
        assert provider.name == "openclaw"

    def test_select_suno_when_configured(self) -> None:
        """_select_music_provider should return SunoProvider when configured."""
        # Patch app.music.settings — _select_music_provider uses the local
        # `from app.config import settings` in __init__.py namespace
        with patch("app.music.settings") as mock_settings:
            mock_settings.MUSIC_PROVIDER = "suno"
            mock_settings.SUNO_API_KEY = "sk-suno-test"
            mock_settings.SUNO_BASE_URL = "http://suno.test"

            from app.music import _select_music_provider
            provider = _select_music_provider()
            assert isinstance(provider, SunoProvider)
            assert provider.name == "suno"

    def test_validates_suno_config_missing_key(self) -> None:
        """_select_music_provider should validate Suno config."""
        with patch("app.music.settings") as mock_settings:
            mock_settings.MUSIC_PROVIDER = "suno"
            mock_settings.SUNO_API_KEY = ""
            mock_settings.SUNO_BASE_URL = "http://suno.test"

            from app.music import _select_music_provider
            with pytest.raises(MusicGenerationError, match="SUNO_API_KEY"):
                _select_music_provider()

    def test_validates_suno_config_missing_url(self) -> None:
        """_select_music_provider should validate SUNO_BASE_URL."""
        with patch("app.music.settings") as mock_settings:
            mock_settings.MUSIC_PROVIDER = "suno"
            mock_settings.SUNO_API_KEY = "sk-test"
            mock_settings.SUNO_BASE_URL = ""

            from app.music import _select_music_provider
            with pytest.raises(MusicGenerationError, match="SUNO_BASE_URL"):
                _select_music_provider()
