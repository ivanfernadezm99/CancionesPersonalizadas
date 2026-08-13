"""Tests for app/music/clipchain.py — Clip chaining pipeline.

Covers split_lyrics, ENERGY_MAP, generate_clips_parallel, stitch_clips,
and generate_stitched with unit and integration tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.music.clipchain import (
    ENERGY_MAP,
    AllProvidersUnavailableError,
    ClipSection,
    _get_energy_descriptor,
    generate_clips_parallel,
    generate_stitched,
    split_lyrics,
    stitch_clips,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def valid_mp3_bytes() -> bytes:
    """Generate a small valid MP3 in memory using pydub."""
    from io import BytesIO

    from pydub import AudioSegment

    seg = AudioSegment.silent(duration=2000, frame_rate=44100)
    buf = BytesIO()
    seg.export(buf, format="mp3", bitrate="192k")
    return buf.getvalue()


@pytest.fixture
def sample_lyrics_6_sections() -> str:
    """Lyrics with all 6 section markers."""
    return """[Verse 1]
Primer verso línea uno
Primer verso línea dos

[Chorus]
Coro línea uno
Coro línea dos

[Verse 2]
Segundo verso línea uno
Segundo verso línea dos

[Chorus]
Coro línea uno
Coro línea dos

[Bridge]
Puente línea uno
Puente línea dos

[Outro]
Outro línea uno
Outro línea dos"""


@pytest.fixture
def sample_lyrics_4_sections() -> str:
    """Lyrics with only 4 section markers (no outro)."""
    return """[Verse 1]
Primer verso

[Chorus]
Coro

[Verse 2]
Segundo verso

[Bridge]
Puente"""


@pytest.fixture
def sample_lyrics_no_markers() -> str:
    """Plain lyrics with no section markers."""
    return """Esta es una canción de amor
Para ti mi amor
Siempre juntos
Por la eternidad"""


@pytest.fixture
def sample_lyrics_single_section() -> str:
    """Lyrics with a single marker."""
    return """[Verse 1]
Un solo verso
Dos líneas
Tres palabras
Cuatro esperanzas"""


@pytest.fixture
def sample_lyrics_unknown_marker() -> str:
    """Lyrics with an unknown section marker."""
    return """[Intro]
Una introducción misteriosa

[Verse 1]
Primer verso
Comienza la historia

[Chorus]
Coro estallido"""


# ═══════════════════════════════════════════════════════════════════════════════
# 4.1 — split_lyrics + ENERGY_MAP
# ═══════════════════════════════════════════════════════════════════════════════


class TestSplitLyrics:
    """Parametrized tests for split_lyrics() and ENERGY_MAP."""

    def test_six_sections(self, sample_lyrics_6_sections: str) -> None:
        """6 markers should produce 6 ClipSections with correct names."""
        sections = split_lyrics(sample_lyrics_6_sections, max_clips=6)

        assert len(sections) == 6
        assert sections[0].section_name == "Verse 1"
        assert sections[1].section_name == "Chorus"
        assert sections[2].section_name == "Verse 2"
        assert sections[3].section_name == "Chorus"
        assert sections[4].section_name == "Bridge"
        assert sections[5].section_name == "Outro"

    def test_six_sections_order(self, sample_lyrics_6_sections: str) -> None:
        """Each ClipSection should have correct order."""
        sections = split_lyrics(sample_lyrics_6_sections, max_clips=6)

        for i, sec in enumerate(sections):
            assert sec.order == i, f"Section {i} has wrong order: {sec.order}"

    def test_six_sections_lyrics_preserved(self, sample_lyrics_6_sections: str) -> None:
        """Each section should contain its own lyrics without markers."""
        sections = split_lyrics(sample_lyrics_6_sections, max_clips=6)

        assert "Primer verso" in sections[0].lyrics_text
        assert "Coro" in sections[1].lyrics_text
        assert "Segundo verso" in sections[2].lyrics_text
        assert "Puente" in sections[4].lyrics_text
        assert "Outro" in sections[5].lyrics_text
        assert "[Verse 1]" not in sections[0].lyrics_text
        assert "[Outro]" not in sections[5].lyrics_text

    def test_four_sections(self, sample_lyrics_4_sections: str) -> None:
        """4 markers should produce 4 ClipSections."""
        sections = split_lyrics(sample_lyrics_4_sections, max_clips=6)

        assert len(sections) == 4
        assert sections[0].section_name == "Verse 1"
        assert sections[3].section_name == "Bridge"

    def test_no_markers_fallback(self, sample_lyrics_no_markers: str) -> None:
        """No markers should produce a single Verse 1 section with full text."""
        sections = split_lyrics(sample_lyrics_no_markers, max_clips=6)

        assert len(sections) == 1
        assert sections[0].section_name == "Verse 1"
        assert sections[0].order == 0
        assert "canción de amor" in sections[0].lyrics_text
        assert "eternidad" in sections[0].lyrics_text

    def test_single_section(self, sample_lyrics_single_section: str) -> None:
        """Single marker should produce one ClipSection."""
        sections = split_lyrics(sample_lyrics_single_section, max_clips=6)

        assert len(sections) == 1
        assert sections[0].section_name == "Verse 1"
        assert "Un solo verso" in sections[0].lyrics_text

    def test_unknown_marker(self, sample_lyrics_unknown_marker: str) -> None:
        """Unknown markers like [Intro] should be ignored (not matched)."""
        sections = split_lyrics(sample_lyrics_unknown_marker, max_clips=6)

        # [Intro] is not matched — only [Verse 1] and [Chorus] are
        assert len(sections) == 2
        assert sections[0].section_name == "Verse 1"
        assert sections[1].section_name == "Chorus"

    def test_respects_max_clips(self, sample_lyrics_6_sections: str) -> None:
        """Should respect max_clips limit."""
        sections = split_lyrics(sample_lyrics_6_sections, max_clips=3)

        assert len(sections) == 3
        assert sections[0].section_name == "Verse 1"
        assert sections[2].section_name == "Verse 2"

    def test_empty_lyrics(self) -> None:
        """Empty text should produce a single empty Verse 1 section."""
        sections = split_lyrics("", max_clips=6)

        assert len(sections) == 1
        assert sections[0].section_name == "Verse 1"
        assert sections[0].lyrics_text == ""


class TestEnergyDescriptor:
    """ENERGY_MAP lookup tests."""

    def test_verse_descriptor(self) -> None:
        """'Verse 1' should map to suave descriptor."""
        desc = _get_energy_descriptor("Verse 1")
        assert desc == ENERGY_MAP["verse"]

    def test_verse_descriptor_no_number(self) -> None:
        """'Verse' without number should map to suave descriptor."""
        desc = _get_energy_descriptor("Verse")
        assert desc == ENERGY_MAP["verse"]

    def test_chorus_descriptor(self) -> None:
        """'Chorus' should map to enérgico descriptor."""
        desc = _get_energy_descriptor("Chorus")
        assert desc == ENERGY_MAP["chorus"]

    def test_bridge_descriptor(self) -> None:
        """'Bridge' should map to clímax descriptor."""
        desc = _get_energy_descriptor("Bridge")
        assert desc == ENERGY_MAP["bridge"]

    def test_outro_descriptor(self) -> None:
        """'Outro' should map to gentil descriptor."""
        desc = _get_energy_descriptor("Outro")
        assert desc == ENERGY_MAP["outro"]

    def test_unknown_section_neutro(self) -> None:
        """Unknown section should return 'neutro'."""
        desc = _get_energy_descriptor("Intro")
        assert desc == "neutro"

    def test_empty_name_neutro(self) -> None:
        """Empty section name should return 'neutro'."""
        desc = _get_energy_descriptor("")
        assert desc == "neutro"

    @pytest.mark.parametrize(
        ("section_name", "expected_key"),
        [
            ("Verse 2", "verse"),
            ("Verse 10", "verse"),
            ("verse 1", "verse"),
            ("CHORUS", "chorus"),
            ("Chorus", "chorus"),
            ("bridge", "bridge"),
            ("OUTRO", "outro"),
        ],
    )
    def test_case_insensitive(self, section_name: str, expected_key: str) -> None:
        """Lookup should be case-insensitive."""
        assert _get_energy_descriptor(section_name) == ENERGY_MAP[expected_key]


# ═══════════════════════════════════════════════════════════════════════════════
# 4.2 — stitch_clips
# ═══════════════════════════════════════════════════════════════════════════════


class TestStitchClips:
    """Tests for stitch_clips() using pydub generated audio."""

    def _make_mp3(self, path: Path, duration_ms: int = 30000) -> Path:
        """Generate a silent MP3 file of the given duration using pydub."""
        from pydub import AudioSegment

        seg = AudioSegment.silent(duration=duration_ms, frame_rate=44100)
        seg.export(str(path), format="mp3", bitrate="192k")
        return path

    def test_stitches_two_clips(self, tmp_path: Path) -> None:
        """Two clips with crossfade should produce correct total duration."""
        clip1 = self._make_mp3(tmp_path / "clip_00.mp3", duration_ms=30000)
        clip2 = self._make_mp3(tmp_path / "clip_01.mp3", duration_ms=30000)

        output = stitch_clips(
            clip_paths=[clip1, clip2],
            crossfade_ms=2500,
            output_path=tmp_path / "final.mp3",
        )

        assert output.exists()
        assert output.suffix == ".mp3"

    def test_stitch_duration_math(self, tmp_path: Path) -> None:
        """Stitched duration should be sum - crossfade (approx)."""
        from pydub import AudioSegment

        # Use 3 clips of 45s each with low crossfade to exceed 120s fallback threshold
        clip1 = self._make_mp3(tmp_path / "clip_00.mp3", duration_ms=45000)
        clip2 = self._make_mp3(tmp_path / "clip_01.mp3", duration_ms=45000)
        clip3 = self._make_mp3(tmp_path / "clip_02.mp3", duration_ms=45000)

        output = stitch_clips(
            clip_paths=[clip1, clip2, clip3],
            crossfade_ms=500,
            output_path=tmp_path / "final.mp3",
        )

        loaded = AudioSegment.from_mp3(str(output))
        # 45 + 45 + 45 - 2*0.5 crossfade ≈ 134s, 3s fade-out ≈ 131s
        expected_min_ms = 45000 + 45000 + 45000 - 1000 - 3000 - 1000  # cf+fade+margin
        expected_max_ms = 45000 + 45000 + 45000 + 1000  # upper bound
        assert expected_min_ms <= len(loaded) <= expected_max_ms, (
            f"Expected ~131s but got {len(loaded)}ms"
        )

    def test_stitch_fade_out_applied(self, tmp_path: Path) -> None:
        """Final stitch should have fade-out (volume drops at end)."""
        from pydub import AudioSegment, effects

        clip1 = self._make_mp3(tmp_path / "clip_00.mp3", duration_ms=10000)
        clip2 = self._make_mp3(tmp_path / "clip_01.mp3", duration_ms=10000)

        output = stitch_clips(
            clip_paths=[clip1, clip2],
            crossfade_ms=500,
            output_path=tmp_path / "final.mp3",
        )

        loaded = AudioSegment.from_mp3(str(output))
        # Check RMS at last 500ms is significantly lower than at midpoint
        mid_start = (len(loaded) // 2) - 250
        end_start = len(loaded) - 500

        mid_rms = effects.normalize(loaded[mid_start : mid_start + 500]).rms
        end_rms = effects.normalize(loaded[end_start:]).rms
        assert end_rms <= mid_rms + 1, "Fade-out should reduce volume at end"

    def test_all_none_raises(self, tmp_path: Path) -> None:
        """All None paths should raise AllProvidersUnavailableError."""
        with pytest.raises(AllProvidersUnavailableError, match="All clip generation"):
            stitch_clips(
                clip_paths=[None, None, None],
                output_path=tmp_path / "final.mp3",
            )

    def test_partial_success_stitches_available(self, tmp_path: Path) -> None:
        """Mix of Path and None should stitch only successful ones."""
        clip1 = self._make_mp3(tmp_path / "clip_00.mp3", duration_ms=10000)
        clip3 = self._make_mp3(tmp_path / "clip_02.mp3", duration_ms=10000)

        output = stitch_clips(
            clip_paths=[clip1, None, clip3],
            crossfade_ms=500,
            output_path=tmp_path / "final.mp3",
        )

        assert output.exists()

    def test_trim_when_exceeds_180s(self, tmp_path: Path) -> None:
        """Stitched result exceeding 180s should be trimmed to 150s."""
        from pydub import AudioSegment

        # 6 x 35s clips with minimal crossfade = ~210s
        clips = [
            self._make_mp3(tmp_path / f"clip_{i:02d}.mp3", duration_ms=35000)
            for i in range(6)
        ]

        output = stitch_clips(
            clip_paths=clips,
            crossfade_ms=100,
            target_seconds=150.0,
            output_path=tmp_path / "final.mp3",
        )

        loaded = AudioSegment.from_mp3(str(output))
        # Should be trimmed to around 150s
        # 6*35 - 5*0.1 = 209.5s, trim to 150000ms
        assert len(loaded) <= 151000  # 151s max (with small encoding margin)

    def test_short_stitch_falls_back_to_extend(self, tmp_path: Path) -> None:
        """Stitched result < 120s should fallback to extend_duration."""
        clip1 = self._make_mp3(tmp_path / "clip_00.mp3", duration_ms=5000)
        clip2 = self._make_mp3(tmp_path / "clip_01.mp3", duration_ms=5000)

        # Stitch with a short duration that triggers extend_duration fallback
        output = stitch_clips(
            clip_paths=[clip1, clip2],
            crossfade_ms=100,
            target_seconds=150.0,
            output_path=tmp_path / "stitched_fallback.mp3",
        )

        # Should exist (after extend_duration fallback)
        assert output.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# 4.3 — generate_clips_parallel (integration w/ mocks)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateClipsParallel:
    """Integration tests for generate_clips_parallel() with mocked OpenClaw."""

    @pytest.mark.asyncio
    async def test_returns_list_of_paths(
        self, tmp_path: Path, valid_mp3_bytes: bytes,
    ) -> None:
        """Happy path: all clips succeed, returns list of Paths."""
        sections = [
            ClipSection(section_name="Verse 1", lyrics_text="verso uno", order=0),
            ClipSection(section_name="Chorus", lyrics_text="coro", order=1),
        ]

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 3
            mock_settings.CLIP_RETRY_ATTEMPTS = 2

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=valid_mp3_bytes)
            mock_client_cls.return_value = mock_client

            results = await generate_clips_parallel(
                sections=sections,
                voice_prompt="romántica",
                job_id="test-parallel-1",
            )

            assert len(results) == 2
            assert results[0] is not None
            assert results[1] is not None
            assert isinstance(results[0], Path)
            assert results[0].suffix == ".mp3"

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(
        self, tmp_path: Path, valid_mp3_bytes: bytes,
    ) -> None:
        """Semaphore(1) should serialize calls (no concurrent invocations)."""
        sections = [
            ClipSection(section_name="Verse 1", lyrics_text="verso", order=0),
            ClipSection(section_name="Chorus", lyrics_text="coro", order=1),
            ClipSection(section_name="Bridge", lyrics_text="puente", order=2),
        ]

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 1
            mock_settings.CLIP_RETRY_ATTEMPTS = 1

            mock_client = MagicMock()
            invoke_counter = 0
            original_invoke = AsyncMock(return_value="task-123")

            async def counted_invoke(*args, **kwargs):  # noqa: ANN202
                nonlocal invoke_counter
                invoke_counter += 1
                assert invoke_counter <= 1, "More than 1 concurrent invoke!"
                await asyncio.sleep(0.05)  # small delay
                invoke_counter -= 1
                return await original_invoke(*args, **kwargs)

            mock_client.invoke = counted_invoke
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=valid_mp3_bytes)
            mock_client_cls.return_value = mock_client

            results = await generate_clips_parallel(
                sections=sections,
                voice_prompt="romántica",
                max_concurrency=1,
                retry_attempts=1,
                job_id="test-concurrency-1",
            )

            assert len(results) == 3
            assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, tmp_path: Path) -> None:
        """Failed invocations should be retried up to retry_attempts times."""
        from app.music.openclaw import OpenClawError

        sections = [
            ClipSection(section_name="Verse 1", lyrics_text="verso", order=0),
        ]

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 1
            mock_settings.CLIP_RETRY_ATTEMPTS = 2

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(
                side_effect=OpenClawError("service unavailable")
            )
            mock_client_cls.return_value = mock_client

            results = await generate_clips_parallel(
                sections=sections,
                voice_prompt="romántica",
                max_concurrency=1,
                retry_attempts=2,
                job_id="test-retry-1",
            )

            assert len(results) == 1
            assert results[0] is None  # All retries failed
            assert mock_client.invoke.await_count == 3  # retry_attempts=2 -> 3 tries

    @pytest.mark.asyncio
    async def test_partial_success(
        self, tmp_path: Path, valid_mp3_bytes: bytes,  # noqa: ARG002
    ) -> None:
        """Mix of success/failure should return [Path, None, Path]."""
        sections = [
            ClipSection(section_name="Verse 1", lyrics_text="verso", order=0),
            ClipSection(section_name="Chorus", lyrics_text="coro fail", order=1),
            ClipSection(section_name="Bridge", lyrics_text="puente", order=2),
        ]

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 3
            mock_settings.CLIP_RETRY_ATTEMPTS = 1

            from app.music.openclaw import OpenClawError

            mock_client = MagicMock()

            async def conditional_invoke(*, lyrics: str, **kwargs) -> str:  # noqa: ANN202, ANN003, ARG001
                if "fail" in lyrics:
                    raise OpenClawError("generation failed")
                return "task-ok"

            mock_client.invoke = conditional_invoke
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=b"x" * 100)
            mock_client_cls.return_value = mock_client

            results = await generate_clips_parallel(
                sections=sections,
                voice_prompt="romántica",
                max_concurrency=3,
                retry_attempts=1,
                job_id="test-partial-1",
            )

            assert len(results) == 3
            assert results[0] is not None  # Verse 1 succeeded
            assert results[1] is None  # Chorus (contains "fail") failed
            assert results[2] is not None  # Bridge succeeded


# ═══════════════════════════════════════════════════════════════════════════════
# 4.4 — generate_stitched (end-to-end with mocks)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateStitched:
    """End-to-end tests for generate_stitched() with mocked internals."""

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_path(
        self, tmp_path: Path, valid_mp3_bytes: bytes,
    ) -> None:
        """Full pipeline should return a Path to the stitched MP3."""
        lyrics = """[Verse 1]
Primer verso

[Chorus]
Coro

[Outro]
Final"""

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 3
            mock_settings.CLIP_RETRY_ATTEMPTS = 1
            mock_settings.CLIP_CROSSFADE_MS = 500
            mock_settings.MAX_CLIPS = 6

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=valid_mp3_bytes)
            mock_client_cls.return_value = mock_client

            # Stitch with clips that are long enough to exceed 120s fallback
            # Use 2s silence per clip (from valid_mp3_bytes) × 3 × ... no, we need
            # 120s+ total. Use extend_duration fallback for valid output.
            result = await generate_stitched(
                lyrics=lyrics,
                voice_prompt="romántica",
                job_id="test-e2e-stitch",
            )

            assert isinstance(result, Path)
            assert result.exists()
            assert result.suffix == ".mp3"

    @pytest.mark.asyncio
    async def test_3_sections_produce_3_clips(
        self, tmp_path: Path, valid_mp3_bytes: bytes,
    ) -> None:
        """3 sections should invoke OpenClaw exactly 3 times."""
        lyrics = """[Verse 1]
Uno

[Chorus]
Dos

[Bridge]
Tres"""

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 3
            mock_settings.CLIP_RETRY_ATTEMPTS = 1
            mock_settings.CLIP_CROSSFADE_MS = 500
            mock_settings.MAX_CLIPS = 6

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=valid_mp3_bytes)
            mock_client_cls.return_value = mock_client

            await generate_stitched(
                lyrics=lyrics,
                voice_prompt="romántica",
                job_id="test-3-clips",
            )

            assert mock_client.invoke.await_count == 3

    @pytest.mark.asyncio
    async def test_all_fail_raises(self, tmp_path: Path) -> None:
        """When all clips fail, generate_stitched should raise."""
        from app.music.openclaw import OpenClawError

        lyrics = """[Verse 1]
Falla

[Chorus]
Falla también"""

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 3
            mock_settings.CLIP_RETRY_ATTEMPTS = 1
            mock_settings.CLIP_CROSSFADE_MS = 500
            mock_settings.MAX_CLIPS = 6

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(
                side_effect=OpenClawError("all failed")
            )
            mock_client_cls.return_value = mock_client

            with pytest.raises(AllProvidersUnavailableError):
                await generate_stitched(
                    lyrics=lyrics,
                    voice_prompt="romántica",
                    job_id="test-all-fail",
                )

    @pytest.mark.asyncio
    async def test_output_saved_in_job_dir(
        self, tmp_path: Path, valid_mp3_bytes: bytes,
    ) -> None:
        """Output should be saved under {OUTPUT_DIR}/{job_id}/final.mp3."""
        lyrics = """[Verse 1]
Hola"""

        with patch("app.music.clipchain.OpenClawClient") as mock_client_cls, \
             patch("app.music.clipchain.settings") as mock_settings:
            mock_settings.OUTPUT_DIR = str(tmp_path)
            mock_settings.OPENCLAW_TOKEN = "test-token"
            mock_settings.OPENCLAW_BASE_URL = "http://localhost:18789"
            mock_settings.MAX_PARALLEL = 1
            mock_settings.CLIP_RETRY_ATTEMPTS = 1
            mock_settings.CLIP_CROSSFADE_MS = 500
            mock_settings.MAX_CLIPS = 6

            mock_client = MagicMock()
            mock_client.invoke = AsyncMock(return_value="task-123")
            mock_client.poll = AsyncMock(
                return_value="http://dl.example.com/song.mp3"
            )
            mock_client.download = AsyncMock(return_value=valid_mp3_bytes)
            mock_client_cls.return_value = mock_client

            result = await generate_stitched(
                lyrics=lyrics,
                voice_prompt="romántica",
                job_id="my-job-dir-test",
            )

            expected = tmp_path / "my-job-dir-test" / "final.mp3"
            assert result == expected
