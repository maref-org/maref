"""MultiAgentCoordinator — 管理多个 SubHarness 实例，协调执行。"""

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
    """多Agent 协调器，管理多个 SubHarness 实例。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

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

    def run_all(self, task: str = "", parallel: bool = False, config: HarnessConfig | None = None) -> dict[str, HarnessResult]:
        if parallel:
            return self._run_parallel(task, config)
        return self._run_sequential(task, config)

    def _run_sequential(self, task: str, config: HarnessConfig | None) -> dict[str, HarnessResult]:
        results: dict[str, HarnessResult] = {}
        for agent_id, info in self._agents.items():
            info.started_at = time.time()
            try:
                h = info.harness
                if config:
                    h.configure(config)
                if hasattr(h, "preflight"):
                    h.preflight()
                info.result = h.run(round_id=task)
            except Exception as e:
                info.result = HarnessResult(status=HarnessStatus.FAILED, errors=[str(e)])
            info.finished_at = time.time()
            results[agent_id] = info.result
        return results

    def _run_parallel(self, task: str, config: HarnessConfig | None) -> dict[str, HarnessResult]:
        results: dict[str, HarnessResult] = {}
        threads: list[threading.Thread] = []
        lock = threading.Lock()

        def _run(agent_id: str, info: AgentInfo) -> None:
            info.started_at = time.time()
            try:
                h = info.harness
                if config:
                    h.configure(config)
                if hasattr(h, "preflight"):
                    h.preflight()
                info.result = h.run(round_id=task)
            except Exception as e:
                info.result = HarnessResult(status=HarnessStatus.FAILED, errors=[str(e)])
            info.finished_at = time.time()
            with lock:
                results[agent_id] = info.result

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
