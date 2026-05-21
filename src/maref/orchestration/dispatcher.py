from __future__ import annotations

from dataclasses import dataclass

from maref.identity.did_registry import AgentDID
from maref.orchestration.decomposer import SubTask


@dataclass
class DispatchResult:
    agent_did: AgentDID
    task_id: str
    confidence: float
    match_dimensions: dict[str, float]


class AgentDispatcher:
    def __init__(self) -> None:
        self._agent_capabilities: dict[AgentDID, list[str]] = {}
        self._agent_performance: dict[AgentDID, float] = {}
        self._dimension_weights = {
            "capability_match": 0.35,
            "performance_history": 0.30,
            "trust_score": 0.20,
            "current_load": 0.10,
            "specialization": 0.05,
        }

    def register_agent(self, did: AgentDID, capabilities: list[str]) -> None:
        self._agent_capabilities[did] = capabilities
        self._agent_performance[did] = 0.7

    def update_performance(self, did: AgentDID, score: float) -> None:
        self._agent_performance[did] = score

    def dispatch(self, task: SubTask) -> DispatchResult | None:
        best_did: AgentDID | None = None
        best_score = -1.0
        best_dimensions: dict[str, float] = {}

        for did, caps in self._agent_capabilities.items():
            dimensions = self._evaluate_match(did, task, caps)
            total = sum(w * dimensions[k] for k, w in self._dimension_weights.items())
            if total > best_score:
                best_score = total
                best_did = did
                best_dimensions = dimensions

        if best_did is None:
            return None
        return DispatchResult(
            agent_did=best_did,
            task_id=task.task_id,
            confidence=best_score,
            match_dimensions=best_dimensions,
        )

    def _evaluate_match(
        self, did: AgentDID, task: SubTask, agent_caps: list[str]
    ) -> dict[str, float]:
        matched = sum(1 for c in task.required_capabilities if c in agent_caps)
        capability_match = matched / max(len(task.required_capabilities), 1)
        performance = self._agent_performance.get(did, 0.5)
        trust_score = 0.7
        current_load = 0.3
        specialization = 0.5 if task.required_capabilities else 0.5
        return {
            "capability_match": capability_match,
            "performance_history": performance,
            "trust_score": trust_score,
            "current_load": current_load,
            "specialization": specialization,
        }
