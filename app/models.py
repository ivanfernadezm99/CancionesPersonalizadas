"""Shared Pydantic models for the Canciones Automáticas API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _validate_voice(v: str | None) -> str | None:
    """Fail-fast voice validation against the registry (RQ-VOICE-02, D5).

    Pydantic v2 runs validators on ``None`` too, so this MUST return the
    value unchanged when it is ``None`` (e.g. PATCH without a voice field).
    The registry is imported lazily to avoid a circular import between
    ``app.models`` and ``app.voice.registry``.
    """
    if v is None:
        return v
    from app.voice.registry import get_voice

    if get_voice(v) is None:
        from app.voice.registry import VOICE_REGISTRY

        valid = ", ".join(VOICE_REGISTRY.keys())
        raise ValueError(f"Unknown voice '{v}'. Valid options: {valid}")
    return v


class GenerateRequest(BaseModel):
    """Parameters for generating a personalized song."""

    recipient: str = Field(..., min_length=1, max_length=100, description="Name of the recipient")
    relationship: str = Field(
        ..., min_length=1, max_length=50, description="Relationship to recipient"
    )
    occasion: str = Field(..., min_length=1, max_length=100, description="Occasion for the song")
    genre: str = Field(..., min_length=1, max_length=50, description="Music genre")
    mood: str = Field(..., min_length=1, max_length=50, description="Song mood")
    story: str | None = Field(None, max_length=2000, description="Optional personal story")
    voice: str = Field(
        default="female", min_length=1, max_length=50, description="Voice ID for generation"
    )
    reference_song: str | None = Field(
        None,
        max_length=200,
        description="Optional reference song for style (e.g. 'Bachata Rosa - Juan Luis Guerra')",
    )
    reference_description: str | None = Field(
        None,
        max_length=1000,
        description="Auto-generated style description from audio reference",
    )
    idea: str | None = Field(
        None,
        max_length=2000,
        description="Optional free-text thematic seed for lyrics (RQ-LYR-07)",
    )

    _validate_voice = field_validator("voice")(_validate_voice)


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
    gender: str = Field(..., description="Gender: male, female, or child")
    prompt_es: str = Field(..., description="Spanish prompt descriptor for Lyria 3")


class VoiceInfo(BaseModel):
    """Public voice info exposed by GET /api/voices (RQ-VOICE-01)."""

    id: str = Field(..., description="Unique voice identifier")
    label: str = Field(..., description="Human-readable label")
    gender: str = Field(..., description="Gender: male, female, or child")


class JobStatusResponse(BaseModel):
    """Response model for job status queries."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress 0.0 to 1.0")
    estimated_remaining_seconds: int = Field(
        default=0, ge=0, description="Estimated seconds remaining"
    )
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


# ── Song Project Models ───────────────────────────────────────────────────────


class SongProjectCreate(BaseModel):
    """Create a new iterative song project."""

    recipient: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(default="pareja", min_length=1, max_length=50)
    genre: str = Field(default="balada romántica", min_length=1, max_length=50)
    mood: str = Field(default="romántico", min_length=1, max_length=50)
    voice: str = Field(default="male", min_length=1, max_length=50)
    reference_song: str | None = Field(
        None,
        max_length=200,
        description="Optional reference song for style (e.g. 'Bachata Rosa - Juan Luis Guerra')",
    )
    reference_description: str | None = Field(
        None,
        max_length=1000,
        description="Auto-generated style description from uploaded audio reference",
    )
    idea: str | None = Field(
        None,
        max_length=2000,
        description="Optional free-text idea used as a thematic seed for draft lyrics (RQ-IDEA-01)",
    )
    chaining_enabled: bool = Field(
        default=False, description="Use clip chaining for the final song instead of pro-preview"
    )

    _validate_voice = field_validator("voice")(_validate_voice)


class StoryFragmentAdd(BaseModel):
    """Add a story fragment to a project."""

    text: str = Field(
        ..., min_length=1, max_length=2000, description="Story fragment to accumulate"
    )


class ReplaceFragmentsRequest(BaseModel):
    """Replace the full story fragment list of a project."""

    fragments: list[str] = Field(
        default_factory=list,
        description="Complete story fragment list, replacing any existing fragments",
    )


class SongProjectUpdate(BaseModel):
    """Update project settings or add a story fragment."""

    genre: str | None = Field(None, min_length=1, max_length=50)
    mood: str | None = Field(None, min_length=1, max_length=50)
    voice: str | None = Field(None, min_length=1, max_length=50)
    reference_song: str | None = Field(None, max_length=200)
    reference_description: str | None = Field(None, max_length=1000)
    idea: str | None = Field(
        None, max_length=2000, description="Optional free-text idea (RQ-IDEA-01)"
    )
    chaining_enabled: bool | None = Field(
        None, description="Enable clip chaining for final song generation"
    )
    fragment: StoryFragmentAdd | None = None

    _validate_voice = field_validator("voice")(_validate_voice)


class StoryFragmentResponse(BaseModel):
    """A story fragment in a project."""

    id: int
    text: str
    sort_order: int
    created_at: str


class ProjectPreview(BaseModel):
    """A generated preview for a project."""

    job_id: str
    job_type: str  # "preview" or "final"
    status: str
    created_at: str


class SongProjectResponse(BaseModel):
    """Full project response with fragments and previews."""

    id: str
    recipient: str
    relationship: str
    genre: str
    mood: str
    voice: str
    reference_song: str | None
    reference_description: str | None
    reference_audio_url: str | None = Field(
        None, description="Public URL of the stored reference audio (Suno Cover mode), if any"
    )
    idea: str | None = Field(
        None, max_length=2000, description="Optional free-text idea (RQ-IDEA-01)"
    )
    status: str
    fragments: list[StoryFragmentResponse]
    previews: list[ProjectPreview]
    created_at: str
    updated_at: str


class AudioReferenceResponse(BaseModel):
    """Response for audio reference upload and analysis."""

    project_id: str
    language: str = "es"
    transcript_preview: str = ""
    duration_seconds: float = 0.0
    energy: str = "media"
    estimated_tempo: str = "medio"
    style_description: str = ""
    reference_audio_url: str | None = None


# ── Payment Models ─────────────────────────────────────────────────────────────


class CheckoutResponse(BaseModel):
    """Response for creating a checkout preference."""

    preference_id: str = Field(..., description="Mercado Pago preference ID")
    init_point: str = Field(..., description="Mercado Pago checkout URL")
    project_id: str = Field(..., description="Project ID")
    amount: float = Field(..., ge=0, description="Amount charged")


class PaymentConfirmRequest(BaseModel):
    """Request body for payment confirmation webhook."""

    project_id: str = Field(..., description="Project being paid for")
    payment_id: str = Field(..., description="Payment transaction ID")
    status: str = Field(..., description="Payment status (approved/rejected/etc)")
    metadata: dict[str, str] | None = Field(None, description="Optional metadata from gateway")


class WebhookResponse(BaseModel):
    """Response for webhook calls."""

    success: bool = Field(..., description="Whether the webhook was processed")
    message: str = Field(..., description="Status message")
