"""Job state machine with transition validation."""

from __future__ import annotations


class InvalidTransitionError(ValueError):
    """Raised when an invalid job status transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status} → {to_status}")


class JobStateMachine:
    """Validates and tracks job status transitions.

    States: queued → lyrics_generating → music_generating → processing → complete
                                                              ↓
                                                            failed
    """

    transitions: dict[str, list[str]] = {
        "queued": ["lyrics_generating"],
        "lyrics_generating": ["music_generating", "failed"],
        "music_generating": ["processing", "failed"],
        "processing": ["complete", "failed"],
        "complete": [],
        "failed": [],
    }

    @classmethod
    def validate(cls, from_status: str, to_status: str) -> None:
        """Validate a state transition. Raises InvalidTransitionError if invalid."""
        allowed = cls.transitions.get(from_status, [])
        if to_status not in allowed:
            raise InvalidTransitionError(from_status, to_status)

    @classmethod
    def is_valid_transition(cls, from_status: str, to_status: str) -> bool:
        """Return True if the transition is valid."""
        return to_status in cls.transitions.get(from_status, [])

    @classmethod
    def possible_transitions(cls, status: str) -> list[str]:
        """Return the list of valid target states from the given status."""
        return list(cls.transitions.get(status, []))
