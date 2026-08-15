"""MAREF — Multi-Agent Reliable Execution Framework."""

from maref.agent_card_config import AgentCardConfig, get_default_card_config
from maref.governance.constants import compute_valid_transitions, hamming_distance
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition

__version__ = "0.54.0"
__all__ = [
    "AgentCardConfig",
    "get_default_card_config",
    "GovernanceState",
    "GovernanceStateMachine",
    "StateTransition",
    "StateMachineSnapshot",
    "hamming_distance",
    "compute_valid_transitions",
]
