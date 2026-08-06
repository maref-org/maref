"""MultiAgentCoordinator — 管理多个 SubHarness 实例，协调执行。

v0.47 F1：接入联邦治理 —
- 派发前经 TrustBoundaryManager 强制门禁（fail-closed）；
- 任务带审计（AuditBus）+ 计量（TaskMeteringEngine）；
- 执行异常走级联断路器。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus


@dataclass
class AgentInfo:
    harness: BaseHarness
    role: str
    result: HarnessResult | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


class MultiAgentCoordinator:
    """多Agent 协调器，管理多个 SubHarness 实例。

    Args:
        boundary: 可选 :class:`~maref.governance.trust_boundary.TrustBoundaryManager`。
            派发前每个 agent 动作经边界校验，越界跳过（fail-closed）。
        audit_bus: 可选 :class:`~maref.governance.audit_bus.AuditBus`。
            每个任务执行后记录审计事件。
        metering: 可选 :class:`~maref.federation.metering.TaskMeteringEngine`。
            每个任务记录计量（caller_did=agent_id）。
        circuit_breaker: 可选 :class:`~maref.governance.circuit_breaker.CircuitBreaker`。
            执行异常触发，熔断后停止后续派发。
    """

    def __init__(
        self,
        boundary: Any | None = None,
        audit_bus: Any | None = None,
        metering: Any | None = None,
        circuit_breaker: Any | None = None,
    ) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._boundary = boundary
        self._audit_bus = audit_bus
        self._metering = metering
        self._circuit_breaker = circuit_breaker

    def add_agent(self, harness: BaseHarness, role: str) -> str:
        agent_id = f"agent_{len(self._agents) + 1}"
        self._agents[agent_id] = AgentInfo(harness=harness, role=role)
        return agent_id

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def roles(self) -> list[str]:
        return [a.role for a in self._agents.values()]

    # -- 治理辅助 --

    def _boundary_allows(self, agent_id: str, role: str, task: str) -> bool:
        """派发前 TrustBoundary 门禁（v0.47 F1）。"""
        if self._boundary is None:
            return True
        decision = self._boundary.check_no_raise(
            action=task or f"role:{role}",
            agent_id=agent_id,
        )
        return decision.allowed

    def _record_audit(self, agent_id: str, role: str, task: str, result: HarnessResult) -> None:
        """任务审计（v0.47 F1）。"""
        if self._audit_bus is None:
            return
        self._audit_bus.log(
            event_type="multi_agent_task",
            actor=agent_id,
            action=task or "task",
            details=f"role={role} status={result.status.value}",
            metadata={"role": role, "status": result.status.value},
        )

    def _record_metering(self, agent_id: str, role: str, task: str, result: HarnessResult) -> None:
        """任务计量（v0.47 F1）。"""
        if self._metering is None:
            return
        self._metering.record(
            task_id=task or "task",
            agent_did=agent_id,
            agent_aic="",
            provider_org=role,
            consumer_org="coordinator",
            duration_ms=result.duration_s * 1000,
            token_count=0,
            success=result.status == HarnessStatus.SUCCEEDED,
            complexity_score=0.5,
            caller_did=agent_id,
        )

    def _execution_failed(self) -> None:
        """级联断路器：执行异常触发（v0.47 F1）。"""
        if self._circuit_breaker is not None:
            self._circuit_breaker.record_failure()

    def _breaker_open(self) -> bool:
        return bool(self._circuit_breaker is not None and self._circuit_breaker.is_open)

    # -- 执行 --

    def run_all(self, task: str = "", parallel: bool = False, config: HarnessConfig | None = None) -> dict[str, HarnessResult]:
        if parallel:
            return self._run_parallel(task, config)
        return self._run_sequential(task, config)

    def _run_sequential(self, task: str, config: HarnessConfig | None) -> dict[str, HarnessResult]:
        results: dict[str, HarnessResult] = {}
        for agent_id, info in self._agents.items():
            results[agent_id] = self._dispatch(agent_id, info, task, config)
            if self._breaker_open():
                break
        return results

    def _dispatch(
        self,
        agent_id: str,
        info: AgentInfo,
        task: str,
        config: HarnessConfig | None,
    ) -> HarnessResult:
        if self._breaker_open():
            return HarnessResult(status=HarnessStatus.FAILED, errors=["circuit breaker open"])
        if not self._boundary_allows(agent_id, info.role, task):
            info.result = HarnessResult(
                status=HarnessStatus.FAILED,
                errors=["trust boundary denied dispatch"],
            )
            return info.result

        info.started_at = time.time()
        try:
            h = info.harness
            if config:
                h.configure(config)
            if hasattr(h, "preflight"):
                h.preflight()
            info.result = h.run(round_id=task)
            self._record_audit(agent_id, info.role, task, info.result)
            self._record_metering(agent_id, info.role, task, info.result)
        except Exception as e:
            info.result = HarnessResult(status=HarnessStatus.FAILED, errors=[str(e)])
            self._execution_failed()
            self._record_audit(agent_id, info.role, task, info.result)
        finally:
            info.finished_at = time.time()
        return info.result

    def _run_parallel(self, task: str, config: HarnessConfig | None) -> dict[str, HarnessResult]:
        results: dict[str, HarnessResult] = {}
        threads: list[threading.Thread] = []
        lock = threading.Lock()

        def _run(agent_id: str, info: AgentInfo) -> None:
            with lock:
                result = self._dispatch(agent_id, info, task, config)
                results[agent_id] = result

        for agent_id, info in self._agents.items():
            t = threading.Thread(target=_run, args=(agent_id, info))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results

    def aggregate(self, results: dict[str, HarnessResult]) -> dict[str, Any]:
        total = len(results)
        succeeded = sum(1 for r in results.values() if r.status == HarnessStatus.SUCCEEDED)
        failed = sum(1 for r in results.values() if r.status == HarnessStatus.FAILED)
        total_duration = max(
            (self._agents[aid].finished_at - self._agents[aid].started_at)
            for aid in results if aid in self._agents
        ) if results else 0.0

        per_agent: dict[str, dict[str, Any]] = {}
        for aid, r in results.items():
            role = self._agents[aid].role if aid in self._agents else "unknown"
            per_agent[aid] = {
                "role": role,
                "status": r.status.value,
                "duration_s": r.duration_s,
                "errors": r.errors[:3],
            }

        return {
            "total_agents": total,
            "succeeded": succeeded,
            "failed": failed,
            "total_duration_s": total_duration,
            "per_agent": per_agent,
        }
