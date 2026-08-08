"""Tests for app/voice/registry.py — VoiceConfig dict registry."""

from __future__ import annotations

import pytest

from app.models import VoiceConfig
from app.voice.registry import VOICE_REGISTRY, get_voice, validate_registry


def test_registry_has_female_entry() -> None:
    """VOICE_REGISTRY should contain a 'female' entry."""
    assert "female" in VOICE_REGISTRY
    entry = VOICE_REGISTRY["female"]
    assert isinstance(entry, VoiceConfig)
    assert entry.id == "female"
    assert entry.gender == "female"
    assert entry.label == "Voz Femenina"
    assert "femenina" in entry.prompt_es


def test_registry_has_male_entry() -> None:
    """VOICE_REGISTRY should contain a 'male' entry."""
    assert "male" in VOICE_REGISTRY
    entry = VOICE_REGISTRY["male"]
    assert isinstance(entry, VoiceConfig)
    assert entry.id == "male"
    assert entry.gender == "male"
    assert entry.label == "Voz Masculina"
    assert "masculino" in entry.prompt_es


def test_registry_has_exactly_seven_entries() -> None:
    """VOICE_REGISTRY should have exactly 7 entries (RQ-VOI-01)."""
    assert len(VOICE_REGISTRY) == 7


def test_registry_contains_all_new_regional_voices() -> None:
    """VOICE_REGISTRY should include the 5 new regional voices (RQ-VOI-01)."""
    for voice_id in (
        "es-latino-male",
        "es-espana-male",
        "es-espana-female",
        "es-latina-female",
        "es-espana-child",
    ):
        assert voice_id in VOICE_REGISTRY
        entry = VOICE_REGISTRY[voice_id]
        assert isinstance(entry, VoiceConfig)
        assert entry.id == voice_id
        assert entry.label
        assert entry.gender in {"male", "female", "child"}
        assert entry.prompt_es


def test_registry_has_no_legacy_duo_or_children() -> None:
    """VOICE_REGISTRY must not contain legacy 'duo' or 'children' (RQ-VOI-02)."""
    assert "duo" not in VOICE_REGISTRY
    assert "children" not in VOICE_REGISTRY


def test_exact_label_casing_female() -> None:
    """Female label must keep exact casing 'Voz Femenina' (D1)."""
    assert VOICE_REGISTRY["female"].label == "Voz Femenina"


def test_exact_label_casing_male() -> None:
    """Male label must keep exact casing 'Voz Masculina' (D1)."""
    assert VOICE_REGISTRY["male"].label == "Voz Masculina"


def test_get_voice_returns_config() -> None:
    """get_voice() should return the VoiceConfig for known voices."""
    female = get_voice("female")
    assert female is not None
    assert female.id == "female"

    male = get_voice("male")
    assert male is not None
    assert male.id == "male"


def test_get_voice_returns_none_for_unknown() -> None:
    """get_voice() should return None for unknown voice IDs."""
    assert get_voice("celebrity_x") is None
    assert get_voice("") is None
    assert get_voice("robot") is None


def test_get_voice_is_case_sensitive() -> None:
    """get_voice() should be case-sensitive (lowercase only)."""
    assert get_voice("Female") is None
    assert get_voice("MALE") is None


def test_validate_registry_passes_for_healthy() -> None:
    """validate_registry() should not raise for valid registry."""
    validate_registry()  # should not raise


def test_validate_registry_fails_on_empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """validate_registry() should raise ValueError for empty registry."""
    monkeypatch.setattr("app.voice.registry.VOICE_REGISTRY", {})
    with pytest.raises(ValueError, match="empty"):
        validate_registry()


def test_validate_registry_fails_on_missing_id_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """validate_registry() should raise ValueError if an entry lacks 'id'."""
    bad_registry = {
        "female": VoiceConfig(id="female", label="Voz Femenina", gender="female", prompt_es="test"),
        "male": VoiceConfig(id="male", label="Voz Masculina", gender="male", prompt_es="test"),
        "invalid": "not_a_voice_config",
    }
    monkeypatch.setattr("app.voice.registry.VOICE_REGISTRY", bad_registry)
    with pytest.raises(ValueError, match="invalid"):
        validate_registry()
