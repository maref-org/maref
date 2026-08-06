from __future__ import annotations

import pytest

from maref.integration.hitl import HITLRouter
from maref.orchestration.plan_executor import (
    Plan,
    PlanExecutor,
    PlanStatus,
    PlanStep,
    StepResult,
)
from maref.orchestration.task_graph import TaskGraph


@pytest.fixture
def hitl_router() -> HITLRouter:
    return HITLRouter()


@pytest.fixture
def basic_plan() -> Plan:
    return Plan(
        plan_id="integ-test-1",
        steps=[
            PlanStep(
                task_id="step1", action="analyze", params={"target": "a"}, description="Analyze A"
            ),
            PlanStep(
                task_id="step2",
                action="compute",
                params={"target": "b"},
                depends_on=["step1"],
                description="Compute B",
            ),
            PlanStep(
                task_id="step3",
                action="report",
                params={"target": "c"},
                depends_on=["step2"],
                description="Report C",
            ),
        ],
    )


def make_gov_check(hitl: HITLRouter):
    def check(task_id: str, params: dict) -> tuple[bool, str | None]:
        _ = hitl.route("critical", "governance_check", f"Check {task_id}")
        return True, None

    return check


class TestHITLAndPlanExecutor:
    def test_plan_executor_creates_hitl_events(
        self, hitl_router: HITLRouter, basic_plan: Plan
    ) -> None:
        executor = PlanExecutor(governance_check=make_gov_check(hitl_router))
        executor.register_handler("analyze", lambda tid, p: {"status": "ok"})
        executor.register_handler("compute", lambda tid, p: {"status": "ok"})
        executor.register_handler("report", lambda tid, p: {"status": "ok"})

        report = executor.execute(basic_plan)

        assert report.status == PlanStatus.COMPLETED
        assert report.all_succeeded
        assert len(hitl_router.get_all()) == 3

    def test_hitl_approval_allows_plan_to_proceed(self, hitl_router: HITLRouter) -> None:
        results: dict[str, bool] = {}

        def check(action: str, params: dict) -> tuple[bool, str | None]:
            if action == "process":
                ev = hitl_router.route("critical", "plan_step", f"Approve {action}")
                hitl_router.approve(ev.event_id)
                results["approved"] = True
            return True, None

        executor = PlanExecutor(governance_check=check)
        executor.register_handler("setup", lambda act, p: {"ok": True})
        executor.register_handler("process", lambda act, p: {"ok": True})

        plan = Plan(
            plan_id="approval-test",
            steps=[
                PlanStep(task_id="step1", action="setup", params={}, description="Setup"),
                PlanStep(
                    task_id="step2",
                    action="process",
                    params={},
                    depends_on=["step1"],
                    description="Process",
                ),
            ],
        )

        report = executor.execute(plan)

        assert report.status == PlanStatus.COMPLETED
        assert results.get("approved") is True

    def test_governance_rejection_blocks_plan(self, hitl_router: HITLRouter) -> None:
        def check(action: str, params: dict) -> tuple[bool, str | None]:
            ev = hitl_router.route("critical", "governance_check", f"Check {action}")
            hitl_router.reject(ev.event_id, reason="not allowed")
            return False, "Blocked by governance"

        executor = PlanExecutor(governance_check=check)
        executor.register_handler("risky_action", lambda act, p: {"status": "ok"})

        plan = Plan(
            plan_id="rejection-test",
            steps=[PlanStep(task_id="step1", action="risky_action", params={}, on_failure="fail")],
        )

        report = executor.execute(plan)

        assert report.status == PlanStatus.FAILED
        assert len(report.steps) == 1
        assert report.steps[0].result == StepResult.BLOCKED
        pending = hitl_router.get_pending()
        assert len(pending) == 0

    def test_hitl_router_tier_map_influences_blocking(self) -> None:
        router = HITLRouter()

        ev_normal = router.route("normal", "test", "Normal event")
        assert not router.is_blocking(ev_normal.tier)

        ev_critical = router.route("critical", "test", "Critical event")
        assert router.is_blocking(ev_critical.tier)

    def test_tool_definition_usable_with_hitl_metadata(self) -> None:
        from maref.tools.tool_schema import ToolRiskLevel, create_file_tool

        file_tool = create_file_tool()
        router = HITLRouter()

        ev = router.route(
            "warning",
            "tool_execution",
            f"Execute {file_tool.name}",
            tool_name=file_tool.name,
            tool_risk_level=file_tool.risk_level.value,
        )

        assert ev.metadata["tool_name"] == "file"
        assert ev.metadata["tool_risk_level"] == ToolRiskLevel.HIGH.value


class TestTaskGraphAndPlanIntegration:
    def test_plan_to_graph_round_trip(self) -> None:
        original = Plan(
            plan_id="roundtrip",
            steps=[
                PlanStep(task_id="a", action="read", params={"file": "x"}, description="Read X"),
                PlanStep(
                    task_id="b",
                    action="write",
                    params={"file": "y"},
                    depends_on=["a"],
                    description="Write Y",
                ),
            ],
        )

        graph = original.to_graph()
        assert isinstance(graph, TaskGraph)
        assert graph.node_count == 2
        assert graph.get_node("a") is not None
        assert graph.get_node("b") is not None
        assert graph.get_dependencies("b") == ["a"]

        order = graph.topological_order()
        assert order.index("a") < order.index("b")

    def test_graph_from_plan_executes_correctly(self) -> None:
        plan = Plan(
            plan_id="graph-exec",
            steps=[
                PlanStep(task_id="fetch", action="read", params={}, description="Fetch data"),
                PlanStep(
                    task_id="validate",
                    action="check",
                    params={},
                    depends_on=["fetch"],
                    description="Validate",
                ),
                PlanStep(
                    task_id="store",
                    action="write",
                    params={},
                    depends_on=["validate"],
                    description="Store",
                ),
            ],
        )

        executed: list[str] = []

        executor = PlanExecutor()
        executor.register_handler("read", lambda act, p: executed.append(act) or {"ok": True})
        executor.register_handler("check", lambda act, p: executed.append(act) or {"ok": True})
        executor.register_handler("write", lambda act, p: executed.append(act) or {"ok": True})

        report = executor.execute(plan)

        assert report.status == PlanStatus.COMPLETED
        assert executed == ["read", "check", "write"]

    def test_graph_cycle_detected_in_plan(self) -> None:
        plan = Plan(
            plan_id="cycle-test",
            steps=[
                PlanStep(task_id="a", action="task", params={}, depends_on=["b"]),
                PlanStep(task_id="b", action="task", params={}, depends_on=["c"]),
                PlanStep(task_id="c", action="task", params={}, depends_on=["a"]),
            ],
        )

        executor = PlanExecutor()
        report = executor.execute(plan)

        assert report.status == PlanStatus.FAILED
        assert report.error is not None
        assert "cycle" in report.error.lower()

    def test_plan_with_tool_definitions(self) -> None:
        from maref.tools.tool_schema import create_shell_tool

        shell_tool = create_shell_tool()

        plan = Plan(
            plan_id="tool-plan",
            steps=[
                PlanStep(
                    task_id="shell-step",
                    action=shell_tool.name,
                    params={"command": "echo hello"},
                    description=shell_tool.description,
                ),
            ],
        )

        executor = PlanExecutor()
        executor.register_handler(
            shell_tool.name, lambda tid, p: {"output": "hello", "exit_code": 0}
        )

        report = executor.execute(plan)

        assert report.status == PlanStatus.COMPLETED
        assert report.all_succeeded
