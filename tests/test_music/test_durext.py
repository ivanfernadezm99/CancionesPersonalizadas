"""Tests for app/music/durext.py — Duration extension via pydub."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.music.durext import ExtendResult, extend_duration, simple_loop, smart_crossfade_loop


class TestSmartCrossfadeLoop:
    """Tests for smart_crossfade_loop()."""

    def test_extends_audio_to_target_duration(self) -> None:
        """Given a short audio, should produce audio at least target_ms long."""
        audio = _make_synth_audio(duration_ms=5000)  # 5 seconds
        result = smart_crossfade_loop(audio, target_ms=15000)  # target 15s
        assert result.duration_seconds >= 14.0  # allow small tolerance

    def test_returns_audio_when_already_long_enough(self) -> None:
        """When audio already meets or exceeds target, return it as-is."""
        audio = _make_synth_audio(duration_ms=20000)  # 20s
        result = smart_crossfade_loop(audio, target_ms=15000)
        # Should still return at least the target
        assert result.duration_seconds >= 15.0

    def test_crossfade_loop_short_audio(self) -> None:
        """Very short audio (1s) should still be extendable."""
        audio = _make_synth_audio(duration_ms=1000)  # 1s
        result = smart_crossfade_loop(audio, target_ms=10000)  # 10s
        assert result.duration_seconds >= 9.0


class TestSimpleLoop:
    """Tests for simple_loop()."""

    def test_repeats_audio_to_target(self) -> None:
        """simple_loop should extend audio to target duration."""
        audio = _make_synth_audio(duration_ms=5000)
        result = simple_loop(audio, target_ms=20000)
        assert result.duration_seconds >= 19.0

    def test_short_audio_with_simple_loop(self) -> None:
        """Very short audio should be extendable with simple loop."""
        audio = _make_synth_audio(duration_ms=2000)
        result = simple_loop(audio, target_ms=12000)
        assert result.duration_seconds >= 11.0


class TestExtendDuration:
    """Tests for extend_duration()."""

    def test_returns_path_and_extended_flag(self, tmp_path: Path) -> None:
        """extend_duration should return ExtendResult with path and flag."""
        mp3_path = _create_test_mp3(tmp_path, duration_ms=5000)
        result = extend_duration(mp3_path, target_seconds=15)
        assert isinstance(result, ExtendResult)
        assert isinstance(result.path, Path)
        assert isinstance(result.extended, bool)

    def test_short_audio_gets_extended(self, tmp_path: Path) -> None:
        """Short audio should be extended to target."""
        mp3_path = _create_test_mp3(tmp_path, duration_ms=5000)
        result = extend_duration(mp3_path, target_seconds=15)
        assert result.extended is True
        assert result.path.exists()
        assert result.path.suffix == ".mp3"

    def test_audio_already_long_enough_not_extended(self, tmp_path: Path) -> None:
        """Audio already meeting target should not be extended."""
        mp3_path = _create_test_mp3(tmp_path, duration_ms=30000)
        result = extend_duration(mp3_path, target_seconds=15)
        assert result.extended is False

    def test_custom_target_seconds(self, tmp_path: Path) -> None:
        """Custom target_seconds should be respected."""
        mp3_path = _create_test_mp3(tmp_path, duration_ms=5000)
        result = extend_duration(mp3_path, target_seconds=30)
        assert result.extended is True

    def test_handles_missing_file_gracefully(self, tmp_path: Path) -> None:
        """Missing file should be handled gracefully."""
        missing = tmp_path / "nonexistent.mp3"
        result = extend_duration(missing)
        assert result.path == missing
        assert result.extended is False


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_synth_audio(duration_ms: int):
    """Create a synthetic audio segment for testing."""
    try:
        from pydub import AudioSegment
    except ImportError:
        pytest.skip("pydub not available")

    import array
    import struct

    # Generate simple sine wave
    sample_rate = 44100
    num_samples = int(sample_rate * duration_ms / 1000)
    samples = array.array("h", [0]) * num_samples

    for i in range(num_samples):
        t = i / sample_rate
        # Simple 440Hz sine wave
        samples[i] = int(16000 * __import__("math").sin(2 * 3.14159 * 440 * t))

    raw_data = struct.pack(f"<{len(samples)}h", *samples)
    return AudioSegment(
        data=raw_data,
        sample_width=2,
        frame_rate=sample_rate,
        channels=1,
    )


def _create_test_mp3(tmp_path: Path, duration_ms: int) -> Path:
    """Create a test MP3 file and return its path."""
    audio = _make_synth_audio(duration_ms)
    path = tmp_path / "test.mp3"
    audio.export(str(path), format="mp3", bitrate="192k")
    return path
