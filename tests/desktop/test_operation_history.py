"""Tests for DesktopController operation history persistence and recovery."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from maref.desktop.controller import (
    DesktopController,
    DesktopOperation,
    DesktopOperationType,
    ExecutionPlan,
    HistoryDatabase,
)


class TestHistoryDatabase:
    def test_init_creates_tables(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = HistoryDatabase(db_path)
            conn = sqlite3.connect(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            table_names = [t[0] for t in tables]
            assert "executions" in table_names
            assert "operations" in table_names
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_save_and_get_executions(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = HistoryDatabase(db_path)
            plan = ExecutionPlan(plan_id="test-plan-001", description="Test plan")
            plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 10, "y": 10}))

            eid = db.save_plan(plan)
            assert eid is not None

            executions = db.get_executions(limit=10)
            assert len(executions) == 1
            assert executions[0]["plan_id"] == "test-plan-001"
            assert executions[0]["description"] == "Test plan"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_limit_executions(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = HistoryDatabase(db_path)
            for i in range(15):
                plan = ExecutionPlan(plan_id=f"plan-{i}")
                db.save_plan(plan)

            executions = db.get_executions(limit=10)
            assert len(executions) == 10
            assert executions[0]["plan_id"] == "plan-14"
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestOperationHistoryPersistence:
    def test_history_persists_across_controller_restarts(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            controller1 = DesktopController(dry_run=True, history_db=db_path, parser_backend="mock")
            plan = ExecutionPlan(plan_id="persistence-test", description="Test persistence")
            plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 100, "y": 100}, description="Click test"))
            plan.add_step(DesktopOperation(op_type=DesktopOperationType.TYPE, params={"text": "Hello"}, description="Type test"))

            result = controller1.execute_and_persist(plan)
            assert result["success"] is True

            del controller1

            controller2 = DesktopController(dry_run=True, history_db=db_path, parser_backend="mock")
            history = controller2.get_history(limit=10)
            assert len(history) == 1
            assert history[0]["plan_id"] == "persistence-test"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_multiple_executions_preserved(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            controller = DesktopController(dry_run=True, history_db=db_path, parser_backend="mock")

            for i in range(5):
                plan = ExecutionPlan(plan_id=f"exec-{i}", description=f"Execution {i}")
                plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": i, "y": i}))
                controller.execute_and_persist(plan)

            history = controller.get_history(limit=10)
            assert len(history) == 5
            plan_ids = [h["plan_id"] for h in history]
            assert "exec-0" in plan_ids
            assert "exec-4" in plan_ids
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_execution_details_include_operations(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            controller = DesktopController(dry_run=True, history_db=db_path, parser_backend="mock")
            plan = ExecutionPlan(plan_id="details-test", description="Test details")
            plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 50, "y": 50}, description="Step 1"))
            plan.add_step(DesktopOperation(op_type=DesktopOperationType.TYPE, params={"text": "test"}, description="Step 2"))

            result = controller.execute_and_persist(plan)
            execution_id = result.get("execution_id")

            if execution_id:
                details = controller.get_execution_details(execution_id)
                assert "operations" in details
                assert len(details["operations"]) == 2
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestDesktopSafetyGateMemoryLimit:
    def test_operation_history_bounded(self) -> None:
        from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2, DesktopThreatAssessment, DesktopThreatSeverity, DesktopThreatCategory

        gate = DesktopSafetyGateV2(max_operation_history=10)
        for i in range(25):
            gate.record_operation("click", f"target-{i}", success=True)

        assert len(gate._operation_history) <= 10
        recent_targets = [r.target for r in gate._operation_history]
        assert "target-24" in recent_targets
        assert "target-0" not in recent_targets

    def test_default_max_operation_history(self) -> None:
        from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2

        gate = DesktopSafetyGateV2()
        assert gate._max_operation_history == DesktopSafetyGateV2.MAX_OPERATION_HISTORY
