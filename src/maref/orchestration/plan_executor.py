from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.orchestration.protocols import (
    AgentTaskResult,
    SelfCheckResult,
    TaskResultStatus,
)
from maref.orchestration.state_merge_controller import StateMergeController
from maref.orchestration.task_graph import (
    NodeType,
    RiskLevel,
    TaskGraph,
    TaskNode,
    TaskStatus,
)


class PlanStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIALLY_COMPLETED = "partially_completed"


class StepResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"


@dataclass
class PlanStep:
    task_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 0.0
    on_failure: str = "rollback"
    # Fork/Join/DynamicRoute metadata
    node_type: NodeType = NodeType.SEQUENCE
    fork_branches: list[str] = field(default_factory=list)
    join_targets: list[str] = field(default_factory=list)
    route_rule: str = ""
    # Loop Engineering: risk-aware serial/parallel + HITL gating
    risk_level: RiskLevel = RiskLevel.MEDIUM
    hitl_required: bool = False


@dataclass
class Plan:
    plan_id: str
    steps: list[PlanStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_graph(self) -> TaskGraph:
        g = TaskGraph()
        for step in self.steps:
            node = TaskNode(
                task_id=step.task_id,
                description=step.description or step.action,
                depends_on=list(step.depends_on),
                node_type=step.node_type,
                risk_level=step.risk_level,
                fork_branches=list(step.fork_branches),
                join_targets=list(step.join_targets),
                route_rule=step.route_rule,
            )
            g.add_node(node)
        return g


@dataclass
class StepExecutionRecord:
    task_id: str
    action: str
    result: StepResult = StepResult.SUCCESS
    duration_ms: float = 0.0
    error: str | None = None
    retries: int = 0
    governance_verdict: str | None = None
    quality_score: float = 1.0
    risk_level: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "result": self.result.value,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "retries": self.retries,
            "governance_verdict": self.governance_verdict,
            "quality_score": self.quality_score,
            "risk_level": self.risk_level,
        }


@dataclass
class PlanExecutionReport:
    plan_id: str
    status: PlanStatus
    steps: list[StepExecutionRecord] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str | None = None

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.steps if s.result == StepResult.SUCCESS)

    @property
    def failure_count(self) -> int:
        return sum(1 for s in self.steps if s.result == StepResult.FAILURE)

    @property
    def all_succeeded(self) -> bool:
        return len(self.steps) > 0 and self.failure_count == 0

    @property
    def quality_score(self) -> float:
        if not self.steps:
            return 1.0
        return sum(s.quality_score for s in self.steps) / len(self.steps)

    @property
    def convergence(self) -> list[float]:
        return [s.quality_score for s in self.steps]

    @property
    def is_converged(self) -> bool:
        if len(self.steps) < _CONVERGENCE_WINDOW:
            return self.status == PlanStatus.COMPLETED
        trajectory = self.convergence
        recent = trajectory[-_CONVERGENCE_WINDOW:]
        return max(recent) - min(recent) < _CONVERGENCE_THRESHOLD and all(
            s > _MIN_QUALITY for s in recent
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "quality_score": self.quality_score,
            "is_converged": self.is_converged,
        }


_CONVERGENCE_WINDOW = 3
_CONVERGENCE_THRESHOLD = 0.05
_MIN_QUALITY = 0.8

GovernanceCheck = Callable[[str, dict[str, Any]], tuple[bool, str | None]]
ActionHandler = Callable[[str, dict[str, Any]], Any]
RouteResolver = Callable[[str, dict[str, Any], list[str]], str]


class PlanExecutor:
    def __init__(
        self,
        governance_check: GovernanceCheck | None = None,
        action_handlers: dict[str, ActionHandler] | None = None,
        route_resolvers: dict[str, RouteResolver] | None = None,
        merge_controller: StateMergeController | None = None,
        max_merge_iterations: int = 3,
    ):
        self._governance_check = governance_check
        self._handlers: dict[str, ActionHandler] = {}
        if action_handlers:
            self._handlers.update(action_handlers)
        self._route_resolvers: dict[str, RouteResolver] = {}
        if route_resolvers:
            self._route_resolvers.update(route_resolvers)
        self._merge_controller = merge_controller or StateMergeController()
        self._max_merge_iterations = max_merge_iterations

    def register_handler(self, action: str, handler: ActionHandler) -> None:
        self._handlers[action] = handler

    def register_handlers(self, handlers: dict[str, ActionHandler]) -> None:
        self._handlers.update(handlers)

    def register_route_resolver(self, rule: str, resolver: RouteResolver) -> None:
        self._route_resolvers[rule] = resolver

    # ------------------------------------------------------------------ #
    # Public execution entry
    # ------------------------------------------------------------------ #
    def execute(self, plan: Plan) -> PlanExecutionReport:
        start = time.time()
        graph = plan.to_graph()

        if graph.has_cycle():
            return PlanExecutionReport(
                plan_id=plan.plan_id,
                status=PlanStatus.FAILED,
                error=f"Plan contains cycles: {graph.detect_cycles()}",
            )

        records: list[StepExecutionRecord] = []
        steps_by_id = {s.task_id: s for s in plan.steps}
        failed_steps: set[str] = set()
        rollback_requested = False
        fail_requested = False
        merge_iterations = 0

        # Use wave-based execution instead of strict topological order
        # so FORK branches can run as soon as ready.
        pending = set(graph.node_ids)
        _merge_halt = False
        while pending and not _merge_halt:
            ready = self._ready_tasks(graph, pending, failed_steps)
            if not ready:
                break

            for task_id in ready:
                pending.discard(task_id)
                node = graph.get_node(task_id)

                if node and node.node_type == NodeType.FORK:
                    for branch_id in node.fork_branches:
                        if branch_id not in graph.node_ids:
                            stub = TaskNode(
                                task_id=branch_id,
                                description=f"auto_branch:{branch_id}",
                                depends_on=[task_id],
                            )
                            graph.add_node(stub)
                            pending.add(branch_id)
                        elif branch_id not in (set(graph.node_ids) - pending):
                            pass
                        else:
                            pending.add(branch_id)

                step = steps_by_id.get(task_id)
                if not step:
                    # C3: JOIN node fires — merge all completed branch results
                    if node and node.node_type == NodeType.JOIN:
                        targets = node.join_targets
                        if len(targets) > 1 and merge_iterations < self._max_merge_iterations:
                            merge_result = self._run_state_merge(
                                targets, records, steps_by_id, graph, pending, failed_steps
                            )
                            if merge_result == "rework":
                                merge_iterations += 1
                            elif merge_result == "halt":
                                _merge_halt = True
                                break

                    records.append(
                        StepExecutionRecord(
                            task_id=task_id,
                            action="unknown",
                            result=StepResult.SKIPPED,
                            error="Step not found in plan",
                        )
                    )
                    graph.set_node_status(task_id, TaskStatus.SKIPPED)
                    failed_steps.add(task_id)
                    continue

                record = self._execute_step(step, records)
                records.append(record)

                if record.result == StepResult.SUCCESS:
                    graph.set_node_status(task_id, TaskStatus.COMPLETED)
                elif record.result == StepResult.SKIPPED:
                    graph.set_node_status(task_id, TaskStatus.SKIPPED)
                    failed_steps.add(task_id)
                else:
                    graph.set_node_status(task_id, TaskStatus.FAILED)
                    failed_steps.add(task_id)
                    if step.on_failure == "rollback":
                        rollback_requested = True
                        pending.clear()
                    elif step.on_failure == "fail":
                        fail_requested = True
                        pending.clear()

            if _merge_halt:
                break

        if rollback_requested:
            plan_status = PlanStatus.ROLLED_BACK
        elif fail_requested:
            plan_status = PlanStatus.FAILED
        elif len(failed_steps) > 0:
            plan_status = PlanStatus.PARTIALLY_COMPLETED
        else:
            plan_status = PlanStatus.COMPLETED

        total = (time.time() - start) * 1000
        return PlanExecutionReport(
            plan_id=plan.plan_id,
            status=plan_status,
            steps=records,
            total_duration_ms=total,
        )

    def _run_state_merge(
        self,
        wave_tasks: list[str],
        records: list[StepExecutionRecord],
        steps_by_id: dict[str, Any],
        graph: TaskGraph,
        pending: set[str],
        failed_steps: set[str],
    ) -> str:
        """Run StateMergeController on completed wave tasks.

        Returns: 'continue', 'rework', 'halt'
        """
        agent_results: list[AgentTaskResult] = []
        for task_id in wave_tasks:
            rec = next((r for r in records if r.task_id == task_id), None)
            if rec is None:
                continue
            agent_results.append(
                AgentTaskResult(
                    task_id=task_id,
                    status=TaskResultStatus.COMPLETED
                    if rec.result == StepResult.SUCCESS
                    else TaskResultStatus.FAILED,
                    summary=rec.action,
                    self_check=SelfCheckResult(
                        passed=rec.result == StepResult.SUCCESS,
                        quality_score=rec.quality_score,
                    ),
                )
            )

        merge_result = self._merge_controller.merge(agent_results)
        route = self._merge_controller.decide_route(merge_result, graph)

        if route == "rework":
            for tid in merge_result.rework_tasks:
                node = graph.get_node(tid)
                if node:
                    node.status = TaskStatus.PENDING
                    pending.add(tid)
                    if tid in failed_steps:
                        failed_steps.discard(tid)
            return "rework"

        if route == "human_review":
            for tid in wave_tasks:
                rec = next((r for r in records if r.task_id == tid), None)
                if rec:
                    rec.governance_verdict = "human_review_required"
            return "halt"

        return "continue"

    # ------------------------------------------------------------------ #
    # Ready-set computation with Fork/Join/DynamicRoute awareness
    # ------------------------------------------------------------------ #
    def _ready_tasks(
        self,
        graph: TaskGraph,
        pending: set[str],
        failed_steps: set[str],
    ) -> list[str]:
        ready: list[str] = []
        for task_id in pending:
            node = graph.get_node(task_id)
            if node is None:
                continue

            deps_ok = all(
                dep_node.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
                for dep in graph.get_dependencies(task_id)
                if (dep_node := graph.get_node(dep)) is not None
            )
            if not deps_ok:
                continue

            if node.node_type == NodeType.SEQUENCE:
                ready.append(task_id)
            elif node.node_type == NodeType.FORK:
                # Fork is ready when its own deps are satisfied
                ready.append(task_id)
            elif node.node_type == NodeType.JOIN:
                # Join is ready when ALL join_targets are terminal
                targets_terminal = all(
                    target_node.status
                    in (
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                        TaskStatus.SKIPPED,
                    )
                    for tid in node.join_targets
                    if (target_node := graph.get_node(tid)) is not None
                )
                if targets_terminal:
                    ready.append(task_id)
            elif node.node_type == NodeType.DYNAMIC_ROUTE:
                # Dynamic route is ready like a normal step
                ready.append(task_id)
        return ready

    def _execute_step(
        self, step: PlanStep, history: list[StepExecutionRecord]
    ) -> StepExecutionRecord:
        step_start = time.time()

        # ------------------------------------------------------------------ #
        # Dynamic Route resolution (happens before governance / handler)
        # ------------------------------------------------------------------ #
        if step.node_type == NodeType.DYNAMIC_ROUTE and step.route_rule:
            resolver = self._route_resolvers.get(step.route_rule)
            if resolver:
                candidates = step.params.get("dynamic_candidates", [])
                chosen = resolver(step.task_id, step.params, candidates)
                step.params["_dynamic_chosen"] = chosen
            else:
                return StepExecutionRecord(
                    task_id=step.task_id,
                    action=step.action,
                    result=StepResult.FAILURE,
                    duration_ms=(time.time() - step_start) * 1000,
                    error=f"No route resolver for rule '{step.route_rule}'",
                    quality_score=0.0,
                    risk_level=step.risk_level.value,
                )

        handler = self._handlers.get(step.action)

        governance_verdict: str | None = None
        if self._governance_check:
            check_params = dict(step.params)
            if step.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or step.hitl_required:
                check_params["_risk_level"] = step.risk_level.value
                check_params["_hitl_required"] = True
            allowed, reason = self._governance_check(step.action, check_params)
            if not allowed:
                governance_verdict = f"denied:{reason}"
                return StepExecutionRecord(
                    task_id=step.task_id,
                    action=step.action,
                    result=StepResult.BLOCKED,
                    duration_ms=(time.time() - step_start) * 1000,
                    error=f"Governance denied: {reason}",
                    governance_verdict=governance_verdict,
                    quality_score=0.0,
                    risk_level=step.risk_level.value,
                )
            governance_verdict = "allowed"

        if not handler:
            governance_verdict = governance_verdict or "allowed"
            return StepExecutionRecord(
                task_id=step.task_id,
                action=step.action,
                result=StepResult.SKIPPED,
                duration_ms=(time.time() - step_start) * 1000,
                error=f"No handler registered for '{step.action}'",
                governance_verdict=governance_verdict,
                quality_score=0.0,
                risk_level=step.risk_level.value,
            )

        for attempt in range(step.max_retries + 1):
            try:
                handler(step.action, step.params)
                quality = self._retry_penalty_score(step, attempt)
                return StepExecutionRecord(
                    task_id=step.task_id,
                    action=step.action,
                    result=StepResult.SUCCESS,
                    duration_ms=(time.time() - step_start) * 1000,
                    retries=attempt,
                    governance_verdict=governance_verdict,
                    quality_score=quality,
                    risk_level=step.risk_level.value,
                )
            except Exception as e:
                if attempt < step.max_retries:
                    time.sleep(step.retry_delay_seconds)
                else:
                    quality = self._retry_penalty_score(step, attempt, error=e)
                    return StepExecutionRecord(
                        task_id=step.task_id,
                        action=step.action,
                        result=StepResult.FAILURE,
                        duration_ms=(time.time() - step_start) * 1000,
                        error=str(e),
                        retries=attempt,
                        governance_verdict=governance_verdict,
                        quality_score=quality,
                        risk_level=step.risk_level.value,
                    )

        return StepExecutionRecord(
            task_id=step.task_id,
            action=step.action,
            result=StepResult.FAILURE,
            duration_ms=(time.time() - step_start) * 1000,
            error="Unexpected execution path",
            quality_score=0.0,
            risk_level=step.risk_level.value,
        )

    @staticmethod
    def _retry_penalty_score(
        step: PlanStep,
        retries: int,
        error: Exception | None = None,
    ) -> float:
        """Quality score 0.0–1.0 based on retries, error state, risk level."""
        if error:
            return 0.0
        base = 1.0
        penalty = retries * 0.15
        if retries > 0:
            penalty += 0.05 * math.log(retries + 1)
        return max(0.1, base - penalty)
