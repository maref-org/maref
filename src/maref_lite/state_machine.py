"""Backward-compatible re-exports from maref.governance.

This module is kept for backward compatibility.
New code should import from maref.governance directly.
"""

from maref.governance.constants import (
    ENTROPY_LEVELS as _ENTROPY_INT,
)
from maref.governance.constants import (
    GRAY_CODE as _GRAY_CODE_INT,
)
from maref.governance.constants import (
    MAX_ENTROPY as _MAX_ENTROPY,
)
from maref.governance.constants import (
    STATE_NAMES as _STATE_NAMES,
)
from maref.governance.constants import (
    hamming_distance,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition

MAX_ENTROPY: int = _MAX_ENTROPY
STATE_NAMES: dict[int, str] = dict(_STATE_NAMES)

GRAY_CODE: dict[GovernanceState, tuple[int, ...]] = {
    GovernanceState(s): c for s, c in _GRAY_CODE_INT.items()
}

ENTROPY_LEVELS: dict[GovernanceState, int] = {
    GovernanceState(s): e for s, e in _ENTROPY_INT.items()
}


def get_valid_transitions() -> dict[GovernanceState, list[GovernanceState]]:
    from maref.governance.state_machine import _VALID_TRANSITIONS
    return dict(_VALID_TRANSITIONS)


VALID_TRANSITIONS: dict[GovernanceState, list[GovernanceState]] = get_valid_transitions()


__all__ = [
    "GovernanceState",
    "GovernanceStateMachine",
    "StateTransition",
    "StateMachineSnapshot",
    "ENTROPY_LEVELS",
    "GRAY_CODE",
    "MAX_ENTROPY",
    "STATE_NAMES",
    "VALID_TRANSITIONS",
    "get_valid_transitions",
    "hamming_distance",
]
