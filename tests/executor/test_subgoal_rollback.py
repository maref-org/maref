"""Tests for WorkflowEngine cascading rollback / compensation (G5).

Verifies:
- WorkflowStep.on_failure="rollback" triggers compensation
- BlastRadiusController limits compensation scope
- Compensation handler registration and execution
- Rollback failure handling
"""

from __future__ import annotations

from maref.executor.types import Task
from maref.executor.workflow.engine import WorkflowEngine
from maref.executor.workflow.types import StepStatus, WorkflowScript, WorkflowStep
from maref.recursive.blast_radius import (
    BlastRadiusConfig,
    BlastRadiusController,
    CompensationStrategy,
)


class _MockPool:
    def __init__(self):
        self._handlers: dict = {}


def _make_handler(success: bool = True):
    def handler(task: Task) -> None:
        if not success:
            raise RuntimeError("handler failed")
    return handler


class TestWorkflowStepCompensationFields:
    def test_on_failure_default_is_fail(self):
        s = WorkflowStep(name="test")
        assert s.on_failure == "fail"

    def test_compensation_step_default_empty(self):
        s = WorkflowStep(name="test")
        assert s.compensation_step == ""

    def test_to_dict_includes_new_fields(self):
        s = WorkflowStep(name="x", on_failure="rollback", compensation_step="undo_x")
        d = s.to_dict()
        assert d["on_failure"] == "rollback"
        assert d["compensation_step"] == "undo_x"

    def test_from_dict_roundtrip(self):
        s = WorkflowStep.from_dict({
            "name": "a", "on_failure": "rollback", "compensation_step": "undo_a"
        })
        assert s.on_failure == "rollback"
        assert s.compensation_step == "undo_a"


class TestWorkflowEngineCompensation:
    def test_register_compensation_handler(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        engine.register_handler("compensate:step_a", _make_handler())
        assert "compensate:step_a" in engine._handlers

    def test_compensate_step_calls_handler(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        called = []

        def recorder(task):
            called.append(task.payload["step_name"])

        engine.register_handler("compensate:step_a", recorder)
        sr = engine._compensate_step("step_a", "step_b")
        assert sr.status == StepStatus.COMPLETED
        assert called == ["step_a"]

    def test_compensate_step_no_handler(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        sr = engine._compensate_step("step_a", "step_b")
        assert sr.status == StepStatus.FAILED
        assert "No compensation handler" in sr.error_message

    def test_compensate_step_handler_failure(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        engine.register_handler("compensate:step_a", _make_handler(success=False))
        sr = engine._compensate_step("step_a", "step_b")
        assert sr.status == StepStatus.FAILED
        assert "handler failed" in sr.error_message

    def test_rollback_triggers_compensation(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        engine.register_handler("good_handler", _make_handler(success=True))
        engine.register_handler("bad_handler", _make_handler(success=False))
        engine.register_handler("compensate:step_a", _make_handler())

        script = WorkflowScript(
            name="test",
            steps=[
                WorkflowStep(name="step_a", agent_role="good_handler"),
                WorkflowStep(name="step_b", agent_role="bad_handler",
                             on_failure="rollback"),
            ],
        )
        result = engine.execute(script)
        assert result.status.name == "FAILED"
        comp_results = [s for s in result.step_results if "compensate:" in s.step_name]
        assert len(comp_results) >= 1

    def test_on_failure_fail_skips_compensation(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        engine.register_handler("step_handler", _make_handler(success=False))
        engine.register_handler("compensate:step_a", _make_handler())

        script = WorkflowScript(
            name="test",
            steps=[
                WorkflowStep(name="step_a", agent_role="step_handler"),
                WorkflowStep(name="step_b", agent_role="step_handler",
                             on_failure="fail"),
            ],
        )
        result = engine.execute(script)
        comp_results = [s for s in result.step_results if "compensate:" in s.step_name]
        assert len(comp_results) == 0

    def test_multi_step_rollback_compensates_all(self):
        pool = _MockPool()
        engine = WorkflowEngine(pool)
        engine.register_handler("ok_handler", _make_handler(success=True))
        engine.register_handler("fail_handler", _make_handler(success=False))
        engine.register_handler("compensate:step_a", _make_handler())
        engine.register_handler("compensate:step_b", _make_handler())

        script = WorkflowScript(
            name="test",
            steps=[
                WorkflowStep(name="step_a", agent_role="ok_handler"),
                WorkflowStep(name="step_b", agent_role="ok_handler"),
                WorkflowStep(name="step_c", agent_role="fail_handler",
                             on_failure="rollback"),
            ],
        )
        result = engine.execute(script)
        comp_names = [s.step_name for s in result.step_results if "compensate:" in s.step_name]
        assert "compensate:step_a" in comp_names
        assert "compensate:step_b" in comp_names

    def test_blast_radius_limits_compensation(self):
        config = BlastRadiusConfig(strategy=CompensationStrategy.PARTIAL, max_radius=1)
        controller = BlastRadiusController(config)
        pool = _MockPool()
        engine = WorkflowEngine(pool, blast_radius=controller)
        engine.register_handler("ok_handler", _make_handler(success=True))
        engine.register_handler("fail_handler", _make_handler(success=False))
        engine.register_handler("compensate:step_a", _make_handler())
        engine.register_handler("compensate:step_b", _make_handler())

        script = WorkflowScript(
            name="test",
            steps=[
                WorkflowStep(name="step_a", agent_role="ok_handler"),
                WorkflowStep(name="step_b", agent_role="ok_handler"),
                WorkflowStep(name="step_c", agent_role="fail_handler",
                             on_failure="rollback"),
            ],
        )
        result = engine.execute(script)
        comp_names = [s.step_name for s in result.step_results if "compensate:" in s.step_name]
        assert len(comp_names) == 1
        assert comp_names[0] == "compensate:step_b"
