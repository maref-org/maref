from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maref.execution.harness.types import HarnessResult, HarnessStatus
from maref.orchestration.plan_executor import (
    ActionHandler,
    GovernanceCheck,
    Plan,
    PlanExecutor,
    PlanStep,
    RouteResolver,
)
from maref.orchestration.task_graph import NodeType, TaskGraph


class OrchestrationBridge:
    """包装 TaskGraph + PlanExecutor。

    提供:
    - decompose(): 任务描述 → TaskGraph
    - execute(): TaskGraph 执行 → 结果 dict
    - 底层 PlanExecutor 直接访问
    """

    def __init__(
        self,
        plan_executor: PlanExecutor | None = None,
        decomposer: Callable[[str], Plan] | None = None,
    ) -> None:
        self._executor = plan_executor or PlanExecutor()
        self._decomposer = decomposer or self._default_decomposer

    @property
    def executor(self) -> PlanExecutor:
        return self._executor

    # ── Task decomposition ─────────────────────────────────────────────

    @staticmethod
    def _default_decomposer(task: str) -> Plan:
        """默认分解器：将任务描述转为单步骤 Plan。"""
        step = PlanStep(
            task_id="task_1",
            action="execute",
            params={"task": task},
            description=task,
        )
        return Plan(plan_id="plan_1", steps=[step])

    def set_decomposer(self, decomposer: Callable[[str], Plan]) -> None:
        self._decomposer = decomposer

    def decompose(self, task: str) -> TaskGraph:
        """将任务描述分解为 TaskGraph。"""
        plan = self._decomposer(task)
        return plan.to_graph()

    # ── Plan execution ─────────────────────────────────────────────────

    def execute(self, graph: TaskGraph) -> dict[str, Any]:
        """执行 TaskGraph 并返回结果。"""
        plan = self._graph_to_plan(graph)
        report = self._executor.execute(plan)
        return {
            "plan_id": report.plan_id,
            "status": report.status.value,
            "total_duration_ms": report.total_duration_ms,
            "step_count": len(report.steps),
            "success_count": report.success_count,
            "failure_count": report.failure_count,
            "error": report.error,
            "steps": [s.to_dict() for s in report.steps],
        }

    def execute_plan(self, plan: Plan) -> dict[str, Any]:
        """直接执行 Plan 对象。"""
        report = self._executor.execute(plan)
        return {
            "plan_id": report.plan_id,
            "status": report.status.value,
            "total_duration_ms": report.total_duration_ms,
            "step_count": len(report.steps),
            "success_count": report.success_count,
            "failure_count": report.failure_count,
            "error": report.error,
        }

    # ── Handler registration ───────────────────────────────────────────

    def register_handler(self, action: str, handler: ActionHandler) -> None:
        self._executor.register_handler(action, handler)

    def register_handlers(self, handlers: dict[str, ActionHandler]) -> None:
        self._executor.register_handlers(handlers)

    def register_route_resolver(self, rule: str, resolver: RouteResolver) -> None:
        self._executor.register_route_resolver(rule, resolver)

    def set_governance_check(self, check: GovernanceCheck) -> None:
        """设置治理检查回调。"""
        self._executor = PlanExecutor(
            governance_check=check,
            action_handlers=self._executor._handlers,
            route_resolvers=self._executor._route_resolvers,
        )

    # ── Result conversion ──────────────────────────────────────────────

    def to_harness_result(
        self,
        execution_result: dict[str, Any],
        round_id: str = "",
    ) -> HarnessResult:
        errors: list[str] = []
        if execution_result.get("error"):
            errors.append(execution_result["error"])
        if execution_result.get("failure_count", 0) > 0:
            for step in execution_result.get("steps", []):
                if step.get("result") == "failure" and step.get("error"):
                    errors.append(f"{step['task_id']}: {step['error']}")

        return HarnessResult(
            harness_type="orchestrated",
            round_id=round_id,
            status=HarnessStatus.SUCCEEDED
            if execution_result.get("status") in ("completed", "partially_completed")
            else HarnessStatus.FAILED,
            duration_s=execution_result.get("total_duration_ms", 0) / 1000,
            errors=errors,
            metrics={
                "step_count": execution_result.get("step_count", 0),
                "success_count": execution_result.get("success_count", 0),
                "failure_count": execution_result.get("failure_count", 0),
                "plan_id": execution_result.get("plan_id", ""),
            },
        )

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _graph_to_plan(graph: TaskGraph) -> Plan:
        """将 TaskGraph 转为 Plan 对象供 PlanExecutor 执行。"""
        steps: list[PlanStep] = []
        for node_id in graph.node_ids:
            node = graph.get_node(node_id)
            if node is None:
                continue
            step = PlanStep(
                task_id=node.task_id,
                action="execute",
                description=node.description,
                depends_on=list(node.depends_on),
                node_type=node.node_type,
                fork_branches=list(node.fork_branches),
                join_targets=list(node.join_targets),
                route_rule=node.route_rule,
            )
            if node.node_type == NodeType.DYNAMIC_ROUTE:
                candidates = node.metadata.get("dynamic_candidates", [])
                step.params["dynamic_candidates"] = candidates
            steps.append(step)

        return Plan(plan_id="graph_plan", steps=steps)
