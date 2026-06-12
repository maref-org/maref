from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HarnessStatus(Enum):
    IDLE = "idle"
    CONFIGURED = "configured"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class HarnessConfig:
    harness_type: str = "stress"
    level: str = "L1"
    duration_minutes: float = 1.0
    round_id: str = ""
    token_budget: int = 0  # 0 = unlimited
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessResult:
    harness_type: str = ""
    round_id: str = ""
    status: HarnessStatus = HarnessStatus.IDLE
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: Any = None
    timestamp: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return self.status == HarnessStatus.SUCCEEDED and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_type": self.harness_type,
            "round_id": self.round_id,
            "status": self.status.value,
            "duration_s": self.duration_s,
            "errors": self.errors[:10],
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }
