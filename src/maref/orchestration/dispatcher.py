from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.discovery.acs_schema import AgentCapabilitySchema
from maref.discovery.discovery_service import DiscoveryQuery, DiscoveryService
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


# Feature flag: ACS schema enabled (可单独关闭回滚)
_FEATURE_ACS_SCHEMA = True


class AgentDispatcher:
    def __init__(
        self,
        trust_engine: TrustEngineV2 | None = None,
        health_monitor: AgentHealthMonitor | None = None,
        discovery_service: DiscoveryService | None = None,
    ) -> None:
        self._agent_capabilities: dict[AgentDID, list[str]] = {}
        self._agent_schemas: dict[AgentDID, AgentCapabilitySchema] = {}
        self._agent_performance: dict[AgentDID, float] = {}
        self._trust_engine = trust_engine
        self._health_monitor = health_monitor
        self._discovery_service = discovery_service
        self._dimension_weights = {
            "capability_match": 0.35,
            "performance_history": 0.30,
            "trust_score": 0.20,
            "current_load": 0.10,
            "specialization": 0.05,
        }

    def register_agent(
        self,
        did: AgentDID,
        capabilities: list[str] | AgentCapabilitySchema | None = None,
    ) -> None:
        """注册 Agent 能力 — 支持 list[str] 和 AgentCapabilitySchema 双模式。

        Args:
            did: Agent DID
            capabilities: list[str] 能力标签（旧模式）或 AgentCapabilitySchema（新模式）
        """
        if capabilities is None:
            caps_list: list[str] = []
            schema: AgentCapabilitySchema | None = None
        elif isinstance(capabilities, AgentCapabilitySchema):
            schema = capabilities
            caps_list = capabilities.tags
            if _FEATURE_ACS_SCHEMA:
                self._agent_schemas[did] = capabilities
                if self._discovery_service is not None:
                    self._discovery_service.register(capabilities)
        else:
            caps_list = capabilities
            schema = None
            if _FEATURE_ACS_SCHEMA:
                auto_schema = AgentCapabilitySchema.from_tags(
                    agent_id=did.did_string, tags=capabilities
                )
                self._agent_schemas[did] = auto_schema
                if self._discovery_service is not None:
                    self._discovery_service.register(auto_schema)

        self._agent_capabilities[did] = caps_list
        self._agent_performance[did] = 0.7
        if self._trust_engine is not None:
            self._trust_engine.register_agent(did.did_string)
        if self._health_monitor is not None:
            self._health_monitor.register(did.did_string)

    def get_schema(self, did: AgentDID) -> AgentCapabilitySchema | None:
        """获取 Agent 的结构化能力描述（ACS）。"""
        return self._agent_schemas.get(did)

    def list_schemas(self) -> dict[str, AgentCapabilitySchema]:
        """列出所有已注册的结构化 schema。"""
        return {
            did.did_string: schema
            for did, schema in self._agent_schemas.items()
        }

    def unregister_agent(self, did: AgentDID) -> bool:
        found = did in self._agent_capabilities
        self._agent_capabilities.pop(did, None)
        self._agent_schemas.pop(did, None)
        self._agent_performance.pop(did, None)
        if self._discovery_service is not None:
            self._discovery_service.unregister(did.did_string)
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
        """Core selection logic without side effects (load increment).

        如果配置了 DiscoveryService，优先使用 DiscoveryService 预过滤候选 Agent，
        再对候选进行加权评分。否则回退到全量线性遍历。
        """
        if self._discovery_service is not None:
            query = DiscoveryQuery(
                required_capabilities=task.required_capabilities,
                min_trust_score=0.0,
                limit=20,
            )
            candidates = self._discovery_service.query(query)
            # 将 discovery 结果映射为 DID 到 match_score 的字典
            discovery_scores: dict[str, float] = {
                r.agent_id: r.match_score for r in candidates
            }
            candidate_ids = {r.agent_id for r in candidates}
        else:
            discovery_scores = {}
            candidate_ids = None

        best_did: AgentDID | None = None
        best_score = -1.0
        best_dimensions: dict[str, float] = {}

        for did, caps in self._agent_capabilities.items():
            # DiscoveryService 预过滤：不在候选列表中的跳过
            if candidate_ids is not None and did.did_string not in candidate_ids:
                continue
            dimensions = self._evaluate_match(did, task, caps, discovery_scores.get(did.did_string))
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
        if self._discovery_service is not None:
            query = DiscoveryQuery(
                required_capabilities=task.required_capabilities,
                min_trust_score=0.0,
                limit=20,
            )
            candidates = self._discovery_service.query(query)
            discovery_scores = {r.agent_id: r.match_score for r in candidates}
            candidate_ids = {r.agent_id for r in candidates}
        else:
            discovery_scores = {}
            candidate_ids = None

        best_did: AgentDID | None = None
        best_score = -1.0
        best_dimensions: dict[str, float] = {}

        for did, caps in self._agent_capabilities.items():
            if candidate_ids is not None and did.did_string not in candidate_ids:
                continue
            if reliability_matrix is not None and observer_id:
                task_type = task.description
                if reliability_matrix.should_bypass(observer_id, did.did_string, task_type):
                    continue

            dimensions = self._evaluate_match(did, task, caps, discovery_scores.get(did.did_string))
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
        self, did: AgentDID, task: SubTask, agent_caps: list[str],
        discovery_match_score: float | None = None,
    ) -> dict[str, float]:
        # 如果 DiscoveryService 已计算 match_score，直接使用
        if discovery_match_score is not None:
            capability_match = discovery_match_score
        else:
            schema = self._agent_schemas.get(did) if _FEATURE_ACS_SCHEMA else None
            if schema is not None:
                capability_match = schema.match_score(task.required_capabilities)
            else:
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

        specialization = 0.5 if task.required_capabilities else 0.5
        return {
            "capability_match": capability_match,
            "performance_history": performance,
            "trust_score": trust_score,
            "current_load": current_load,
            "specialization": specialization,
        }
