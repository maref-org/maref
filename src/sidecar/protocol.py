from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    OBSERVING = "observing"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    ERROR = "error"
    DEGRADED = "degraded"
    HALT = "halt"


class ObservationType(str, Enum):
    STATE = "state"
    ENTROPY = "entropy"
    METRIC = "metric"
    ANOMALY = "anomaly"


@dataclass
class AgentId:
    name: str
    namespace: str = "default"

    def __hash__(self) -> int:
        return hash((self.name, self.namespace))

    def __str__(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass
class EntropyReading:
    agent_id: AgentId
    value: float = 0.0
    level: str = "normal"
    timestamp: float = field(default_factory=time.time)


@dataclass
class StateSnapshot:
    agent_id: AgentId
    state: AgentState = AgentState.IDLE
    current_task: str = ""
    task_progress: float = 0.0
    pending_messages: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class Observation:
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentId | None = None
    type: ObservationType = ObservationType.STATE
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
