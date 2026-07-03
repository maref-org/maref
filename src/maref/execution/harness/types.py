from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HarnessStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class HarnessConfig:
    harness_type: str = "unified"
    level: str = "L1"
    round_id: str = ""
    duration_minutes: float = 0.0
    token_budget: int = 0
    max_workers: int = 4
    timeout_seconds: int = 300
    retry_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.extra, dict):
            return
        self.extra = {}


@dataclass
class HarnessResult:
    harness_type: str = "unified"
    round_id: str = ""
    status: HarnessStatus = HarnessStatus.SUCCEEDED
    passed: bool = True
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: Any = None
