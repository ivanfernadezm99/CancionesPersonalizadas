"""Audio reference analysis via Whisper transcription + pydub feature extraction.

Extracts lyrics, language, duration, energy, and estimated tempo from an
uploaded MP3 to generate a style description for Lyria 3 music generation.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AudioAnalysisResult:
    """Result of analyzing a reference audio file."""

    language: str = "es"
    transcript: str = ""
    duration_seconds: float = 0.0
    energy: str = "media"  # baja, media, alta
    estimated_tempo: str = "medio"  # lento, medio, rápido
    style_description: str = ""


@dataclass
class AudioAnalysisError:
    """Error during audio analysis."""

    error: str
    detail: str = ""


def analyze_audio(file_path: Path) -> AudioAnalysisResult | AudioAnalysisError:
    """Analyze an MP3 file for style reference.

    Runs Whisper transcription + pydub feature extraction and generates
    a Spanish style description suitable for Lyria 3 prompts.

    Args:
        file_path: Path to the MP3 file to analyze.

    Returns:
        AudioAnalysisResult on success, AudioAnalysisError on failure.
    """
    result = AudioAnalysisResult()

    # 1. pydub analysis (duration, energy)
    try:
        pydub_result = _analyze_with_pydub(file_path)
        result.duration_seconds = pydub_result["duration"]
        result.energy = pydub_result["energy"]
        result.estimated_tempo = pydub_result["tempo"]
    except Exception as exc:
        logger.warning("pydub analysis failed, using defaults: %s", exc)

    # 2. Whisper transcription
    try:
        whisper_result = _transcribe_with_whisper(file_path)
        result.language = whisper_result["language"]
        result.transcript = whisper_result["text"]
    except Exception as exc:
        logger.warning("Whisper transcription failed: %s", exc)
        # Non-fatal — we can still generate a basic description

    # 3. Build style description
    result.style_description = _build_style_description(result)

    logger.info(
        "Audio analysis complete: lang=%s, duration=%.1fs, energy=%s, tempo=%s",
        result.language, result.duration_seconds, result.energy, result.estimated_tempo,
    )
    return result


def _analyze_with_pydub(file_path: Path) -> dict[str, Any]:
    """Extract duration, energy level, and estimated tempo from MP3."""
    from pydub import AudioSegment
    from pydub.utils import make_chunks

    audio = AudioSegment.from_mp3(str(file_path))
    duration = audio.duration_seconds

    # RMS-based energy: sample every 100ms chunks
    chunk_ms = 100
    chunks = make_chunks(audio, chunk_ms) if duration > 0.2 else [audio]
    rms_values = [chunk.rms for chunk in chunks if chunk.rms > 0]
    avg_rms = float(np.mean(rms_values)) if rms_values else 0.0

    # Normalize energy: most music RMS is between 500-4000
    if avg_rms < 800:
        energy = "baja"
    elif avg_rms < 2500:
        energy = "media"
    else:
        energy = "alta"

    # Crude tempo estimation from zero-crossing rate
    samples = np.array(audio.get_array_of_samples(), dtype=np.float64)
    if len(samples) > 1:
        zcr = float(np.sum(np.abs(np.diff(np.sign(samples)))) / (2 * len(samples)))
        if zcr < 0.05:
            tempo = "lento"
        elif zcr < 0.12:
            tempo = "medio"
        else:
            tempo = "rápido"
    else:
        tempo = "medio"

    return {"duration": duration, "energy": energy, "tempo": tempo}


def _transcribe_with_whisper(file_path: Path) -> dict[str, str]:
    """Transcribe audio with Whisper, returning language and text."""
    import whisper

    model_size = getattr(settings, "WHISPER_MODEL", "base")
    logger.info("Loading Whisper model '%s'...", model_size)
    model = whisper.load_model(model_size)

    result = model.transcribe(
        str(file_path),
        language=None,  # auto-detect
        fp16=False,
    )

    language = result.get("language", "es")
    text = result.get("text", "").strip()
    return {"language": language, "text": text}


def _build_style_description(result: AudioAnalysisResult) -> str:
    """Build a Spanish style description from analysis results."""
    parts: list[str] = ["Estilo musical de referencia:"]

    # Energy → dynamic description
    if result.energy == "baja":
        parts.append("canción íntima y suave, interpretación delicada")
    elif result.energy == "alta":
        parts.append("canción enérgica y potente, interpretación intensa")
    else:
        parts.append("canción equilibrada, interpretación expresiva")

    # Tempo
    tempo_map = {"lento": "tempo lento y pausado", "medio": "tempo moderado", "rápido": "tempo rápido y dinámico"}
    parts.append(tempo_map.get(result.estimated_tempo, "tempo moderado"))

    # Duration context
    if result.duration_seconds:
        mins = int(result.duration_seconds // 60)
        secs = int(result.duration_seconds % 60)
        parts.append(f"duración aproximada {mins}:{secs:02d}")

    # Language
    lang_map = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés"}
    lang_name = lang_map.get(result.language, result.language)
    parts.append(f"cantada en {lang_name}")

    # Transcript sample (first 300 chars for context)
    if result.transcript:
        sample = result.transcript[:300]
        parts.append(f"letra de ejemplo: \"{sample}\"")

    return ". ".join(parts) + "."
