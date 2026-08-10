"""Verifier protocol — evaluation interface for MAREF Loop verifiers."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Verdict:
    """Evaluation result from a single verifier."""

    passed: bool
    score: float  # 0.0 (worst) to 1.0 (best)
    confidence: float  # 0.0 (uncertain) to 1.0 (certain)
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    verifier_name: str = ""


@dataclass
class EvaluationRequest:
    """Input to a verifier."""

    item_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class Verifier(ABC):
    """Base class for all MAREF verifiers."""

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        self._name = name
        self._version = version

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @abstractmethod
    async def evaluate(self, request: EvaluationRequest) -> Verdict:
        """Evaluate the request and return a verdict."""

    def get_capabilities(self) -> list[str]:
        """Tags describing what this verifier can evaluate."""
        return []


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class CrossValidationResult:
    """Result from running multiple verifiers on the same input."""

    request_id: str = field(default_factory=_new_id)
    verdicts: list[Verdict] = field(default_factory=list)
    consensus_passed: bool | None = None
    consensus_score: float = 0.0
    consensus_confidence: float = 0.0
    agreement_ratio: float = 0.0
    divergences: list[dict[str, Any]] = field(default_factory=list)
    collaboration: dict[str, Any] | None = None

    @property
    def verifier_count(self) -> int:
        return len(self.verdicts)

    @property
    def passed_count(self) -> int:
        return sum(1 for v in self.verdicts if v.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for v in self.verdicts if not v.passed)
