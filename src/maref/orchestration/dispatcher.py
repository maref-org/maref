from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.identity.did_registry import AgentDID
from maref.orchestration.decomposer import SubTask
from maref.recursive.agent_health import AgentHealthMonitor
from maref.recursive.trust_engine_v2 import TrustEngineV2


@dataclass
class DispatchResult:
    agent_did: AgentDID
    task_id: str
    confidence: float
    match_dimensions: dict[str, float]


class AgentDispatcher:
    def __init__(
        self,
        trust_engine: TrustEngineV2 | None = None,
        health_monitor: AgentHealthMonitor | None = None,
    ) -> None:
        self._agent_capabilities: dict[AgentDID, list[str]] = {}
        self._agent_performance: dict[AgentDID, float] = {}
        self._trust_engine = trust_engine
        self._health_monitor = health_monitor
        self._dimension_weights = {
            "capability_match": 0.35,
            "performance_history": 0.30,
            "trust_score": 0.20,
            "current_load": -0.10,  # get_load_ratio 越大负载越重，负载越高越不优先
            "specialization": 0.05,
        }

    def register_agent(self, did: AgentDID, capabilities: list[str]) -> None:
        self._agent_capabilities[did] = capabilities
        self._agent_performance[did] = 0.7
        # Mirror registration in downstream systems if present
        if self._trust_engine is not None:
            self._trust_engine.register_agent(did.did_string)
        if self._health_monitor is not None:
            self._health_monitor.register(did.did_string)

    def unregister_agent(self, did: AgentDID) -> bool:
        """Remove an agent's capability registration.

        Args:
            did: The MAREF DID to unregister.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        found = did in self._agent_capabilities
        self._agent_capabilities.pop(did, None)
        self._agent_performance.pop(did, None)
        return found

    def update_performance(self, did: AgentDID, score: float) -> None:
        self._agent_performance[did] = score

    def dispatch(self, task: SubTask) -> DispatchResult | None:
        result = self._select_best_agent(task)
        if result is None:
            return None
        # Update health monitor: increment task count for selected agent
        if self._health_monitor is not None:
            self._health_monitor.increment_tasks(result.agent_did.did_string)
        return result

    def _select_best_agent(self, task: SubTask) -> DispatchResult | None:
        """Core selection logic without side effects (load increment)."""
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

    def dispatch_with_bypass(
        self,
        task: SubTask,
        reliability_matrix: Any | None = None,
        observer_id: str = "",
    ) -> DispatchResult | None:
        """Dispatch that respects ReliabilityMatrix bypass decisions.

        If *reliability_matrix* is provided and an agent is bypassed for this
        task type, it is excluded from consideration.
        """
        best_did: AgentDID | None = None
        best_score = -1.0
        best_dimensions: dict[str, float] = {}

        for did, caps in self._agent_capabilities.items():
            if reliability_matrix is not None and observer_id:
                task_type = task.description
                if reliability_matrix.should_bypass(observer_id, did.did_string, task_type):
                    continue

            dimensions = self._evaluate_match(did, task, caps)
            total = sum(w * dimensions[k] for k, w in self._dimension_weights.items())
            if total > best_score:
                best_score = total
                best_did = did
                best_dimensions = dimensions

        if best_did is None:
            return None

        if self._health_monitor is not None:
            self._health_monitor.increment_tasks(best_did.did_string)

        return DispatchResult(
            agent_did=best_did,
            task_id=task.task_id,
            confidence=best_score,
            match_dimensions=best_dimensions,
        )

    def release_after_execution(
        self,
        result: DispatchResult,
        execution_success: bool = True,
    ) -> None:
        """Release agent load after task execution completes.

        Call this from the orchestrator / saga when a dispatched task
        finishes (success or failure) so the load counter is decremented.
        """
        self.release_agent(result.agent_did)
        if self._trust_engine is not None:
            self._trust_engine.record_task(
                result.agent_did.did_string,
                result.task_id,
                success=execution_success,
                quality=result.confidence,
                latency_ms=0.0,
            )

    def release_agent(self, did: AgentDID) -> None:
        """Call when a task finishes to decrement the agent's load counter."""
        if self._health_monitor is not None:
            self._health_monitor.decrement_tasks(did.did_string)

    def _evaluate_match(
        self, did: AgentDID, task: SubTask, agent_caps: list[str]
    ) -> dict[str, float]:
        matched = sum(1 for c in task.required_capabilities if c in agent_caps)
        capability_match = matched / max(len(task.required_capabilities), 1)
        performance = self._agent_performance.get(did, 0.5)

        # Phase 2.2: live trust score from TrustEngineV2
        trust_score = 0.7
        if self._trust_engine is not None:
            score_obj = self._trust_engine.get_score(did.did_string)
            if score_obj is not None:
                trust_score = score_obj.overall_trust / 100.0

        # Phase 2.2: live load ratio from AgentHealthMonitor
        current_load = 0.3
        if self._health_monitor is not None:
            current_load = self._health_monitor.get_load_ratio(did.did_string)

        # 专精度 = 能力是否完全覆盖任务所需；完全覆盖视为该领域专家，否则非专精
        specialization = 1.0 if capability_match >= 1.0 else 0.0
        return {
            "capability_match": capability_match,
            "performance_history": performance,
            "trust_score": trust_score,
            "current_load": current_load,
            "specialization": specialization,
        }
