"""FastAPI router exposing the voice registry.

Provides ``GET /api/voices`` as the single source of truth for the frontend
voice selector (RQ-VOICE-01). JWT-protected like sibling project routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models import VoiceInfo
from app.voice import get_available_voices

router = APIRouter(prefix="/api")


@router.get("/voices", response_model=list[VoiceInfo])
async def get_voices() -> list[VoiceInfo]:
    """Return the full voice registry as {id, label, gender} entries.

    The frontend voice selector MUST be fed by this endpoint rather than
    hard-coding its own options (RQ-VOICE-01).
    """
    return [
        VoiceInfo(id=voice.id, label=voice.label, gender=voice.gender)
        for voice in get_available_voices()
    ]
