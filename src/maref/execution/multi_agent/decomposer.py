"""HarnessTaskDecomposer — 大任务分解为 Agent-子任务映射，结果归并。"""

from __future__ import annotations

from typing import Any

from maref.execution.harness.types import HarnessResult, HarnessStatus


class HarnessTaskDecomposer:
    """把大任务按 Agent 角色分解为子任务，执行后归并结果。"""

    def decompose(self, task: str, agents: dict[str, str]) -> dict[str, str]:
        """agents: {agent_id: role} → {agent_id: sub_task_description}

        简单策略：用角色名修饰原始任务描述。
        """
        return {aid: f"[{role}] {task}" for aid, role in agents.items()}

    def merge(self, results: dict[str, HarnessResult]) -> HarnessResult:
        """归并多个 Agent 的执行结果为单一 HarnessResult。"""
        errors: list[str] = []
        metrics: dict[str, Any] = {}
        total_duration = 0.0

        for agent_id, r in results.items():
            if r.errors:
                errors.extend(f"[{agent_id}] {e}" for e in r.errors)
            total_duration = max(total_duration, r.duration_s)
            for k, v in r.metrics.items():
                metrics[f"{agent_id}/{k}"] = v

        status = HarnessStatus.FAILED if errors else HarnessStatus.SUCCEEDED
        return HarnessResult(
            harness_type="multi_agent",
            status=status,
            duration_s=total_duration,
            errors=errors,
            metrics=metrics,
        )
