from __future__ import annotations

from enum import Enum, auto

__all__ = [
    "EvolutionState",
    "SafetyLevel",
    "ENTROPY_LEVELS",
    "GRAY_CODE",
    "MAX_ENTROPY",
    "STATE_NAMES",
    "VALID_TRANSITIONS",
    "compute_valid_transitions",
    "hamming_distance",
]


class EvolutionState(Enum):
    IDLE = auto()
    EVOLVING = auto()
    STABLE = auto()
    DEGRADED = auto()
    RECOVERING = auto()
    EMERGENCY = auto()

class SafetyLevel(Enum):
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    NONE = auto()

# ── Gray code state machine constants ──────────────────────────────

ENTROPY_LEVELS: dict[str, int] = {
    "INIT": 0, "LEARN": 1, "PLAN": 2, "ACT": 3,
    "REVIEW": 2, "REFINE": 2, "HEAL": 1, "HALT": 0,
}

GRAY_CODE: dict[str, int] = {
    "INIT": 0b0000, "LEARN": 0b0001, "PLAN": 0b0011, "ACT": 0b0010,
    "REVIEW": 0b0110, "REFINE": 0b0111, "HEAL": 0b0101, "HALT": 0b0100,
}

MAX_ENTROPY: int = 3

STATE_NAMES: list[str] = [
    "INIT", "LEARN", "PLAN", "ACT",
    "REVIEW", "REFINE", "HEAL", "HALT",
]


def compute_valid_transitions(state: str) -> list[str]:
    transitions = {
        "INIT": ["LEARN"],
        "LEARN": ["INIT", "PLAN"],
        "PLAN": ["LEARN", "ACT"],
        "ACT": ["PLAN", "REVIEW"],
        "REVIEW": ["ACT", "REFINE"],
        "REFINE": ["REVIEW", "HEAL"],
        "HEAL": ["REFINE", "HALT"],
        "HALT": [],
    }
    return transitions.get(state, [])


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


VALID_TRANSITIONS: dict[str, list[str]] = {
    "INIT": ["LEARN"],
    "LEARN": ["INIT", "PLAN"],
    "PLAN": ["LEARN", "ACT"],
    "ACT": ["PLAN", "REVIEW"],
    "REVIEW": ["ACT", "REFINE"],
    "REFINE": ["REVIEW", "HEAL"],
    "HEAL": ["REFINE", "HALT"],
    "HALT": [],
}
