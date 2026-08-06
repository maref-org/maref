from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from maref.executor.types import Task
from maref.executor.worker import WorkerPool
from maref.executor.workflow.engine import (
    CircularDependencyError,
    GovernanceBlockedError,
    WorkflowEngine,
    WorkflowError,
    _topological_groups,
    _topological_sort,
)
from maref.executor.workflow.generator import WorkflowScriptGenerator, _parse_json
from maref.executor.workflow.patterns.base import PatternResult
from maref.executor.workflow.patterns.fan_out import FanOutConfig, FanOutPattern
from maref.executor.workflow.patterns.generate_filter import (
    GenerateFilterConfig,
    GenerateFilterPattern,
)
from maref.executor.workflow.types import (
    StepResult,
    StepStatus,
    WorkflowCheckpoint,
    WorkflowResult,
    WorkflowScript,
    WorkflowStatus,
    WorkflowStep,
    _now,
)


# ── Helpers ─────────────────────────────────────────────────────────

class FakeGovernance:
    def __init__(self, allow: bool = True):
        self.allow = allow
        self.records: list[tuple[str, bool]] = []
        self.state_name = "TEST"

    def check(self, stage: str) -> bool:
        return self.allow

    def record(self, stage: str, allowed: bool) -> None:
        self.records.append((stage, allowed))


def _make_pool(db_path: str, handlers: dict[str, Callable] | None = None) -> WorkerPool:
    from maref.executor.queue import TaskQueue
    queue = TaskQueue(db_path)
    pool = WorkerPool(queue, num_workers=2)
    if handlers:
        for name, handler in handlers.items():
            pool.register_handler(name, handler)
    return pool


# ====================================================================
# types.py
# ====================================================================

class TestWorkflowStep:
    def test_to_dict_roundtrip(self) -> None:
        step = WorkflowStep(
            name="analyze",
            description="分析输入",
            agent_role="analyzer",
            input_template="分析 {data}",
            validator_prompt="检查输出格式",
            timeout_seconds=120,
            max_retries=2,
            depends_on=["setup"],
            fallback_step="analyze_fallback",
            parallel_group="group1",
            metadata={"key": "val"},
        )
        d = step.to_dict()
        restored = WorkflowStep.from_dict(d)
        assert restored.name == "analyze"
        assert restored.agent_role == "analyzer"
        assert restored.depends_on == ["setup"]
        assert restored.parallel_group == "group1"
        assert restored.metadata == {"key": "val"}

    def test_defaults(self) -> None:
        step = WorkflowStep(name="test")
        assert step.description == ""
        assert step.agent_role == ""
        assert step.depends_on == []
        assert step.max_retries == 0
        assert step.timeout_seconds == 0.0
        assert step.metadata == {}

    def test_from_dict_minimal(self) -> None:
        step = WorkflowStep.from_dict({"name": "minimal"})
        assert step.name == "minimal"
        assert step.description == ""

    def test_serialization_json(self) -> None:
        step = WorkflowStep(name="json-test", metadata={"nested": {"list": [1, 2]}})
        d = step.to_dict()
        loaded = json.loads(json.dumps(d))
        restored = WorkflowStep.from_dict(loaded)
        assert restored.name == "json-test"
        assert restored.metadata == {"nested": {"list": [1, 2]}}


class TestWorkflowScript:
    def test_step_names(self) -> None:
        script = WorkflowScript(
            name="test",
            steps=[WorkflowStep(name="a"), WorkflowStep(name="b")],
        )
        assert script.step_names() == ["a", "b"]

    def test_get_step(self) -> None:
        script = WorkflowScript(
            steps=[
                WorkflowStep(name="find", description="寻找"),
                WorkflowStep(name="write", description="撰写"),
            ],
        )
        assert script.get_step("find") is not None
        assert script.get_step("find").description == "寻找"
        assert script.get_step("nonexistent") is None

    def test_parallel_groups(self) -> None:
        script = WorkflowScript(
            steps=[
                WorkflowStep(name="a", parallel_group="g1"),
                WorkflowStep(name="b", parallel_group="g1"),
                WorkflowStep(name="c", parallel_group="g2"),
                WorkflowStep(name="d"),
            ],
        )
        groups = script.parallel_groups()
        assert len(groups["g1"]) == 2
        assert len(groups["g2"]) == 1

    def test_to_dict_roundtrip(self) -> None:
        script = WorkflowScript(
            name="test-script",
            description="a test",
            steps=[
                WorkflowStep(name="step1", agent_role="analyzer"),
                WorkflowStep(name="step2", agent_role="writer", depends_on=["step1"]),
            ],
            max_concurrency=8,
            checkpoint_interval=3,
        )
        d = script.to_dict()
        restored = WorkflowScript.from_dict(d)
        assert restored.name == "test-script"
        assert len(restored.steps) == 2
        assert restored.steps[1].depends_on == ["step1"]
        assert restored.max_concurrency == 8

    def test_new_id_is_unique(self) -> None:
        s1 = WorkflowScript()
        s2 = WorkflowScript()
        assert s1.id != s2.id

    def test_empty_script(self) -> None:
        script = WorkflowScript()
        assert script.step_names() == []
        assert script.get_step("x") is None
        assert script.parallel_groups() == {}


class TestWorkflowResult:
    def test_summary(self) -> None:
        result = WorkflowResult(
            script_id="s1",
            status=WorkflowStatus.COMPLETED,
            step_results=[
                StepResult(step_name="a", status=StepStatus.COMPLETED),
                StepResult(step_name="b", status=StepStatus.COMPLETED),
                StepResult(step_name="c", status=StepStatus.FAILED),
            ],
            total_duration_ms=1500.0,
        )
        sm = result.summary()
        assert sm["status"] == "completed"
        assert sm["steps"]["total"] == 3
        assert sm["steps"]["completed"] == 2
        assert sm["steps"]["failed"] == 1

    def test_failed_steps(self) -> None:
        result = WorkflowResult(script_id="s1")
        result.step_results = [
            StepResult(step_name="a", status=StepStatus.COMPLETED),
            StepResult(step_name="b", status=StepStatus.FAILED),
        ]
        assert len(result.failed_steps()) == 1
        assert result.failed_steps()[0].step_name == "b"

    def test_get_step_result(self) -> None:
        result = WorkflowResult(script_id="s1")
        result.step_results = [
            StepResult(step_name="step_x", status=StepStatus.COMPLETED),
        ]
        assert result.get_step_result("step_x").status == StepStatus.COMPLETED
        assert result.get_step_result("nonexistent") is None

    def test_defaults(self) -> None:
        result = WorkflowResult()
        assert result.status == WorkflowStatus.COMPLETED
        assert result.step_results == []
        assert result.total_duration_ms == 0.0

    def test_no_failed_steps_when_all_succeed(self) -> None:
        result = WorkflowResult(script_id="s1")
        result.step_results = [
            StepResult(step_name="a", status=StepStatus.COMPLETED),
        ]
        assert result.failed_steps() == []


class TestWorkflowCheckpoint:
    def test_to_dict(self) -> None:
        cp = WorkflowCheckpoint(
            script=WorkflowScript(name="s1", steps=[WorkflowStep(name="a")]),
            last_completed_step=0,
            step_results=[StepResult(step_name="a", status=StepStatus.COMPLETED)],
        )
        d = cp.to_dict()
        assert d["last_completed_step"] == 0
        assert d["step_results"][0]["step_name"] == "a"
        assert d["script"]["name"] == "s1"

    def test_from_to_dict_consistency(self) -> None:
        cp = WorkflowCheckpoint(id="cp1")
        d = cp.to_dict()
        assert d["id"] == "cp1"

    def test_defaults(self) -> None:
        cp = WorkflowCheckpoint()
        assert cp.id is not None
        assert cp.last_completed_step == 0
        assert cp.step_results == []


class TestStepResult:
    def test_defaults(self) -> None:
        sr = StepResult()
        assert sr.status == StepStatus.COMPLETED
        assert sr.output == {}
        assert sr.duration_ms == 0.0

    def test_with_values(self) -> None:
        sr = StepResult(
            step_name="s1",
            status=StepStatus.FAILED,
            error_message="oops",
            duration_ms=100.0,
        )
        assert sr.step_name == "s1"
        assert sr.status == StepStatus.FAILED
        assert sr.error_message == "oops"
        assert sr.duration_ms == 100.0


class TestStepStatus:
    def test_values(self) -> None:
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"


class TestWorkflowStatus:
    def test_values(self) -> None:
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"


# ====================================================================
# engine.py
# ====================================================================

class TestTopologicalSort:
    def test_no_deps(self) -> None:
        steps = [WorkflowStep(name="a"), WorkflowStep(name="b")]
        sorted_steps = _topological_sort(steps)
        assert [s.name for s in sorted_steps] == ["a", "b"]

    def test_with_deps(self) -> None:
        steps = [
            WorkflowStep(name="a"),
            WorkflowStep(name="c", depends_on=["b"]),
            WorkflowStep(name="b", depends_on=["a"]),
        ]
        sorted_steps = _topological_sort(steps)
        names = [s.name for s in sorted_steps]
        assert names.index("a") < names.index("b")
        assert names.index("b") < names.index("c")

    def test_unknown_dep_raises(self) -> None:
        steps = [WorkflowStep(name="a", depends_on=["nonexistent"])]
        with pytest.raises(WorkflowError, match="unknown step"):
            _topological_sort(steps)

    def test_circular_dep_raises(self) -> None:
        steps = [
            WorkflowStep(name="a", depends_on=["b"]),
            WorkflowStep(name="b", depends_on=["a"]),
        ]
        with pytest.raises(CircularDependencyError):
            _topological_sort(steps)

    def test_self_dep_raises(self) -> None:
        steps = [WorkflowStep(name="a", depends_on=["a"])]
        with pytest.raises(CircularDependencyError):
            _topological_sort(steps)


class TestTopologicalGroups:
    def test_simple_layering(self) -> None:
        steps = [
            WorkflowStep(name="a"),
            WorkflowStep(name="b", depends_on=["a"]),
            WorkflowStep(name="c", depends_on=["a"]),
            WorkflowStep(name="d", depends_on=["b", "c"]),
        ]
        groups = _topological_groups(steps)
        assert len(groups) == 3
        assert groups[0][0].name == "a"
        assert {s.name for s in groups[1]} == {"b", "c"}
        assert groups[2][0].name == "d"

    def test_single_step(self) -> None:
        groups = _topological_groups([WorkflowStep(name="a")])
        assert len(groups) == 1
        assert groups[0][0].name == "a"

    def test_no_groups_when_no_steps(self) -> None:
        groups = _topological_groups([])
        assert len(groups) == 0 or (len(groups) == 1 and len(groups[0]) == 0)


class TestWorkflowEngine:
    def test_sequential_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            executed: list[str] = []

            def handler_a(task: Task) -> None:
                executed.append("a")
                task.payload["result"] = {"output": "A done"}

            def handler_b(task: Task) -> None:
                executed.append("b")
                task.payload["result"] = {"output": "B done"}

            pool = _make_pool(db, {"step_a": handler_a, "step_b": handler_b})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="seq-test",
                steps=[
                    WorkflowStep(name="s1", agent_role="step_a"),
                    WorkflowStep(name="s2", agent_role="step_b", depends_on=["s1"]),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert executed == ["a", "b"]
            assert len(result.step_results) == 2
            for sr in result.step_results:
                assert sr.status == StepStatus.COMPLETED

    def test_step_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing_handler(task: Task) -> None:
                raise RuntimeError("intentional failure")

            pool = _make_pool(db, {"fail": failing_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="fail-test",
                steps=[WorkflowStep(name="s1", agent_role="fail")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "intentional failure" in result.error_message

    def test_handler_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="no-handler",
                steps=[WorkflowStep(name="s1", agent_role="nonexistent")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "No handler registered" in result.error_message

    def test_governance_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            governance = FakeGovernance(allow=False)

            pool = _make_pool(db, {"step": lambda t: None})
            engine = WorkflowEngine(pool, governance_bridge=governance)

            script = WorkflowScript(
                name="gov-block",
                steps=[WorkflowStep(name="s1", agent_role="step")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "Governance" in result.error_message

    def test_governance_allows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            governance = FakeGovernance(allow=True)

            def handler(task: Task) -> None:
                task.payload["result"] = {"output": "ok"}

            pool = _make_pool(db, {"step": handler})
            engine = WorkflowEngine(pool, governance_bridge=governance)

            script = WorkflowScript(
                steps=[WorkflowStep(name="s1", agent_role="step")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert governance.records == [("step", True)]

    def test_retry_then_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            attempt_count: list[int] = [0]

            def flaky_handler(task: Task) -> None:
                attempt_count[0] += 1
                if attempt_count[0] < 2:
                    raise RuntimeError(f"Attempt {attempt_count[0]} failed")
                task.payload["result"] = {"output": "success"}

            pool = _make_pool(db, {"flaky": flaky_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="retry-test",
                steps=[
                    WorkflowStep(name="s1", agent_role="flaky", max_retries=2),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert attempt_count[0] == 2

    def test_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def slow_handler(task: Task) -> None:
                time.sleep(5)

            pool = _make_pool(db, {"slow": slow_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="timeout-test",
                steps=[
                    WorkflowStep(name="s1", agent_role="slow", timeout_seconds=0.1),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED

    def test_parallel_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            order: list[str] = []
            lock = threading.Lock()

            def handler_a(task: Task) -> None:
                time.sleep(0.1)
                with lock:
                    order.append("a")
                task.payload["result"] = {"output": "A"}

            def handler_b(task: Task) -> None:
                time.sleep(0.05)
                with lock:
                    order.append("b")
                task.payload["result"] = {"output": "B"}

            pool = _make_pool(db, {"h_a": handler_a, "h_b": handler_b})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="parallel-test",
                steps=[
                    WorkflowStep(name="p1", agent_role="h_a", parallel_group="g1"),
                    WorkflowStep(name="p2", agent_role="h_b", parallel_group="g1"),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert len(result.step_results) == 2

    def test_fallback_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing_handler(task: Task) -> None:
                raise RuntimeError("main failed")

            def fallback_handler(task: Task) -> None:
                task.payload["result"] = {"output": "fallback used"}

            pool = _make_pool(db, {"main": failing_handler, "fb": fallback_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="fallback-test",
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="main",
                        max_retries=0,
                        fallback_step="s1_fallback",
                    ),
                    WorkflowStep(name="s1_fallback", agent_role="fb"),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            fallback_sr = result.get_step_result("s1→fallback:s1_fallback")
            assert fallback_sr is not None
            assert fallback_sr.status == StepStatus.COMPLETED

    def test_missing_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing_handler(task: Task) -> None:
                raise RuntimeError("fail")

            pool = _make_pool(db, {"main": failing_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="missing-fallback",
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="main",
                        max_retries=0,
                        fallback_step="nonexistent",
                    ),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "not found" in result.error_message

    def test_fallback_also_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def always_fails(task: Task) -> None:
                raise RuntimeError("always fails")

            pool = _make_pool(db, {"main": always_fails, "fb": always_fails})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="main",
                        max_retries=0,
                        fallback_step="s1_fallback",
                    ),
                    WorkflowStep(name="s1_fallback", agent_role="fb"),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "Fallback also failed" in result.step_results[-1].error_message

    def test_final_output_from_last_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def handler(task: Task) -> None:
                task.payload["result"] = {"output": "final result"}

            pool = _make_pool(db, {"h": handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="output-test",
                steps=[WorkflowStep(name="s1", agent_role="h")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert result.final_output == {"output": "final result"}

    def test_checkpoint_create_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            cp_dir = os.path.join(tmp, "checkpoints")
            executed: list[str] = []

            def handler_a(task: Task) -> None:
                executed.append("a")
                task.payload["result"] = {"output": "a"}

            def handler_b(task: Task) -> None:
                executed.append("b")
                task.payload["result"] = {"output": "b"}

            def handler_c(task: Task) -> None:
                executed.append("c")
                task.payload["result"] = {"output": "c"}

            pool = _make_pool(
                db, {"h_a": handler_a, "h_b": handler_b, "h_c": handler_c}
            )
            engine = WorkflowEngine(pool, checkpoint_dir=cp_dir)

            script = WorkflowScript(
                name="cp-test",
                steps=[
                    WorkflowStep(name="s1", agent_role="h_a"),
                    WorkflowStep(name="s2", agent_role="h_b", depends_on=["s1"]),
                    WorkflowStep(name="s3", agent_role="h_c", depends_on=["s2"]),
                ],
                checkpoint_interval=1,
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED

            checkpoints = engine.list_checkpoints()
            assert len(checkpoints) > 0

            resume_result = engine.resume(checkpoints[-1])
            assert resume_result.status == WorkflowStatus.COMPLETED

    def test_resume_without_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool, checkpoint_dir=os.path.join(tmp, "cps"))

            with pytest.raises(WorkflowError, match="not found"):
                engine.resume("nonexistent-checkpoint")

    def test_empty_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool)

            script = WorkflowScript(name="empty")
            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED

    def test_register_handlers_from_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def handler(task: Task) -> None:
                task.payload["result"] = {"ok": True}

            pool = _make_pool(db, {"my_handler": handler})
            engine = WorkflowEngine(pool)
            engine.register_handlers_from_pool()

            script = WorkflowScript(
                name="import-test",
                steps=[WorkflowStep(name="s1", agent_role="my_handler")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED

    def test_register_handler_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def handler(task: Task) -> None:
                task.payload["result"] = {"done": True}

            pool = _make_pool(db)
            engine = WorkflowEngine(pool)
            engine.register_handler("direct", handler)

            script = WorkflowScript(
                steps=[WorkflowStep(name="s1", agent_role="direct")],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED

    def test_list_checkpoints_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool, checkpoint_dir=os.path.join(tmp, "cps"))
            assert engine.list_checkpoints() == []

    def test_script_with_input_formatting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            received: list[str] = []

            def handler(task: Task) -> None:
                received.append(task.payload.get("input", ""))
                task.payload["result"] = {"output": "ok"}

            pool = _make_pool(db, {"h": handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="h",
                        input_template="analyze {topic}",
                    )
                ],
            )

            result = engine.execute(script, inputs={"topic": "AI safety"})
            assert result.status == WorkflowStatus.COMPLETED
            assert "analyze AI safety" in received

    def test_topological_sort_in_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(name="a", depends_on=["b"]),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "unknown step" in result.error_message

    def test_mixed_parallel_and_sequential_in_same_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            order: list[str] = []
            lock = threading.Lock()

            def handler_a(task: Task) -> None:
                with lock:
                    order.append("a")
                task.payload["result"] = {"output": "A"}

            def handler_b(task: Task) -> None:
                with lock:
                    order.append("b")
                task.payload["result"] = {"output": "B"}

            pool = _make_pool(db, {"h_a": handler_a, "h_b": handler_b})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(name="p1", agent_role="h_a", parallel_group="g1"),
                    WorkflowStep(name="s1", agent_role="h_b"),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert len(result.step_results) == 2

    def test_input_template_keyerror_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            received: list[str] = []

            def handler(task: Task) -> None:
                received.append(task.payload.get("input", ""))
                task.payload["result"] = {"output": "ok"}

            pool = _make_pool(db, {"h": handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="h",
                        input_template="process {missing_key}",
                    )
                ],
            )

            result = engine.execute(script, inputs={"unused": "val"})
            assert result.status == WorkflowStatus.COMPLETED
            assert "process {missing_key}" in received

    def test_parallel_group_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing(task: Task) -> None:
                raise RuntimeError("parallel fail")

            def ok(task: Task) -> None:
                task.payload["result"] = {"output": "ok"}

            pool = _make_pool(db, {"f": failing, "o": ok})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(name="p1", agent_role="f", parallel_group="g1"),
                    WorkflowStep(name="p2", agent_role="o", parallel_group="g1"),
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED
            assert "parallel fail" in result.error_message

    def test_validator_handler_called(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            validated: list[bool] = []

            def main_handler(task: Task) -> None:
                task.payload["result"] = {"output": "data"}

            def validator_handler(task: Task) -> None:
                validated.append(True)
                task.payload["result"] = {"passed": True}

            pool = _make_pool(db, {"step": main_handler, "step.validator": validator_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="step",
                        validator_prompt="Check output quality",
                    )
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert len(validated) == 1

    def test_validator_handler_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def main_handler(task: Task) -> None:
                task.payload["result"] = {"output": "bad data"}

            def validator_handler(task: Task) -> None:
                task.payload["result"] = {"passed": False, "issues": ["quality low"]}

            pool = _make_pool(db, {"step": main_handler, "step.validator": validator_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="step",
                        validator_prompt="Check output quality",
                    )
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert result.step_results[0].metadata.get("validation_issues") == ["quality low"]


# ====================================================================
# generator.py
# ====================================================================

class TestParseJson:
    def test_direct_json(self) -> None:
        result = _parse_json('{"name": "test"}')
        assert result == {"name": "test"}

    def test_code_fence(self) -> None:
        result = _parse_json('```json\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_plain_code_fence(self) -> None:
        result = _parse_json('```\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_embedded_json(self) -> None:
        result = _parse_json("Some text\n{\"name\": \"test\"}\nmore text")
        assert result == {"name": "test"}

    def test_invalid_input(self) -> None:
        result = _parse_json("not json at all")
        assert result is None

    def test_broken_json_inside_code_fence(self) -> None:
        result = _parse_json("```json\n{invalid}\n```")
        assert result is None

    def test_empty_string(self) -> None:
        result = _parse_json("")
        assert result is None


class TestWorkflowScriptGenerator:
    def test_from_dict(self) -> None:
        data = {
            "name": "test-script",
            "description": "A test",
            "steps": [
                {"name": "analyze", "agent_role": "analyzer", "input_template": "do analysis"},
                {"name": "write", "agent_role": "writer", "depends_on": ["analyze"]},
            ],
        }
        script = WorkflowScriptGenerator.from_dict(data)
        assert script.name == "test-script"
        assert len(script.steps) == 2
        assert script.steps[1].depends_on == ["analyze"]

    def test_from_step_list(self) -> None:
        steps: list[dict[str, Any]] = [
            {"name": "a", "agent_role": "analyzer"},
            {"name": "b", "agent_role": "writer", "depends_on": ["a"]},
        ]
        script = WorkflowScriptGenerator.from_step_list(steps, name="manual")
        assert script.name == "manual"
        assert len(script.steps) == 2

    def test_from_step_list_default_name(self) -> None:
        steps = [{"name": "a", "agent_role": "analyzer"}]
        script = WorkflowScriptGenerator.from_step_list(steps)
        assert script.name == "generated-script"

    def test_generate_requires_model(self) -> None:
        gen = WorkflowScriptGenerator()
        with pytest.raises(RuntimeError, match="No model_adapter"):
            gen.generate("do something")

    def test_generate_with_fake_model(self) -> None:
        class FakeModel:
            def complete(self, prompt: str) -> str:
                return json.dumps({
                    "name": "generated",
                    "description": "auto-generated",
                    "steps": [
                        {
                            "name": "analyze",
                            "agent_role": "analyzer",
                            "input_template": "analyze the input",
                            "validator_prompt": "",
                            "timeout_seconds": 120,
                            "max_retries": 1,
                            "depends_on": [],
                            "fallback_step": "",
                            "parallel_group": "",
                        }
                    ],
                })

        gen = WorkflowScriptGenerator(model_adapter=FakeModel())
        script = gen.generate("test task")
        assert script.name == "test task"
        assert len(script.steps) == 1
        assert script.steps[0].agent_role == "analyzer"

    def test_generate_with_name(self) -> None:
        class FakeModel:
            def complete(self, prompt: str) -> str:
                return json.dumps({
                    "name": "ai-name",
                    "steps": [
                        {
                            "name": "a",
                            "agent_role": "analyzer",
                            "input_template": "do it",
                            "validator_prompt": "",
                            "timeout_seconds": 60,
                            "max_retries": 1,
                            "depends_on": [],
                            "fallback_step": "",
                            "parallel_group": "",
                        }
                    ],
                })

        gen = WorkflowScriptGenerator(model_adapter=FakeModel())
        script = gen.generate("test task", name="custom-name")
        assert script.name == "custom-name"

    def test_generate_parsing_failure(self) -> None:
        class FakeModel:
            def complete(self, prompt: str) -> str:
                return "not json at all"

        gen = WorkflowScriptGenerator(model_adapter=FakeModel())
        with pytest.raises(ValueError, match="Failed to parse"):
            gen.generate("whatever")

    def test_generate_with_prompt(self) -> None:
        class FakeModel:
            def complete(self, prompt: str) -> str:
                assert "Custom system" in prompt
                assert "my task" in prompt
                return json.dumps({
                    "steps": [
                        {
                            "name": "a",
                            "agent_role": "analyzer",
                            "input_template": "do it",
                            "validator_prompt": "",
                            "timeout_seconds": 60,
                            "max_retries": 1,
                            "depends_on": [],
                            "fallback_step": "",
                            "parallel_group": "",
                        }
                    ],
                })

        gen = WorkflowScriptGenerator(model_adapter=FakeModel())
        script = gen.generate_with_prompt("Custom system prompt", "my task")
        assert script.name == "my task"
        assert len(script.steps) == 1

    def test_generate_with_prompt_no_model(self) -> None:
        gen = WorkflowScriptGenerator()
        with pytest.raises(RuntimeError, match="No model_adapter"):
            gen.generate_with_prompt("sys prompt", "task")

    def test_parsed_to_script_uses_name_from_parsed(self) -> None:
        class FakeModel:
            def complete(self, prompt: str) -> str:
                return json.dumps({
                    "name": "from-llm",
                    "description": "desc from llm",
                    "steps": [],
                })

        gen = WorkflowScriptGenerator(model_adapter=FakeModel())
        script = gen.generate("task", name="custom-name")
        assert script.name == "custom-name"


# ====================================================================
# FanOutPattern
# ====================================================================

class TestFanOutPattern:
    def test_fan_out_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            results: list[str] = []

            def worker(task: Task) -> None:
                results.append(task.payload.get("input", ""))
                task.payload["result"] = {"output": f"done-{len(results)}"}

            def synthesizer(task: Task) -> None:
                sub = task.payload.get("sub_results", [])
                task.payload["result"] = {"synthesized": True, "count": len(sub)}

            pool = _make_pool(db, {"worker": worker, "synthesizer": synthesizer})
            pattern = FanOutPattern(pool)

            result = pattern.run("analyze X", FanOutConfig(n_agents=3))
            assert result.status == "completed"
            assert result.metadata["subtasks_completed"] == 3
            assert result.output["synthesized"] is True

    def test_fan_out_no_synthesizer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def worker(task: Task) -> None:
                task.payload["result"] = {"output": "done"}

            pool = _make_pool(db, {"worker": worker})
            pattern = FanOutPattern(pool)

            result = pattern.run("test", FanOutConfig(n_agents=2))
            assert result.status == "completed"
            assert "sub_results" in result.output

    def test_fan_out_no_worker_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = FanOutPattern(pool)

            result = pattern.run("test", FanOutConfig(n_agents=2))
            assert result.status == "partial"

    def test_to_workflow_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = FanOutPattern(pool)

            script = pattern.to_workflow_script("test task", FanOutConfig(n_agents=3))
            assert script.name.startswith("fanout:")
            assert len(script.steps) == 4
            assert script.steps[0].parallel_group == "fanout"
            assert script.steps[-1].depends_on == ["fanout-0", "fanout-1", "fanout-2"]

    def test_custom_subtask_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def worker(task: Task) -> None:
                task.payload["result"] = {"ok": True}

            def synthesizer(task: Task) -> None:
                task.payload["result"] = {"ok": True}

            pool = _make_pool(db, {"worker": worker, "synthesizer": synthesizer})
            pattern = FanOutPattern(pool)

            config = FanOutConfig(
                n_agents=2,
                subtask_template="Analyze {task} aspect {index}",
            )
            result = pattern.run("test", config)
            assert result.status == "completed"

    def test_worker_handler_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing_worker(task: Task) -> None:
                raise RuntimeError("worker error")

            pool = _make_pool(db, {"worker": failing_worker})
            pattern = FanOutPattern(pool)

            result = pattern.run("test", FanOutConfig(n_agents=2))
            assert result.status == "partial"
            assert result.metadata["subtasks_failed"] == 2


class TestGenerateFilterPattern:
    def test_generate_filter_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = [
                    {"item": f"idea {i}", "score": 10 - i}
                    for i in range(5)
                ]

            def filter_handler(task: Task) -> None:
                candidates = task.payload.get("candidates", [])
                task.payload["result"] = candidates[:2]

            pool = _make_pool(db, {"generator": generator, "filter": filter_handler})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run(
                "brainstorm features",
                GenerateFilterConfig(n_generate=5, n_keep=2),
            )
            assert result.status == "completed"
            assert result.metadata["n_generate"] == 5
            assert result.metadata["n_keep"] == 2

    def test_generate_filter_no_filter_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = [
                    {"item": f"idea {i}"} for i in range(5)
                ]

            pool = _make_pool(db, {"generator": generator})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=5, n_keep=2))
            assert result.status == "completed"
            assert result.metadata["n_generate"] == 5

    def test_generate_filter_no_generator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test")
            assert result.status == "completed"

    def test_generator_returns_dict_with_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = {
                    "candidates": [{"item": "a"}, {"item": "b"}, {"item": "c"}]
                }

            def filter_handler(task: Task) -> None:
                task.payload["result"] = [{"item": "a"}]

            pool = _make_pool(db, {"generator": generator, "filter": filter_handler})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=3, n_keep=1))
            assert result.status == "completed"

    def test_generator_returns_dict_with_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = {
                    "items": [{"item": "x"}, {"item": "y"}]
                }

            pool = _make_pool(db, {"generator": generator})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=2, n_keep=1))
            assert result.status == "completed"
            assert len(result.output["candidates"]) == 2

    def test_generator_returns_other_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = {"text": "single result"}

            pool = _make_pool(db, {"generator": generator})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test")
            assert result.status == "completed"

    def test_generator_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def failing_generator(task: Task) -> None:
                raise RuntimeError("gen failed")

            pool = _make_pool(db, {"generator": failing_generator})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test")
            assert result.status == "completed"
            assert "error" in result.output["candidates"][0]

    def test_filter_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = [{"item": "a"}, {"item": "b"}]

            def failing_filter(task: Task) -> None:
                raise RuntimeError("filter failed")

            pool = _make_pool(db, {"generator": generator, "filter": failing_filter})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=2, n_keep=1))
            assert result.status == "completed"

    def test_to_workflow_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = GenerateFilterPattern(pool)

            script = pattern.to_workflow_script("ideas", GenerateFilterConfig(n_generate=5, n_keep=2))
            assert script.name.startswith("genfilter:")
            assert len(script.steps) == 2

    def test_filter_returns_dict_with_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = [{"item": f"i{i}"} for i in range(3)]

            def filter_handler(task: Task) -> None:
                task.payload["result"] = {
                    "filtered": [{"item": "i0"}, {"item": "i1"}]
                }

            pool = _make_pool(db, {"generator": generator, "filter": filter_handler})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=3, n_keep=2))
            assert result.status == "completed"
            assert len(result.output["filtered"]) == 2

    def test_filter_returns_other_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def generator(task: Task) -> None:
                task.payload["result"] = [{"item": "a"}]

            def filter_handler(task: Task) -> None:
                task.payload["result"] = {"text": "not a list"}

            pool = _make_pool(db, {"generator": generator, "filter": filter_handler})
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test", GenerateFilterConfig(n_generate=1, n_keep=1))
            assert result.status == "completed"
            assert len(result.output["filtered"]) == 0


# ====================================================================
# PatternResult
# ====================================================================

class TestPatternResult:
    def test_default_completed_at(self) -> None:
        r = PatternResult(pattern_name="test", status="completed")
        assert r.completed_at != ""

    def test_explicit_completed_at(self) -> None:
        r = PatternResult(pattern_name="test", status="completed", completed_at="2026-01-01")
        assert r.completed_at == "2026-01-01"

    def test_metadata(self) -> None:
        r = PatternResult(
            pattern_name="fan_out",
            status="completed",
            metadata={"n": 3, "ms": 100.0},
        )
        assert r.metadata["n"] == 3
        assert r.metadata["ms"] == 100.0

    def test_defaults(self) -> None:
        r = PatternResult()
        assert r.pattern_name == ""
        assert r.status == ""
        assert r.output == {}
        assert r.metadata == {}
