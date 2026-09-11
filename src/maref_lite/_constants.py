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


ENTROPY_LEVELS: dict[str, int] = {
    "INIT": 0,
    "LEARN": 1,
    "PLAN": 2,
    "ACT": 3,
    "REVIEW": 2,
    "REFINE": 2,
    "HEAL": 1,
    "HALT": 0,
}
GRAY_CODE: dict[str, int] = {
    "INIT": 0,
    "LEARN": 1,
    "PLAN": 3,
    "ACT": 2,
    "REVIEW": 6,
    "REFINE": 7,
    "HEAL": 5,
    "HALT": 4,
}
MAX_ENTROPY: int = 3
STATE_NAMES: list[str] = ["INIT", "LEARN", "PLAN", "ACT", "REVIEW", "REFINE", "HEAL", "HALT"]


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
