"""生成再过滤模式 — 先广泛生成 → 按标准筛选。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.executor.types import Task, TaskPriority
from maref.executor.worker import WorkerPool
from maref.executor.workflow.patterns.base import PatternResult
from maref.executor.workflow.types import WorkflowScript, WorkflowStep


@dataclass
class GenerateFilterConfig:
    """生成过滤配置。"""
    n_generate: int = 10  # 生成候选数
    n_keep: int = 3       # 保留数
    diversity: float = 0.7
    filter_criteria: str = "relevance, quality, feasibility"
    generate_prompt_template: str = "Generate {n} diverse ideas for: {task}"
    filter_prompt: str = "Filter the following candidates and return the top {n_keep} by {criteria}"
    timeout_seconds: float = 120.0
    max_retries: int = 1


class GenerateFilterPattern:
    """生成再过滤模式。

    1. generate: 生成 N 个候选方案
    2. filter: 按标准筛选, 保留 Top-K
    """

    def __init__(
        self,
        worker_pool: WorkerPool,
        generator_handler: str = "generator",
        filter_handler: str = "filter",
    ) -> None:
        self._pool = worker_pool
        self._generator_handler = generator_handler
        self._filter_handler = filter_handler

    def run(
        self,
        task_description: str,
        config: GenerateFilterConfig | None = None,
    ) -> PatternResult:
        config = config or GenerateFilterConfig()
        start = time.time()

        candidates = self._generate(task_description, config)
        filtered = self._filter(candidates, task_description, config) if candidates else []

        return PatternResult(
            pattern_name="generate_filter",
            status="completed",
            output={
                "candidates": candidates,
                "filtered": filtered,
                "n_generated": len(candidates),
                "n_kept": len(filtered) if isinstance(filtered, list) else 1,
            },
            metadata={
                "n_generate": config.n_generate,
                "n_keep": config.n_keep,
                "duration_ms": (time.time() - start) * 1000,
            },
        )

    def _generate(
        self, task: str, config: GenerateFilterConfig
    ) -> list[dict[str, Any]]:
        handler = self._get_handler(self._generator_handler)
        if handler is None:
            return [{"error": f"No generator handler '{self._generator_handler}'"}]

        prompt = config.generate_prompt_template.format(
            n=config.n_generate, task=task
        )
        t = Task(
            name="generate",
            priority=TaskPriority.HIGH,
            payload={
                "input": prompt,
                "n_generate": config.n_generate,
                "diversity": config.diversity,
            },
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        try:
            handler(t)
            result = t.payload.get("result", t.payload)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                candidates = result.get("candidates", result.get("items", []))
                if isinstance(candidates, list):
                    return candidates
            return [{"item": str(result)}]
        except BaseException as e:
            return [{"error": str(e)}]

    def _filter(
        self,
        candidates: list[dict[str, Any]],
        task: str,
        config: GenerateFilterConfig,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        handler = self._get_handler(self._filter_handler)
        if handler is None:
            return candidates[: config.n_keep]

        prompt = config.filter_prompt.format(
            n_keep=config.n_keep, criteria=config.filter_criteria, task=task
        )
        t = Task(
            name="filter",
            payload={
                "input": prompt,
                "candidates": candidates,
                "n_keep": config.n_keep,
                "criteria": config.filter_criteria,
            },
            timeout_seconds=config.timeout_seconds,
        )
        try:
            handler(t)
            result = t.payload.get("result", t.payload)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                filtered = result.get("filtered", result.get("candidates", result.get("items", [])))
                if isinstance(filtered, list):
                    return filtered
            return candidates[: config.n_keep]
        except BaseException:
            return candidates[: config.n_keep]

    def _get_handler(self, name: str) -> Callable | None:
        if hasattr(self._pool, "_handlers"):
            return self._pool._handlers.get(name)
        return None

    def to_workflow_script(self, task: str, config: GenerateFilterConfig | None = None) -> WorkflowScript:
        config = config or GenerateFilterConfig()
        return WorkflowScript(
            name=f"genfilter:{task[:40]}",
            steps=[
                WorkflowStep(
                    name="generate",
                    description=f"Generate {config.n_generate} candidates",
                    agent_role=self._generator_handler,
                    input_template=config.generate_prompt_template.format(
                        n=config.n_generate, task=task
                    ),
                    timeout_seconds=config.timeout_seconds,
                    max_retries=config.max_retries,
                ),
                WorkflowStep(
                    name="filter",
                    description=f"Keep top {config.n_keep} by {config.filter_criteria}",
                    agent_role=self._filter_handler,
                    input_template=config.filter_prompt.format(
                        n_keep=config.n_keep, criteria=config.filter_criteria
                    ),
                    timeout_seconds=config.timeout_seconds,
                    depends_on=["generate"],
                ),
            ],
        )
