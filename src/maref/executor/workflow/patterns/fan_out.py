"""扇出再综合模式 — 大任务拆小步 → 并行执行 → 结果综合。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maref.executor.types import Task, TaskPriority
from maref.executor.worker import WorkerPool
from maref.executor.workflow.patterns.base import PatternResult
from maref.executor.workflow.types import WorkflowScript, WorkflowStep


@dataclass
class FanOutConfig:
    """扇出配置。"""
    n_agents: int = 3
    subtask_template: str = ""  # 子任务模板, 用 {index} 占位
    synthesize_prompt: str = "Synthesize the following results into a coherent output."
    timeout_seconds: float = 120.0
    max_retries: int = 1


class FanOutPattern:
    """扇出再综合模式。

    1. decompose: 将大任务拆解为 N 个子任务
    2. fan_out: N 个 Agent 并行执行子任务
    3. synthesize: 综合所有子结果
    """

    def __init__(
        self,
        worker_pool: WorkerPool,
        worker_handler: str = "worker",
        synthesize_handler: str = "synthesizer",
    ) -> None:
        self._pool = worker_pool
        self._worker_handler = worker_handler
        self._synthesize_handler = synthesize_handler
        self._lock = threading.Lock()

    def run(
        self,
        task_description: str,
        config: FanOutConfig | None = None,
    ) -> PatternResult:
        config = config or FanOutConfig()
        start = time.time()

        # Phase 1: 扇出 — 创建 N 个子任务
        subtasks = self._decompose(task_description, config)
        # Phase 2: 并行执行
        results = self._fan_out(subtasks, config)
        # Phase 3: 综合
        final = self._synthesize(results, config)

        return PatternResult(
            pattern_name="fan_out",
            status="completed" if not any(
                r.get("error") for r in results
            ) else "partial",
            output=final,
            metadata={
                "n_agents": config.n_agents,
                "subtasks_completed": sum(
                    1 for r in results if not r.get("error")
                ),
                "subtasks_failed": sum(
                    1 for r in results if r.get("error")
                ),
                "duration_ms": (time.time() - start) * 1000,
            },
        )

    def _decompose(
        self, task: str, config: FanOutConfig
    ) -> list[str]:
        """将任务拆解为 N 个子任务描述。"""
        if config.subtask_template:
            return [
                config.subtask_template.format(index=i, total=config.n_agents, task=task)
                for i in range(config.n_agents)
            ]
        return [
            f"{task} — Part {i + 1}/{config.n_agents}"
            for i in range(config.n_agents)
        ]

    def _fan_out(
        self, subtasks: list[str], config: FanOutConfig
    ) -> list[dict[str, Any]]:
        """并行执行所有子任务。"""
        results: list[dict[str, Any] | None] = [None] * len(subtasks)
        threads: list[threading.Thread] = []

        def execute(i: int, subtask: str) -> None:
            try:
                task = Task(
                    name=f"fanout-{i}",
                    priority=TaskPriority.HIGH,
                    payload={"input": subtask, "index": i},
                    timeout_seconds=config.timeout_seconds,
                    max_retries=config.max_retries,
                )
                handler = self._get_handler(self._worker_handler)
                if handler is None:
                    results[i] = {"error": f"No handler '{self._worker_handler}'", "index": i}
                    return
                handler(task)
                results[i] = task.payload.get("result", task.payload)
            except BaseException as e:
                results[i] = {"error": str(e), "index": i}

        for i, subtask in enumerate(subtasks):
            t = threading.Thread(target=execute, args=(i, subtask), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return [r for r in results if r is not None]

    def _synthesize(
        self, results: list[dict[str, Any]], config: FanOutConfig
    ) -> dict[str, Any]:
        """综合所有子结果。"""
        handler = self._get_handler(self._synthesize_handler)
        if handler is None:
            return {"synthesized": False, "sub_results": results, "note": f"No synthesizer handler '{self._synthesize_handler}'"}

        task = Task(
            name="synthesize",
            payload={
                "input": config.synthesize_prompt,
                "sub_results": results,
            },
            timeout_seconds=config.timeout_seconds,
        )
        try:
            handler(task)
            synthesized = task.payload.get("result", task.payload)
            if isinstance(synthesized, dict):
                return synthesized
            return {"synthesized": True, "output": str(synthesized), "sub_results": results}
        except BaseException as e:
            return {"synthesized": False, "error": str(e), "sub_results": results}

    def _get_handler(self, name: str) -> Callable | None:
        if hasattr(self._pool, "_handlers"):
            return self._pool._handlers.get(name)
        return None

    def to_workflow_script(self, task: str, config: FanOutConfig | None = None) -> WorkflowScript:
        """将扇出模式导出为 WorkflowScript。"""
        config = config or FanOutConfig()
        subtasks = self._decompose(task, config)
        steps = [
            WorkflowStep(
                name=f"fanout-{i}",
                description=f"Subtask {i + 1}",
                agent_role=self._worker_handler,
                input_template=subtasks[i],
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                parallel_group="fanout",
            )
            for i in range(len(subtasks))
        ]
        steps.append(
            WorkflowStep(
                name="synthesize",
                description="Synthesize all results",
                agent_role=self._synthesize_handler,
                input_template=config.synthesize_prompt,
                timeout_seconds=config.timeout_seconds,
                depends_on=[s.name for s in steps],
            )
        )
        return WorkflowScript(
            name=f"fanout:{task[:40]}",
            steps=steps,
            max_concurrency=config.n_agents,
        )
