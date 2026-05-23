from __future__ import annotations

from maref.orchestration.plan_executor import (
    Plan, PlanExecutor, PlanStep, PlanStatus, StepResult,
)


def _always_allow(action: str, params: dict) -> tuple[bool, str | None]:
    return True, None


def _always_deny(action: str, params: dict) -> tuple[bool, str | None]:
    return False, "Not authorized"


def _succeed(action: str, params: dict) -> None:
    pass


def _fail(action: str, params: dict) -> None:
    msg = f"Intentional failure for {action}"
    raise RuntimeError(msg)


class TestPlan:
    def test_empty_plan(self):
        p = Plan(plan_id="test-1")
        assert p.step_count == 0
        assert p.plan_id == "test-1"

    def test_plan_to_graph(self):
        p = Plan(
            plan_id="test-1",
            steps=[
                PlanStep(task_id="a", action="read", description="Read file"),
                PlanStep(task_id="b", action="write", description="Write file", depends_on=["a"]),
            ],
        )
        g = p.to_graph()
        assert g.node_count == 2
        assert g.get_node("a") is not None
        assert g.get_node("b") is not None


class TestPlanExecutor:
    def test_execute_empty_plan(self):
        exe = PlanExecutor()
        report = exe.execute(Plan(plan_id="empty"))
        assert report.status == PlanStatus.COMPLETED
        assert report.steps == []
        assert report.all_succeeded is False  # no steps

    def test_execute_simple_plan(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"read": _succeed},
        )
        plan = Plan(
            plan_id="test-1",
            steps=[PlanStep(task_id="s1", action="read", description="Read")],
        )
        report = exe.execute(plan)
        assert report.status == PlanStatus.COMPLETED
        assert len(report.steps) == 1
        assert report.steps[0].result == StepResult.SUCCESS
        assert report.steps[0].action == "read"

    def test_execute_multi_step_dag(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"step_a": _succeed, "step_b": _succeed, "step_c": _succeed},
        )
        plan = Plan(
            plan_id="dag",
            steps=[
                PlanStep(task_id="a", action="step_a", description="A"),
                PlanStep(task_id="b", action="step_b", description="B", depends_on=["a"]),
                PlanStep(task_id="c", action="step_c", description="C", depends_on=["b"]),
            ],
        )
        report = exe.execute(plan)
        assert report.status == PlanStatus.COMPLETED
        assert len(report.steps) == 3
        assert all(s.result == StepResult.SUCCESS for s in report.steps)

    def test_governance_block(self):
        exe = PlanExecutor(
            governance_check=_always_deny,
            action_handlers={"write": _succeed},
        )
        plan = Plan(
            plan_id="gov-block",
            steps=[PlanStep(task_id="s1", action="write", description="Write")],
        )
        report = exe.execute(plan)
        assert report.steps[0].result == StepResult.BLOCKED
        assert "Governance denied" in (report.steps[0].error or "")

    def test_execution_failure_default_rollback(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"fail": _fail},
        )
        plan = Plan(
            plan_id="fail-rollback",
            steps=[
                PlanStep(task_id="s1", action="ok", description="OK"),
                PlanStep(task_id="s2", action="fail", description="Fail", on_failure="rollback"),
                PlanStep(task_id="s3", action="ok2", description="OK2"),
            ],
        )
        exe.register_handler("ok", _succeed)
        exe.register_handler("ok2", _succeed)
        report = exe.execute(plan)
        assert report.status == PlanStatus.ROLLED_BACK
        assert report.steps[0].result == StepResult.SUCCESS
        assert report.steps[1].result == StepResult.FAILURE

    def test_execution_failure_skip(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"ok": _succeed, "fail": _fail, "after": _succeed},
        )
        plan = Plan(
            plan_id="fail-skip",
            steps=[
                PlanStep(task_id="s1", action="ok", description="OK"),
                PlanStep(task_id="s2", action="fail", description="Fail", on_failure="skip"),
                PlanStep(task_id="s3", action="after", description="After", depends_on=["s1"]),
            ],
        )
        report = exe.execute(plan)
        assert report.status == PlanStatus.PARTIALLY_COMPLETED
        assert report.steps[0].result == StepResult.SUCCESS
        assert report.steps[1].result == StepResult.FAILURE
        assert report.steps[2].result == StepResult.SUCCESS

    def test_dependency_failure_skips_downstream(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"ok": _succeed, "fail": _fail},
        )
        plan = Plan(
            plan_id="dep-fail",
            steps=[
                PlanStep(task_id="s1", action="fail", description="Fail", on_failure="fail"),
                PlanStep(task_id="s2", action="ok", description="OK", depends_on=["s1"]),
            ],
        )
        report = exe.execute(plan)
        assert report.steps[1].result == StepResult.SKIPPED
        assert "Dependency failed" in (report.steps[1].error or "")

    def test_retry_success(self):
        call_count: list[int] = [0]

        def _retry_once(action: str, params: dict) -> None:
            call_count[0] += 1
            if call_count[0] < 2:
                msg = f"Attempt {call_count[0]} failed"
                raise RuntimeError(msg)

        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"retry": _retry_once},
        )
        plan = Plan(
            plan_id="retry",
            steps=[PlanStep(task_id="s1", action="retry", max_retries=2, retry_delay_seconds=0)],
        )
        report = exe.execute(plan)
        assert report.steps[0].result == StepResult.SUCCESS
        assert call_count[0] == 2

    def test_retry_exhausted(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"always_fail": _fail},
        )
        plan = Plan(
            plan_id="retry-exhaust",
            steps=[PlanStep(task_id="s1", action="always_fail", max_retries=1, retry_delay_seconds=0)],
        )
        report = exe.execute(plan)
        assert report.steps[0].result == StepResult.FAILURE
        assert report.steps[0].retries == 1

    def test_missing_handler(self):
        exe = PlanExecutor(governance_check=_always_allow)
        plan = Plan(
            plan_id="no-handler",
            steps=[PlanStep(task_id="s1", action="nonexistent")],
        )
        report = exe.execute(plan)
        assert report.steps[0].result == StepResult.SKIPPED
        assert "No handler" in (report.steps[0].error or "")

    def test_cycle_detection(self):
        exe = PlanExecutor()
        plan = Plan(
            plan_id="cycle",
            steps=[
                PlanStep(task_id="a", action="read", depends_on=["b"]),
                PlanStep(task_id="b", action="write", depends_on=["a"]),
            ],
        )
        report = exe.execute(plan)
        assert report.status == PlanStatus.FAILED
        assert "cycle" in (report.error or "").lower()

    def test_register_handler_dynamically(self):
        exe = PlanExecutor(governance_check=_always_allow)
        exe.register_handler("dynamic", _succeed)
        plan = Plan(
            plan_id="dynamic",
            steps=[PlanStep(task_id="s1", action="dynamic")],
        )
        report = exe.execute(plan)
        assert report.steps[0].result == StepResult.SUCCESS

    def test_execution_report_to_dict(self):
        exe = PlanExecutor(
            governance_check=_always_allow,
            action_handlers={"test": _succeed},
        )
        report = exe.execute(Plan(
            plan_id="dict-test",
            steps=[PlanStep(task_id="s1", action="test")],
        ))
        d = report.to_dict()
        assert d["plan_id"] == "dict-test"
        assert d["status"] == "completed"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["action"] == "test"
        assert d["steps"][0]["result"] == "success"
