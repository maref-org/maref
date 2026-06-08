"""编排模式库测试。"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from maref.executor.queue import TaskQueue
from maref.executor.types import Task
from maref.executor.worker import WorkerPool
from maref.executor.workflow.patterns.base import PatternResult
from maref.executor.workflow.patterns.fan_out import FanOutConfig, FanOutPattern
from maref.executor.workflow.patterns.generate_filter import (
    GenerateFilterConfig,
    GenerateFilterPattern,
)
from maref.executor.workflow.patterns.tournament import (
    TournamentConfig,
    TournamentPattern,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _make_pool(
    db_path: str,
    handlers: dict[str, callable] | None = None,
) -> WorkerPool:
    queue = TaskQueue(db_path)
    pool = WorkerPool(queue, num_workers=2)
    if handlers:
        for name, handler in handlers.items():
            pool.register_handler(name, handler)
    return pool


# ====================================================================
# FanOutPattern
# ====================================================================

class TestFanOutPattern:
    def test_fan_out_basic(self):
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

    def test_fan_out_no_synthesizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def worker(task: Task) -> None:
                task.payload["result"] = {"output": "done"}

            pool = _make_pool(db, {"worker": worker})
            pattern = FanOutPattern(pool)

            result = pattern.run("test", FanOutConfig(n_agents=2))
            assert result.status == "completed"
            assert "sub_results" in result.output

    def test_fan_out_no_worker_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = FanOutPattern(pool)

            result = pattern.run("test", FanOutConfig(n_agents=2))
            assert result.status == "partial"

    def test_to_workflow_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = FanOutPattern(pool)

            script = pattern.to_workflow_script("test task", FanOutConfig(n_agents=3))
            assert script.name.startswith("fanout:")
            assert len(script.steps) == 4  # 3 fanout + 1 synthesize
            assert script.steps[0].parallel_group == "fanout"
            assert script.steps[-1].depends_on == ["fanout-0", "fanout-1", "fanout-2"]

    def test_custom_subtask_template(self):
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


# ====================================================================
# TournamentPattern
# ====================================================================

class TestTournamentPattern:
    def test_tournament_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            contestant_calls: list[int] = []

            def contestant(task: Task) -> None:
                idx = task.payload.get("index", 0)
                contestant_calls.append(idx)
                task.payload["result"] = {"output": f"result-{idx}", "index": idx}

            def judge(task: Task) -> None:
                contestants = task.payload.get("contestants", [])
                best = max(
                    enumerate(contestants),
                    key=lambda x: x[1].get("index", 0) if isinstance(x[1], dict) else 0,
                )
                task.payload["result"] = {
                    "winner": best[1],
                    "winner_index": best[0],
                    "winner_strategy": f"strategy-{best[0]}",
                }

            pool = _make_pool(db, {"contestant": contestant, "judge": judge})
            pattern = TournamentPattern(pool)

            result = pattern.run(
                "sort numbers",
                TournamentConfig(
                    n_contestants=3,
                    strategies=["asc", "desc", "random"],
                ),
            )
            assert result.status == "completed"
            assert result.output.get("winner_index") is not None
            assert len(contestant_calls) == 3

    def test_tournament_no_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def contestant(task: Task) -> None:
                task.payload["result"] = {"output": "ok"}

            pool = _make_pool(db, {"contestant": contestant})
            pattern = TournamentPattern(pool)

            result = pattern.run("test", TournamentConfig(n_contestants=2))
            assert result.status == "failed"

    def test_tournament_with_auto_strategies(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")

            def contestant(task: Task) -> None:
                task.payload["result"] = {"ok": True}

            def judge(task: Task) -> None:
                task.payload["result"] = {"winner": "first", "winner_index": 0}

            pool = _make_pool(db, {"contestant": contestant, "judge": judge})
            pattern = TournamentPattern(pool)

            result = pattern.run("test", TournamentConfig(n_contestants=2))
            assert result.status == "completed"

    def test_to_workflow_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = TournamentPattern(pool)

            script = pattern.to_workflow_script("solve X", TournamentConfig(n_contestants=2))
            assert script.name.startswith("tournament:")
            assert len(script.steps) == 3  # 2 contestants + 1 judge
            assert script.steps[0].parallel_group == "contestants"


# ====================================================================
# GenerateFilterPattern
# ====================================================================

class TestGenerateFilterPattern:
    def test_generate_filter_basic(self):
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

    def test_generate_filter_no_filter_handler(self):
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

    def test_generate_filter_no_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = GenerateFilterPattern(pool)

            result = pattern.run("test")
            assert result.status == "completed"

    def test_generator_returns_dict_with_candidates(self):
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

    def test_to_workflow_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            pool = _make_pool(db)
            pattern = GenerateFilterPattern(pool)

            script = pattern.to_workflow_script("ideas", GenerateFilterConfig(n_generate=5, n_keep=2))
            assert script.name.startswith("genfilter:")
            assert len(script.steps) == 2


# ====================================================================
# PatternResult
# ====================================================================

class TestPatternResult:
    def test_default_completed_at(self):
        r = PatternResult(pattern_name="test", status="completed")
        assert r.completed_at != ""

    def test_explicit_completed_at(self):
        r = PatternResult(pattern_name="test", status="completed", completed_at="2026-01-01")
        assert r.completed_at == "2026-01-01"

    def test_metadata(self):
        r = PatternResult(
            pattern_name="fan_out",
            status="completed",
            metadata={"n": 3, "ms": 100.0},
        )
        assert r.metadata["n"] == 3
        assert r.metadata["ms"] == 100.0
