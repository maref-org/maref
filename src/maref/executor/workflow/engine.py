from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from maref.executor.types import Task, TaskPriority
from maref.executor.worker import WorkerPool
from maref.executor.workflow.types import (
    StepResult,
    StepStatus,
    WorkflowCheckpoint,
    WorkflowResult,
    WorkflowScript,
    WorkflowStatus,
    _now,
)

# 可选的 governance bridge 类型（避免硬依赖）
GovernanceBridgeLike = Any  # 只要实现了 .check(stage) -> bool 即可

HandlerType = Callable[[Task], None]


class WorkflowError(RuntimeError):
    pass


class CircularDependencyError(WorkflowError):
    pass


class GovernanceBlockedError(WorkflowError):
    pass


def _topological_sort(steps: list, depends_on_attr: str = "depends_on") -> list:
    """拓扑排序 — 按依赖关系确定执行顺序。

    如果 A depends_on B, 则 B 在 A 之前执行。
    无依赖的步骤保持原始顺序。
    """
    [s.name for s in steps]
    step_map = {s.name: s for s in steps}

    in_degree: dict[str, int] = {s.name: 0 for s in steps}
    adj: dict[str, list[str]] = {s.name: [] for s in steps}

    for s in steps:
        for dep in getattr(s, depends_on_attr, []):
            if dep not in step_map:
                raise WorkflowError(
                    f"Step '{s.name}' depends on unknown step '{dep}'"
                )
            adj[dep].append(s.name)
            in_degree[s.name] = in_degree.get(s.name, 0) + 1

    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_names: list[str] = []

    while queue:
        name = queue.pop(0)
        sorted_names.append(name)
        for neighbor in adj[name]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_names) != len(steps):
        raise CircularDependencyError(
            f"Circular dependency detected: {len(steps)} steps, "
            f"{len(sorted_names)} sortable"
        )

    result = [step_map[n] for n in sorted_names]
    return result


def _topological_groups(steps: list) -> list[list]:
    """将拓扑排序结果分组为并行执行层。

    如果 A 和 B 没有依赖关系且不在同一 parallel_group，
    它们仍在不同步骤执行（通过并行组实现真实并行）。
    同一层内且同一 parallel_group 的步骤可以并行。
    """
    sorted_steps = _topological_sort(steps)

    # 构建依赖索引
    {s.name: s for s in sorted_steps}
    {s.name: i for i, s in enumerate(sorted_steps)}

    # 每步的最早执行层
    layer: dict[str, int] = {}
    for s in sorted_steps:
        deps = getattr(s, "depends_on", [])
        if not deps:
            layer[s.name] = 0
        else:
            layer[s.name] = max(layer.get(d, 0) for d in deps) + 1

    # 按层分组
    max_layer = max(layer.values()) if layer else 0
    groups: list[list] = [[] for _ in range(max_layer + 1)]
    for s in sorted_steps:
        groups[layer[s.name]].append(s)

    return groups


class WorkflowEngine:
    """编排脚本引擎。

    接收 WorkflowScript → 按依赖关系解析执行顺序 → 按步骤执行 →
    支持并行组 / 重试 / 回退 / 治理检查 / 检查点。

    与 WorkerPool 共享 handler 注册表, 但直接调用 handler 而非经由队列。
    """

    def __init__(
        self,
        worker_pool: WorkerPool,
        governance_bridge: GovernanceBridgeLike | None = None,
        checkpoint_dir: str = "",
    ) -> None:
        self._worker_pool = worker_pool
        self._governance = governance_bridge
        self._checkpoint_dir = checkpoint_dir
        self._handlers: dict[str, HandlerType] = {}
        self._lock = threading.Lock()
        # 自动从 WorkerPool 导入已注册的 handler
        self.register_handlers_from_pool()

    # ── Handler 注册 ─────────────────────────────────────────────────

    def register_handler(self, name: str, handler: HandlerType) -> None:
        self._handlers[name] = handler

    def register_handlers_from_pool(self) -> None:
        """从 WorkerPool 导入已注册的 handler。"""
        if hasattr(self._worker_pool, "_handlers"):
            self._handlers.update(self._worker_pool._handlers)

    # ── 核心执行 ─────────────────────────────────────────────────────

    def execute(
        self,
        script: WorkflowScript,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """执行编排脚本。"""
        inputs = inputs or {}
        result = WorkflowResult(
            script_id=script.id,
            started_at=_now(),
        )

        try:
            groups = _topological_groups(script.steps)
        except WorkflowError as e:
            result.status = WorkflowStatus.FAILED
            result.error_message = str(e)
            result.completed_at = _now()
            return result

        step_index = 0
        checkpoint_count = 0

        for group in groups:
            # 检查组内是否有并行步骤
            has_parallel = any(
                s.parallel_group for s in group
            )

            if has_parallel:
                grouped: dict[str, list] = {}
                for s in group:
                    pg = s.parallel_group or f"__seq_{s.name}"
                    grouped.setdefault(pg, []).append(s)

                for pg_name, pg_steps in grouped.items():
                    if pg_name.startswith("__seq_") or len(pg_steps) == 1:
                        sr = self._execute_step(
                            pg_steps[0], script, inputs, result
                        )
                        result.step_results.append(sr)
                        step_index += 1
                        if sr.status == StepStatus.FAILED:
                            result.status = WorkflowStatus.FAILED
                            result.error_message = (
                                f"Step '{pg_steps[0].name}' failed: "
                                f"{sr.error_message}"
                            )
                            result.completed_at = _now()
                            return result
                    else:
                        srs = self._execute_parallel(pg_steps, script, inputs, result)
                        result.step_results.extend(srs)
                        step_index += len(srs)
                        failed = [sr for sr in srs if sr.status == StepStatus.FAILED]
                        if failed:
                            result.status = WorkflowStatus.FAILED
                            result.error_message = (
                                f"Parallel group '{pg_name}' failed: "
                                f"{failed[0].error_message}"
                            )
                            result.completed_at = _now()
                            return result
            else:
                for step in group:
                    sr = self._execute_step(step, script, inputs, result)
                    result.step_results.append(sr)
                    step_index += 1
                    if sr.status == StepStatus.FAILED:
                        result.status = WorkflowStatus.FAILED
                        result.error_message = (
                            f"Step '{step.name}' failed: {sr.error_message}"
                        )
                        result.completed_at = _now()
                        return result

            # 检查点
            if (
                self._checkpoint_dir
                and script.checkpoint_interval > 0
                and step_index % script.checkpoint_interval == 0
                and step_index > 0
            ):
                self._save_checkpoint(
                    script, step_index - 1, result.step_results
                )
                checkpoint_count += 1

        result.status = WorkflowStatus.COMPLETED
        result.completed_at = _now()

        # 聚合最终输出：取最后一步的输出
        if result.step_results:
            last = result.step_results[-1]
            if last.status == StepStatus.COMPLETED:
                result.final_output = last.output

        total_ms = 0.0
        for sr in result.step_results:
            total_ms += sr.duration_ms
        result.total_duration_ms = total_ms

        result.metadata["checkpoints_created"] = checkpoint_count
        result.metadata["groups_executed"] = len(groups)

        return result

    def resume(
        self,
        checkpoint_id: str,
    ) -> WorkflowResult:
        """从检查点恢复执行。"""
        cp = self._load_checkpoint(checkpoint_id)
        if cp is None:
            raise WorkflowError(f"Checkpoint '{checkpoint_id}' not found")

        result = WorkflowResult(
            script_id=cp.script.id,
            started_at=_now(),
            step_results=list(cp.step_results),
        )

        next_index = cp.last_completed_step + 1
        remaining = cp.script.steps[next_index:]

        if not remaining:
            result.status = WorkflowStatus.COMPLETED
            result.completed_at = _now()
            if result.step_results:
                last = result.step_results[-1]
                if last.status == StepStatus.COMPLETED:
                    result.final_output = last.output
            return result

        # 剥离对已完成步骤的依赖引用
        completed_names = {s.step_name for s in cp.step_results}
        for step in remaining:
            step.depends_on = [d for d in step.depends_on if d not in completed_names]

        groups = _topological_groups(remaining)
        step_index = next_index

        for group in groups:
            has_parallel = any(s.parallel_group for s in group)
            if has_parallel:
                grouped: dict[str, list] = {}
                for s in group:
                    pg = s.parallel_group or f"__seq_{s.name}"
                    grouped.setdefault(pg, []).append(s)
                for pg_steps in grouped.values():
                    if len(pg_steps) == 1:
                        sr = self._execute_step(
                            pg_steps[0], cp.script, {}, result
                        )
                        result.step_results.append(sr)
                        step_index += 1
                        if sr.status == StepStatus.FAILED:
                            result.status = WorkflowStatus.FAILED
                            result.error_message = (
                                f"Step '{pg_steps[0].name}' failed (resume): "
                                f"{sr.error_message}"
                            )
                            result.completed_at = _now()
                            return result
                    else:
                        srs = self._execute_parallel(
                            pg_steps, cp.script, {}, result
                        )
                        result.step_results.extend(srs)
                        step_index += len(srs)
            else:
                for step in group:
                    sr = self._execute_step(step, cp.script, {}, result)
                    result.step_results.append(sr)
                    step_index += 1
                    if sr.status == StepStatus.FAILED:
                        result.status = WorkflowStatus.FAILED
                        result.error_message = (
                            f"Step '{step.name}' failed (resume): "
                            f"{sr.error_message}"
                        )
                        result.completed_at = _now()
                        return result

        result.status = WorkflowStatus.COMPLETED
        result.completed_at = _now()
        if result.step_results:
            last = result.step_results[-1]
            if last.status == StepStatus.COMPLETED:
                result.final_output = last.output

        total_ms = 0.0
        for sr in result.step_results:
            total_ms += sr.duration_ms
        result.total_duration_ms = total_ms

        return result

    # ── 内部执行方法 ──────────────────────────────────────────────────

    def _execute_step(
        self,
        step,
        script: WorkflowScript,
        inputs: dict[str, Any],
        result: WorkflowResult,
    ) -> StepResult:
        sr = StepResult(step_name=step.name)
        handler = self._handlers.get(step.agent_role)

        # 治理检查
        if self._governance is not None:
            allowed = self._governance.check("step")
            self._governance.record("step", allowed)
            if not allowed:
                sr.status = StepStatus.FAILED
                sr.error_message = (
                    f"Governance blocked step '{step.name}': "
                    f"governance state={getattr(self._governance, 'state_name', 'unknown')}"
                )
                sr.completed_at = _now()
                return sr

        if handler is None:
            sr.status = StepStatus.FAILED
            sr.error_message = (
                f"No handler registered for agent_role='{step.agent_role}' "
                f"in step '{step.name}'"
            )
            sr.completed_at = _now()
            return sr

        # 构建 Task
        rendered_input = step.input_template
        if inputs:
            try:
                rendered_input = step.input_template.format(**inputs)
            except KeyError:
                pass

        task = Task(
            name=step.name,
            description=step.description,
            priority=TaskPriority.HIGH,
            payload={
                "step_name": step.name,
                "agent_role": step.agent_role,
                "input": rendered_input,
                "validator_prompt": step.validator_prompt,
            },
            timeout_seconds=step.timeout_seconds,
            max_retries=step.max_retries,
        )

        # 带重试的执行
        sr.started_at = _now()
        start = time.time()
        last_error = ""

        for attempt in range(step.max_retries + 1):
            if attempt > 0:
                task.retry_count = attempt

            try:
                if step.timeout_seconds and step.timeout_seconds > 0:
                    self._execute_with_timeout(handler, task, step.timeout_seconds)
                else:
                    handler(task)

                sr.status = StepStatus.COMPLETED
                sr.output = task.payload.get("result", task.payload)
                sr.duration_ms = (time.time() - start) * 1000
                sr.completed_at = _now()

                # 验证
                if step.validator_prompt:
                    self._validate_step(sr, step, task)

                return sr

            except BaseException as e:
                last_error = str(e)
                if attempt < step.max_retries:
                    continue
                # 重试耗尽 → 尝试回退
                if step.fallback_step:
                    return self._execute_fallback(
                        step, script, inputs, result, last_error
                    )

        sr.status = StepStatus.FAILED
        sr.error_message = last_error
        sr.duration_ms = (time.time() - start) * 1000
        sr.completed_at = _now()
        return sr

    def _execute_with_timeout(
        self,
        handler: HandlerType,
        task: Task,
        timeout: float,
    ) -> None:
        exc: list[BaseException | None] = [None]
        done = threading.Event()

        def runner() -> None:
            try:
                handler(task)
            except BaseException as e:
                exc[0] = e
            finally:
                done.set()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        finished = done.wait(timeout=timeout)
        if not finished:
            raise TimeoutError(
                f"Step '{task.name}' timed out after {timeout}s"
            )
        if exc[0] is not None:
            raise exc[0]  # type: ignore

    def _execute_fallback(
        self,
        failed_step,
        script: WorkflowScript,
        inputs: dict[str, Any],
        result: WorkflowResult,
        error: str,
    ) -> StepResult:
        fallback_step = script.get_step(failed_step.fallback_step)
        if fallback_step is None:
            sr = StepResult(step_name=failed_step.name)
            sr.status = StepStatus.FAILED
            sr.error_message = (
                f"Step failed and fallback '{failed_step.fallback_step}' not found: {error}"
            )
            sr.completed_at = _now()
            return sr

        sr = StepResult(step_name=f"{failed_step.name}→fallback:{fallback_step.name}")
        handler = self._handlers.get(fallback_step.agent_role)
        if handler is None:
            sr.status = StepStatus.FAILED
            sr.error_message = (
                f"Fallback step '{fallback_step.name}' has no handler"
            )
            sr.completed_at = _now()
            return sr

        task = Task(
            name=fallback_step.name,
            payload={"input": fallback_step.input_template, "original_error": error},
            timeout_seconds=fallback_step.timeout_seconds,
        )
        sr.started_at = _now()
        start = time.time()
        try:
            handler(task)
            sr.status = StepStatus.COMPLETED
            sr.output = task.payload.get("result", task.payload)
            sr.duration_ms = (time.time() - start) * 1000
            sr.completed_at = _now()
        except BaseException as e:
            sr.status = StepStatus.FAILED
            sr.error_message = f"Fallback also failed: {e}"
            sr.duration_ms = (time.time() - start) * 1000
            sr.completed_at = _now()
        return sr

    def _execute_parallel(
        self,
        steps: list,
        script: WorkflowScript,
        inputs: dict[str, Any],
        result: WorkflowResult,
    ) -> list[StepResult]:
        """并行执行一组步骤。"""
        step_results: list[StepResult] = [None] * len(steps)  # type: ignore
        threads: list[threading.Thread] = []
        lock = threading.Lock()

        def run_step(i: int, step) -> None:
            sr = self._execute_step(step, script, inputs, result)
            with lock:
                step_results[i] = sr

        for i, step in enumerate(steps):
            t = threading.Thread(target=run_step, args=(i, step), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return step_results  # type: ignore

    def _validate_step(
        self, sr: StepResult, step, task: Task
    ) -> None:
        """步骤验证：调用验证 handler 检查步骤输出。"""
        validator_handler = self._handlers.get(f"{step.agent_role}.validator")
        if validator_handler is None:
            return

        try:
            validator_task = Task(
                name=f"validate:{step.name}",
                payload={
                    "step_output": sr.output,
                    "validator_prompt": step.validator_prompt,
                },
            )
            validator_handler(validator_task)
            validation_result = validator_task.payload.get("result", {})
            if isinstance(validation_result, dict) and not validation_result.get("passed", True):
                sr.metadata["validation_issues"] = validation_result.get("issues", [])
        except BaseException:
            pass

    # ── 检查点 ─────────────────────────────────────────────────────

    def _save_checkpoint(
        self,
        script: WorkflowScript,
        last_completed_step: int,
        step_results: list[StepResult],
    ) -> str:
        cp = WorkflowCheckpoint(
            script=script,
            last_completed_step=last_completed_step,
            step_results=step_results,
        )
        os.makedirs(self._checkpoint_dir, exist_ok=True)
        path = os.path.join(
            self._checkpoint_dir, f"wf-checkpoint-{cp.id}.json"
        )
        with open(path, "w") as f:
            json.dump(cp.to_dict(), f, indent=2)
        return cp.id

    def _load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        path = os.path.join(
            self._checkpoint_dir, f"wf-checkpoint-{checkpoint_id}.json"
        )
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return WorkflowCheckpoint(
            id=data["id"],
            script=WorkflowScript.from_dict(data["script"]),
            last_completed_step=data["last_completed_step"],
            step_results=[
                StepResult(
                    step_name=sr["step_name"],
                    status=StepStatus(sr["status"]),
                    started_at=sr.get("started_at", ""),
                    completed_at=sr.get("completed_at", ""),
                    output=sr.get("output", {}),
                    error_message=sr.get("error_message", ""),
                    duration_ms=sr.get("duration_ms", 0.0),
                )
                for sr in data.get("step_results", [])
            ],
            created_at=data["created_at"],
        )

    def list_checkpoints(self) -> list[str]:
        if not os.path.isdir(self._checkpoint_dir):
            return []
        return sorted(
            f.replace("wf-checkpoint-", "").replace(".json", "")
            for f in os.listdir(self._checkpoint_dir)
            if f.startswith("wf-checkpoint-") and f.endswith(".json")
        )
