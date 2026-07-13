from __future__ import annotations

from maref.desktop.controller import DesktopOperation, DesktopOperationType, ExecutionPlan, ExecutionResult, ExecutionStep, PersistedExecution


class TestDesktopOperationType:
    def test_values(self) -> None:
        assert DesktopOperationType.CLICK.value == "click"
        assert DesktopOperationType.DOUBLE_CLICK.value == "double_click"
        assert DesktopOperationType.RIGHT_CLICK.value == "right_click"
        assert DesktopOperationType.TYPE.value == "type"
        assert DesktopOperationType.HOTKEY.value == "hotkey"
        assert DesktopOperationType.SCROLL.value == "scroll"
        assert DesktopOperationType.DRAG.value == "drag"
        assert DesktopOperationType.WAIT.value == "wait"
        assert DesktopOperationType.SCREENSHOT.value == "screenshot"
        assert DesktopOperationType.PARSE.value == "parse"

    def test_enum_members(self) -> None:
        assert len(DesktopOperationType) == 10


class TestDesktopOperation:
    def test_defaults(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.CLICK)
        assert op.op_type == DesktopOperationType.CLICK
        assert op.params == {}
        assert op.description == ""

    def test_with_params(self) -> None:
        op = DesktopOperation(
            op_type=DesktopOperationType.TYPE,
            params={"text": "hello"},
            description="type hello",
        )
        assert op.op_type == DesktopOperationType.TYPE
        assert op.params == {"text": "hello"}
        assert op.description == "type hello"

    def test_to_dict(self) -> None:
        op = DesktopOperation(
            op_type=DesktopOperationType.CLICK,
            params={"x": 100, "y": 200},
            description="click button",
        )
        d = op.to_dict()
        assert d["op_type"] == "click"
        assert d["params"] == {"x": 100, "y": 200}
        assert d["description"] == "click button"


class TestExecutionStep:
    def test_defaults(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.CLICK)
        step = ExecutionStep(step_index=0, operation=op, success=True)
        assert step.step_index == 0
        assert step.operation is op
        assert step.success is True
        assert step.duration_ms == 0.0
        assert step.error == ""
        assert step.safety_decision == "allow"

    def test_with_values(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.WAIT, params={"ms": 500})
        step = ExecutionStep(
            step_index=1,
            operation=op,
            success=False,
            duration_ms=123.456,
            error="timeout",
            safety_decision="block",
            verification_passed=False,
            verification_diff_pct=5.0,
        )
        assert step.step_index == 1
        assert step.duration_ms == 123.456
        assert step.error == "timeout"
        assert step.safety_decision == "block"
        assert step.verification_passed is False
        assert step.verification_diff_pct == 5.0

    def test_to_dict(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.CLICK)
        step = ExecutionStep(
            step_index=0, operation=op, success=True, duration_ms=50.0
        )
        d = step.to_dict()
        assert d["step_index"] == 0
        assert d["success"] is True
        assert d["duration_ms"] == 50.0


class TestExecutionPlan:
    def test_defaults(self) -> None:
        plan = ExecutionPlan(plan_id="p1")
        assert plan.plan_id == "p1"
        assert plan.description == ""
        assert plan.steps == []
        assert "Finder" in plan.safe_apps

    def test_add_step(self) -> None:
        plan = ExecutionPlan(plan_id="p1", description="test plan")
        op = DesktopOperation(op_type=DesktopOperationType.CLICK)
        plan.add_step(op)
        assert len(plan.steps) == 1
        assert plan.steps[0] is op

    def test_to_dict(self) -> None:
        plan = ExecutionPlan(plan_id="p1")
        op = DesktopOperation(op_type=DesktopOperationType.CLICK)
        plan.add_step(op)
        d = plan.to_dict()
        assert d["plan_id"] == "p1"
        assert len(d["steps"]) == 1
        assert isinstance(d["safe_apps"], list)


class TestExecutionResult:
    def test_defaults(self) -> None:
        result = ExecutionResult(plan_id="p1", success=True)
        assert result.plan_id == "p1"
        assert result.success is True
        assert result.steps == []
        assert result.total_duration_ms == 0.0
        assert result.governance_state == "healthy"

    def test_to_dict(self) -> None:
        result = ExecutionResult(plan_id="p1", success=False, total_duration_ms=1500.0)
        d = result.to_dict()
        assert d["plan_id"] == "p1"
        assert d["success"] is False
        assert d["total_duration_ms"] == 1500.0


class TestPersistedExecution:
    def test_defaults(self) -> None:
        pe = PersistedExecution(
            id=1,
            plan_id="p1",
            description="test",
            plan_json='{"steps":[]}',
            result_json='{"success":true}',
            created_at=1000.0,
        )
        assert pe.id == 1
        assert pe.plan_id == "p1"
        assert pe.executed_at == 0.0
        assert pe.success is False

    def test_with_values(self) -> None:
        pe = PersistedExecution(
            id=2,
            plan_id="p2",
            description="executed",
            plan_json="{}",
            result_json="{}",
            created_at=1000.0,
            executed_at=2000.0,
            success=True,
        )
        assert pe.executed_at == 2000.0
        assert pe.success is True
