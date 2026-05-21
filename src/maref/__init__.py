"""MAREF — Multi-Agent Reliable Execution Framework."""

__version__ = "0.24.0-rc"

from maref.governance.constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    compute_valid_transitions,
    hamming_distance,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import (
    GovernanceState,
    StateMachineSnapshot,
    StateTransition,
)

__all__ = [
    "GovernanceState",
    "GovernanceStateMachine",
    "StateTransition",
    "StateMachineSnapshot",
    "ENTROPY_LEVELS",
    "GRAY_CODE",
    "MAX_ENTROPY",
    "STATE_NAMES",
    "hamming_distance",
    "compute_valid_transitions",
]
