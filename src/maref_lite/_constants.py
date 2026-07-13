from enum import Enum, auto


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
