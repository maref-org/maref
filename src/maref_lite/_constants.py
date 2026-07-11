from __future__ import annotations

from enum import Enum, auto
from typing import Final


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