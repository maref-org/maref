from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Any


class VerifierStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    DEPRECATED = "deprecated"


@dataclass
class VerifierEntry:
    name: str
    model: str
    methodology: str
    status: VerifierStatus = VerifierStatus.ACTIVE
    accuracy: float = 0.0
    recall: float = 0.0
    bias: float = 0.0
    last_evaluation: str = ""
    total_calls: int = 0
    correct_calls: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    @property
    def precision(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.correct_calls / self.total_calls

    def record_call(self, correct: bool) -> None:
        self.total_calls += 1
        if correct:
            self.correct_calls += 1
        self.accuracy = self.precision


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[str, VerifierEntry] = {}

    def register(self, entry: VerifierEntry) -> None:
        self._verifiers[entry.name] = entry

    def unregister(self, name: str) -> None:
        self._verifiers.pop(name, None)

    def get(self, name: str) -> VerifierEntry | None:
        return self._verifiers.get(name)

    def list_active(self) -> list[VerifierEntry]:
        return [v for v in self._verifiers.values() if v.status == VerifierStatus.ACTIVE]

    def list_all(self) -> list[VerifierEntry]:
        return list(self._verifiers.values())

    def get_accuracy(self, name: str) -> float:
        entry = self._verifiers.get(name)
        if entry is None:
            return 0.0
        return entry.accuracy

    def get_bias(self, name: str) -> float:
        entry = self._verifiers.get(name)
        if entry is None:
            return 1.0
        return entry.bias

    def record_evaluation(self, name: str, correct: bool) -> None:
        entry = self._verifiers.get(name)
        if entry is not None:
            entry.record_call(correct)

    def set_status(self, name: str, status: VerifierStatus) -> None:
        entry = self._verifiers.get(name)
        if entry is not None:
            entry.status = status

    def detect_drift(self, threshold: float = 0.1) -> list[dict[str, Any]]:
        drifted: list[dict[str, Any]] = []
        for entry in self._verifiers.values():
            if entry.accuracy < threshold:
                drifted.append({
                    "name": entry.name,
                    "accuracy": entry.accuracy,
                    "threshold": threshold,
                    "recommendation": "recalibrate or deprecate",
                })
        return drifted
