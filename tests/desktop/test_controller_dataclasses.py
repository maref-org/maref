from __future__ import annotations

import json

from maref.desktop.controller import (
    DesktopOperation,
    DesktopOperationType,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    HistoryDatabase,
    OperationMode,
    PersistedExecution,
)
from maref.desktop.input_controller import SafetyDecision


class TestDesktopOperation:
    def test_to_dict(self) -> None:
        op = DesktopOperation(
            op_type=DesktopOperationType.CLICK,
            params={"x": 100, "y": 200},
            description="Click button",
        )
        d = op.to_dict()
        assert d["op_type"] == "click"
        assert d["params"]["x"] == 100
        assert d["description"] == "Click button"


class TestExecutionStep:
    def test_to_dict(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 1, "y": 2})
        step = ExecutionStep(
            step_index=0,
            operation=op,
            success=True,
            duration_ms=10.5,
            safety_decision=SafetyDecision.ALLOW.value,
            verification_passed=True,
            verification_diff_pct=0.01,
        )
        d = step.to_dict()
        assert d["step_index"] == 0
        assert d["success"] is True
        assert d["safety_decision"] == "allow"
        assert d["duration_ms"] == 10.5
        assert d["verification_diff_pct"] == 0.01


class TestExecutionPlan:
    def test_add_step(self) -> None:
        plan = ExecutionPlan(plan_id="plan-1", description="test")
        assert len(plan.steps) == 0
        plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK))
        assert len(plan.steps) == 1

    def test_to_dict(self) -> None:
        plan = ExecutionPlan(
            plan_id="plan-1",
            description="test plan",
        )
        plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 100}))
        d = plan.to_dict()
        assert d["plan_id"] == "plan-1"
        assert len(d["steps"]) == 1
        assert "Finder" in d["safe_apps"]


class TestExecutionResult:
    def test_to_dict(self) -> None:
        op = DesktopOperation(op_type=DesktopOperationType.WAIT, params={"seconds": 1})
        step = ExecutionStep(step_index=0, operation=op, success=True)
        result = ExecutionResult(
            plan_id="plan-1",
            success=True,
            steps=[step],
            total_duration_ms=100.0,
            governance_state="healthy",
        )
        d = result.to_dict()
        assert d["plan_id"] == "plan-1"
        assert d["success"] is True
        assert len(d["steps"]) == 1
        assert d["governance_state"] == "healthy"


class TestPersistedExecution:
    def test_to_dict(self) -> None:
        plan = {"plan_id": "p1", "steps": []}
        result = {"success": True, "plan_id": "p1", "steps": []}
        pe = PersistedExecution(
            id=1,
            plan_id="p1",
            description="test",
            plan_json=json.dumps(plan),
            result_json=json.dumps(result),
            created_at=1000.0,
            executed_at=1001.0,
            success=True,
        )
        d = pe.to_dict()
        assert d["id"] == 1
        assert d["plan_id"] == "p1"
        assert d["plan"] == plan
        assert d["result"] == result
        assert d["success"] is True

    def test_to_dict_no_result(self) -> None:
        plan = {"plan_id": "p1", "steps": []}
        pe = PersistedExecution(
            id=2,
            plan_id="p1",
            description="no result",
            plan_json=json.dumps(plan),
            result_json="",
            created_at=1000.0,
        )
        d = pe.to_dict()
        assert d["result"] is None
        assert d["success"] is False


class TestHistoryDatabase:
    def test_init_and_save_plan(self) -> None:
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test_maref.db")
        db = HistoryDatabase(db_path)
        plan = ExecutionPlan(plan_id="plan-1", description="test")
        eid = db.save_plan(plan)
        assert eid > 0

    def test_save_and_get_executions(self) -> None:
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test_maref2.db")
        db = HistoryDatabase(db_path)
        plan = ExecutionPlan(plan_id="plan-1", description="test")
        eid = db.save_plan(plan)

        result = ExecutionResult(plan_id="plan-1", success=True)
        db.save_result(eid, result)

        executions = db.get_executions()
        assert len(executions) >= 1

    def test_save_result_with_steps(self) -> None:
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test_maref3.db")
        db = HistoryDatabase(db_path)
        plan = ExecutionPlan(plan_id="plan-1", description="test")
        plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 10}))
        eid = db.save_plan(plan)

        op = DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 10})
        step = ExecutionStep(step_index=0, operation=op, success=True)
        result = ExecutionResult(plan_id="plan-1", success=True, steps=[step])
        db.save_result(eid, result)

        ops = db.get_operations(eid)
        assert len(ops) >= 1
        assert ops[0]["step_index"] == 0

    def test_get_operations_empty(self) -> None:
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test_maref4.db")
        db = HistoryDatabase(db_path)
        ops = db.get_operations(999)
        assert ops == []

    def test_get_executions_limit(self) -> None:
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test_maref5.db")
        db = HistoryDatabase(db_path)
        for i in range(3):
            db.save_plan(ExecutionPlan(plan_id=f"plan-{i}", description=f"test {i}"))
        executions = db.get_executions(limit=2)
        assert len(executions) <= 2
