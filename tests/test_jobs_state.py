"""Tests for app/jobs/state.py — JobStateMachine."""

from __future__ import annotations

import pytest

from app.jobs.state import JobStateMachine, InvalidTransitionError

# ── Valid transitions ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("queued", "lyrics_generating"),
        ("queued", "failed"),
        ("lyrics_generating", "music_generating"),
        ("lyrics_generating", "failed"),
        ("music_generating", "processing"),
        ("music_generating", "failed"),
        ("processing", "complete"),
        ("processing", "failed"),
    ],
)
def test_valid_transitions(from_status: str, to_status: str) -> None:
    """All valid state transitions should pass validation."""
    JobStateMachine.validate(from_status, to_status)  # should not raise


# ── Invalid transitions ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        # Can't go backwards
        ("lyrics_generating", "queued"),
        ("music_generating", "lyrics_generating"),
        ("processing", "music_generating"),
        ("complete", "processing"),
        # Can't skip stages
        ("queued", "music_generating"),
        ("queued", "processing"),
        ("queued", "complete"),
        # Terminal states can't transition
        ("complete", "failed"),
        ("complete", "queued"),
        ("complete", "lyrics_generating"),
        ("failed", "queued"),
        ("failed", "complete"),
        ("failed", "lyrics_generating"),
        # Self-transitions
        ("queued", "queued"),
        ("complete", "complete"),
        ("failed", "failed"),
    ],
)
def test_invalid_transitions_raise_error(from_status: str, to_status: str) -> None:
    """Invalid state transitions should raise InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError):
        JobStateMachine.validate(from_status, to_status)


# ── Transitions dict structure ───────────────────────────────────────────────


def test_transitions_covers_all_states() -> None:
    """All defined statuses should appear in transitions."""
    all_statuses = {
        "queued", "lyrics_generating", "music_generating",
        "processing", "complete", "failed",
    }
    assert set(JobStateMachine.transitions.keys()) == all_statuses


def test_transition_targets_are_valid() -> None:
    """All transition targets should be known statuses."""
    valid = {
        "queued", "lyrics_generating", "music_generating",
        "processing", "complete", "failed",
    }
    for from_status, targets in JobStateMachine.transitions.items():
        for target in targets:
            assert target in valid, f"Invalid target {target} from {from_status}"


def test_terminal_states_have_no_transitions() -> None:
    """Terminal states (complete, failed) should have empty transition lists."""
    assert JobStateMachine.transitions["complete"] == []
    assert JobStateMachine.transitions["failed"] == []


# ── Utility methods ──────────────────────────────────────────────────────────


def test_is_valid_transition_true() -> None:
    """is_valid_transition should return True for valid transitions."""
    assert JobStateMachine.is_valid_transition("queued", "lyrics_generating")


def test_is_valid_transition_false() -> None:
    """is_valid_transition should return False for invalid transitions."""
    assert not JobStateMachine.is_valid_transition("complete", "queued")
    assert not JobStateMachine.is_valid_transition("failed", "complete")


def test_possible_transitions_returns_list() -> None:
    """possible_transitions should return the list of valid targets."""
    targets = JobStateMachine.possible_transitions("queued")
    assert targets == ["lyrics_generating", "failed"]


def test_possible_transitions_terminal() -> None:
    """Terminal states should have empty possible transitions."""
    assert JobStateMachine.possible_transitions("complete") == []
    assert JobStateMachine.possible_transitions("failed") == []
