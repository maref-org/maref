from __future__ import annotations

import warnings
from typing import Any

from maref.governance.verifier_consensus import ConsensusStrategy, VerifierConsensus
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry

_DEPRECATION_MSG = (
    "MAREFLoop is deprecated and will be removed in v1.0. "
    "Use `maref.loop` package instead: "
    "ConvergentLoop, ExploratoryLoop, InteractiveLoop with LoopGovernanceBridge."
)


class MAREFLoop:
    def __init__(self) -> None:
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        self._registry = VerifierRegistry()
        self._consensus = VerifierConsensus(self._registry)
        self._history: list[dict[str, Any]] = []

    def register_verifier(self, name: str, model: str, methodology: str, accuracy: float = 0.0) -> None:
        entry = VerifierEntry(
            name=name,
            model=model,
            methodology=methodology,
            accuracy=accuracy,
        )
        self._registry.register(entry)

    def check(self, action: str, context: dict[str, Any]) -> dict[str, Any]:
        result = self._consensus.evaluate(
            item={"action": action, "context": context},
            strategy=ConsensusStrategy.WEIGHTED_MAJORITY,
        )
        entry = {
            "action": action,
            "passed": result.passed,
            "agreement": result.agreement,
            "votes": len(result.votes),
        }
        self._history.append(entry)
        return entry

    def record(self, action: str, outcome: dict[str, Any]) -> None:
        for v in self._registry.list_active():
            correct = outcome.get("success", False)
            self._registry.record_evaluation(v.name, correct)

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def get_verifiers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": v.name,
                "model": v.model,
                "methodology": v.methodology,
                "accuracy": v.accuracy,
                "status": v.status.value,
            }
            for v in self._registry.list_all()
        ]

    def detect_drift(self) -> list[dict[str, Any]]:
        return self._registry.detect_drift(threshold=0.1)
