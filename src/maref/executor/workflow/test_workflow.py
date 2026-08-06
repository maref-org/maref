"""WorkflowScript Engine 测试。"""

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
    WorkflowEngine,
    WorkflowError,
    _topological_groups,
    _topological_sort,
)
from maref.executor.workflow.generator import WorkflowScriptGenerator, _parse_json
from maref.executor.workflow.types import (
    StepResult,
    StepStatus,
    WorkflowCheckpoint,
    WorkflowResult,
    WorkflowScript,
    WorkflowStatus,
    WorkflowStep,
)

# ── Fake GovernanceBridge ────────────────────────────────────────────

class FakeGovernance:
    def __init__(self, allow: bool = True):
        self.allow = allow
        self.records: list[tuple[str, bool]] = []
        self.state_name = "TEST"

    def check(self, stage: str) -> bool:
        return self.allow

    def record(self, stage: str, allowed: bool) -> None:
        self.records.append((stage, allowed))


# ── Helper: 创建 WorkerPool ─────────────────────────────────────────

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
    def test_to_dict_roundtrip(self):
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

    def test_defaults(self):
        step = WorkflowStep(name="test")
        assert step.description == ""
        assert step.agent_role == ""
        assert step.depends_on == []
        assert step.max_retries == 0


class TestWorkflowScript:
    def test_step_names(self):
        script = WorkflowScript(
            name="test",
            steps=[
                WorkflowStep(name="a"),
                WorkflowStep(name="b"),
            ],
        )
        assert script.step_names() == ["a", "b"]

    def test_get_step(self):
        script = WorkflowScript(
            steps=[
                WorkflowStep(name="find", description="寻找"),
                WorkflowStep(name="write", description="撰写"),
            ],
        )
        assert script.get_step("find") is not None
        assert script.get_step("find").description == "寻找"  # type: ignore[union-attr]
        assert script.get_step("nonexistent") is None

    def test_parallel_groups(self):
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

    def test_to_dict_roundtrip(self):
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

    def test_new_id_is_unique(self):
        s1 = WorkflowScript()
        s2 = WorkflowScript()
        assert s1.id != s2.id


class TestWorkflowResult:
    def test_summary(self):
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

    def test_failed_steps(self):
        result = WorkflowResult(script_id="s1")
        result.step_results = [
            StepResult(step_name="a", status=StepStatus.COMPLETED),
            StepResult(step_name="b", status=StepStatus.FAILED),
        ]
        assert len(result.failed_steps()) == 1
        assert result.failed_steps()[0].step_name == "b"

    def test_get_step_result(self):
        result = WorkflowResult(script_id="s1")
        result.step_results = [
            StepResult(step_name="step_x", status=StepStatus.COMPLETED),
        ]
        assert result.get_step_result("step_x").status == StepStatus.COMPLETED  # type: ignore[union-attr]
        assert result.get_step_result("nonexistent") is None


class TestWorkflowCheckpoint:
    def test_to_dict(self):
        cp = WorkflowCheckpoint(
            script=WorkflowScript(name="s1", steps=[WorkflowStep(name="a")]),
            last_completed_step=0,
            step_results=[StepResult(step_name="a", status=StepStatus.COMPLETED)],
        )
        d = cp.to_dict()
        assert d["last_completed_step"] == 0
        assert d["step_results"][0]["step_name"] == "a"
        assert d["script"]["name"] == "s1"

    def test_from_to_dict_consistency(self):
        cp = WorkflowCheckpoint(id="cp1")
        d = cp.to_dict()
        assert d["id"] == "cp1"


# ====================================================================
# engine.py
# ====================================================================

class TestTopologicalSort:
    def test_no_deps(self):
        steps = [WorkflowStep(name="a"), WorkflowStep(name="b")]
        sorted_steps = _topological_sort(steps)
        assert [s.name for s in sorted_steps] == ["a", "b"]

    def test_with_deps(self):
        steps = [
            WorkflowStep(name="a"),
            WorkflowStep(name="c", depends_on=["b"]),
            WorkflowStep(name="b", depends_on=["a"]),
        ]
        sorted_steps = _topological_sort(steps)
        names = [s.name for s in sorted_steps]
        assert names.index("a") < names.index("b")
        assert names.index("b") < names.index("c")

    def test_unknown_dep_raises(self):
        steps = [WorkflowStep(name="a", depends_on=["nonexistent"])]
        with pytest.raises(WorkflowError, match="unknown step"):
            _topological_sort(steps)

    def test_circular_dep_raises(self):
        steps = [
            WorkflowStep(name="a", depends_on=["b"]),
            WorkflowStep(name="b", depends_on=["a"]),
        ]
        with pytest.raises(CircularDependencyError):
            _topological_sort(steps)


class TestTopologicalGroups:
    def test_simple_layering(self):
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


class TestWorkflowEngine:
    def test_sequential_execution(self):
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

    def test_step_failure(self):
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

    def test_handler_not_found(self):
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

    def test_governance_block(self):
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

    def test_retry_then_succeed(self):
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
                    WorkflowStep(
                        name="s1",
                        agent_role="flaky",
                        max_retries=2,
                    )
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED
            assert attempt_count[0] == 2

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def slow_handler(task: Task) -> None:
                time.sleep(5)

            pool = _make_pool(db, {"slow": slow_handler})
            engine = WorkflowEngine(pool)

            script = WorkflowScript(
                name="timeout-test",
                steps=[
                    WorkflowStep(
                        name="s1",
                        agent_role="slow",
                        timeout_seconds=0.1,
                    )
                ],
            )

            result = engine.execute(script)
            assert result.status == WorkflowStatus.FAILED

    def test_parallel_execution(self):
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

    def test_fallback_step(self):
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
            # fallback step name should be in results
            fallback_sr = result.get_step_result("s1→fallback:s1_fallback")
            assert fallback_sr is not None
            assert fallback_sr.status == StepStatus.COMPLETED

    def test_missing_fallback(self):
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

    def test_final_output_from_last_step(self):
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

    def test_checkpoint_create_and_resume(self):
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

            # 验证检查点文件已创建
            checkpoints = engine.list_checkpoints()
            assert len(checkpoints) > 0

            # 验证恢复
            resume_result = engine.resume(checkpoints[-1])
            assert resume_result.status == WorkflowStatus.COMPLETED

    def test_empty_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            engine = WorkflowEngine(pool)

            script = WorkflowScript(name="empty")
            result = engine.execute(script)
            assert result.status == WorkflowStatus.COMPLETED

    def test_register_handlers_from_pool(self):
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


# ====================================================================
# generator.py
# ====================================================================

class TestParseJson:
    def test_direct_json(self):
        result = _parse_json('{"name": "test"}')
        assert result == {"name": "test"}

    def test_code_fence(self):
        result = _parse_json('```json\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_plain_code_fence(self):
        result = _parse_json('```\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_embedded_json(self):
        result = _parse_json("Some text\n{\"name\": \"test\"}\nmore text")
        assert result == {"name": "test"}

    def test_invalid_input(self):
        result = _parse_json("not json at all")
        assert result is None


class TestWorkflowScriptGenerator:
    def test_from_dict(self):
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

    def test_from_step_list(self):
        steps: list[dict[str, Any]] = [
            {"name": "a", "agent_role": "analyzer"},
            {"name": "b", "agent_role": "writer", "depends_on": ["a"]},
        ]
        script = WorkflowScriptGenerator.from_step_list(steps, name="manual")
        assert script.name == "manual"
        assert len(script.steps) == 2

    def test_generate_requires_model(self):
        gen = WorkflowScriptGenerator()
        with pytest.raises(RuntimeError, match="No model_adapter"):
            gen.generate("do something")

    def test_generate_with_fake_model(self):
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


# ====================================================================
# Integration: engine + generator
# ====================================================================

class TestWorkflowIntegration:
    def test_generated_script_executes(self):
        script = WorkflowScriptGenerator.from_dict({
            "name": "integrated",
            "steps": [
                {
                    "name": "step1",
                    "agent_role": "worker",
                    "input_template": "do work",
                    "timeout_seconds": 30,
                    "max_retries": 0,
                    "depends_on": [],
                    "fallback_step": "",
                    "parallel_group": "",
                    "validator_prompt": "",
                }
            ],
        })

        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            results: list[str] = []

            def handler(task: Task) -> None:
                results.append("executed")
                task.payload["result"] = {"done": True}

            pool = _make_pool(db, {"worker": handler})
            engine = WorkflowEngine(pool)
            result = engine.execute(script)

            assert result.status == WorkflowStatus.COMPLETED
            assert results == ["executed"]
