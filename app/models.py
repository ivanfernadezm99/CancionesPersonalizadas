"""Shared Pydantic models for the Canciones Automáticas API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Parameters for generating a personalized song."""

    recipient: str = Field(..., min_length=1, max_length=100, description="Name of the recipient")
    relationship: str = Field(..., min_length=1, max_length=50, description="Relationship to recipient")
    occasion: str = Field(..., min_length=1, max_length=100, description="Occasion for the song")
    genre: str = Field(..., min_length=1, max_length=50, description="Music genre")
    mood: str = Field(..., min_length=1, max_length=50, description="Song mood")
    story: str | None = Field(None, max_length=2000, description="Optional personal story")
    voice: str = Field(..., min_length=1, max_length=50, description="Voice ID for generation")


class Verse(BaseModel):
    """A single verse (estrofa) in the song lyrics."""

    number: int = Field(..., ge=1, description="Verse number")
    lines: list[str] = Field(..., min_length=1, max_length=10, description="Lines of the verse")


class Chorus(BaseModel):
    """The chorus (estribillo) of the song."""

    lines: list[str] = Field(..., min_length=1, max_length=10, description="Lines of the chorus")


class Bridge(BaseModel):
    """Optional bridge (puente) in the song."""

    lines: list[str] = Field(..., min_length=1, max_length=10, description="Lines of the bridge")


class LyricsResult(BaseModel):
    """Complete lyrics output from an LLM provider."""

    verses: list[Verse] = Field(..., min_length=1, max_length=5, description="Song verses")
    chorus: Chorus = Field(..., description="Song chorus")
    bridge: Bridge | None = Field(None, description="Optional bridge section")
    language: str = Field(default="es", description="Language code")
    title_suggestion: str = Field(..., min_length=1, description="Suggested song title")
    provider: str = Field(..., description="LLM provider that generated the lyrics")


class VoiceConfig(BaseModel):
    """Configuration for a voice used in music generation."""

    id: str = Field(..., description="Unique voice identifier")
    label: str = Field(..., description="Human-readable label")
    gender: str = Field(..., description="Gender: male or female")
    prompt_es: str = Field(..., description="Spanish prompt descriptor for Lyria 3")


class JobStatusResponse(BaseModel):
    """Response model for job status queries."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress 0.0 to 1.0")
    estimated_remaining_seconds: int = Field(default=0, ge=0, description="Estimated seconds remaining")
    error: str | None = Field(None, description="Error message if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")


class JobCreateResponse(BaseModel):
    """Response model for job creation (POST /api/generate)."""

    job_id: str = Field(..., description="Unique job identifier (UUID v4)")
    status: str = Field(default="queued", description="Initial job status")
    estimated_total_seconds: int = Field(default=180, description="Estimated total processing time")
    endpoints: dict[str, str] = Field(..., description="Status and stream endpoint URLs")
