"""锦标赛模式 — 多策略并行 → 择优输出。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.executor.types import Task, TaskPriority
from maref.executor.worker import WorkerPool
from maref.executor.workflow.patterns.base import PatternResult
from maref.executor.workflow.types import WorkflowScript, WorkflowStep


@dataclass
class TournamentConfig:
    """锦标赛配置。"""
    n_contestants: int = 3
    strategies: list[str] = field(default_factory=list)
    judge_prompt: str = "Evaluate the following results and select the best one."
    judge_criteria: str = "accuracy, completeness, clarity"
    timeout_seconds: float = 120.0
    max_retries: int = 1


class TournamentPattern:
    """锦标赛模式。

    1. spawn: N 个 Agent 用不同策略/视角执行同一任务
    2. judge: 裁判 Agent 评估所有结果, 选出最优
    """

    def __init__(
        self,
        worker_pool: WorkerPool,
        contestant_handler: str = "contestant",
        judge_handler: str = "judge",
    ) -> None:
        self._pool = worker_pool
        self._contestant_handler = contestant_handler
        self._judge_handler = judge_handler

    def run(
        self,
        task_description: str,
        config: TournamentConfig | None = None,
    ) -> PatternResult:
        config = config or TournamentConfig()
        start = time.time()

        strategies = config.strategies or [
            f"{task_description} (strategy {i + 1})"
            for i in range(config.n_contestants)
        ]

        # Phase 1: 多策略并行
        results = self._run_contestants(task_description, strategies, config)
        # Phase 2: 裁判评估
        winner = self._judge(task_description, results, config)

        return PatternResult(
            pattern_name="tournament",
            status="completed" if winner.get("winner") is not None else "failed",
            output=winner,
            metadata={
                "n_contestants": len(strategies),
                "winner_index": winner.get("winner_index"),
                "winner_strategy": winner.get("winner_strategy"),
                "duration_ms": (time.time() - start) * 1000,
            },
        )

    def _run_contestants(
        self,
        task: str,
        strategies: list[str],
        config: TournamentConfig,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any] | None] = [None] * len(strategies)
        threads: list[threading.Thread] = []

        def execute(i: int, strategy: str) -> None:
            try:
                t = Task(
                    name=f"contestant-{i}",
                    priority=TaskPriority.HIGH,
                    payload={
                        "task": task,
                        "strategy": strategy,
                        "index": i,
                    },
                    timeout_seconds=config.timeout_seconds,
                    max_retries=config.max_retries,
                )
                handler = self._get_handler(self._contestant_handler)
                if handler is None:
                    results[i] = {"error": f"No handler '{self._contestant_handler}'", "index": i}
                    return
                handler(t)
                results[i] = t.payload.get("result", t.payload)
            except BaseException as e:
                results[i] = {"error": str(e), "index": i}

        for i, strategy in enumerate(strategies):
            t = threading.Thread(target=execute, args=(i, strategy), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return [r for r in results if r is not None]

    def _judge(
        self,
        task: str,
        results: list[dict[str, Any]],
        config: TournamentConfig,
    ) -> dict[str, Any]:
        handler = self._get_handler(self._judge_handler)
        if handler is None:
            return {"winner": None, "winner_index": None, "error": f"No judge handler '{self._judge_handler}'"}

        t = Task(
            name="judge",
            payload={
                "task": task,
                "contestants": results,
                "criteria": config.judge_criteria,
                "judge_prompt": config.judge_prompt,
            },
            timeout_seconds=config.timeout_seconds,
        )
        try:
            handler(t)
            verdict = t.payload.get("result", t.payload)
            if isinstance(verdict, dict):
                return verdict
            return {"winner": str(verdict), "winner_index": 0, "winner_strategy": "unknown", "all_results": results}
        except BaseException as e:
            return {"winner": None, "winner_index": None, "error": str(e), "all_results": results}

    def _get_handler(self, name: str) -> Callable | None:
        if hasattr(self._pool, "_handlers"):
            return self._pool._handlers.get(name)
        return None

    def to_workflow_script(self, task: str, config: TournamentConfig | None = None) -> WorkflowScript:
        config = config or TournamentConfig()
        strategies = config.strategies or [
            f"strategy-{i}" for i in range(config.n_contestants)
        ]
        steps = [
            WorkflowStep(
                name=f"contestant-{i}",
                description=f"Contestant {i}: {s}",
                agent_role=self._contestant_handler,
                input_template=f"Task: {task}\nApproach: {s}",
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                parallel_group="contestants",
            )
            for i, s in enumerate(strategies)
        ]
        steps.append(
            WorkflowStep(
                name="judge",
                description="Judge and select best result",
                agent_role=self._judge_handler,
                input_template=config.judge_prompt,
                timeout_seconds=config.timeout_seconds,
                depends_on=[s.name for s in steps],
            )
        )
        return WorkflowScript(
            name=f"tournament:{task[:40]}",
            steps=steps,
            max_concurrency=config.n_contestants,
        )
