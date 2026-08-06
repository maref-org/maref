from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def record_hit(self) -> None:
        self.hits += 1
        self.total_requests += 1

    def record_miss(self) -> None:
        self.misses += 1
        self.total_requests += 1


class OrchestrationCache:
    def __init__(self, max_size: int = 256) -> None:
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._stats = CacheStats()

    def get(self, key: str) -> Any | None:
        if key in self._store:
            self._store.move_to_end(key)
            self._stats.record_hit()
            return self._store[key]
        self._stats.record_miss()
        return None

    def put(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
            self._store[key] = value
        else:
            if len(self._store) >= self._max_size:
                self._store.popitem(last=False)
                self._stats.evictions += 1
            self._store[key] = value

    def clear(self) -> None:
        self._store.clear()
        self._stats = CacheStats()

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def stats(self) -> CacheStats:
        return self._stats


@dataclass
class TimeoutConfig:
    llm_decompose_timeout: float = 5.0
    dispatch_timeout: float = 2.0
    handoff_timeout: float = 30.0
    sync_timeout: float = 10.0


@dataclass
class TimeoutResult:
    timed_out: bool
    operation: str
    elapsed: float
    timeout_limit: float


class TimeoutController:
    def __init__(self, config: TimeoutConfig | None = None) -> None:
        self._config = config or TimeoutConfig()

    def execute_with_timeout(
        self,
        operation: str,
        fn: Callable[[], Any],
        timeout_override: float | None = None,
    ) -> tuple[Any, TimeoutResult]:
        timeout_limit = timeout_override or getattr(self._config, f"{operation}_timeout", 5.0)
        if timeout_limit is None:
            timeout_limit = 5.0
        start = time.time()
        try:
            result = fn()
            elapsed = time.time() - start
            return result, TimeoutResult(
                timed_out=elapsed > timeout_limit,
                operation=operation,
                elapsed=elapsed,
                timeout_limit=timeout_limit,
            )
        except Exception:
            elapsed = time.time() - start
            return None, TimeoutResult(
                timed_out=True,
                operation=operation,
                elapsed=elapsed,
                timeout_limit=timeout_limit,
            )


@dataclass
class ConcurrentDispatchResult:
    subtask_id: str
    result: Any
    elapsed: float
    timed_out: bool = False
    error: str = ""


class ConcurrentOrchestrator:
    def __init__(self, max_concurrent: int = 4) -> None:
        self._max_concurrent = max_concurrent

    def dispatch_concurrent(
        self,
        tasks: list[dict[str, Any]],
        executor: Callable[[dict[str, Any]], Any],
    ) -> list[ConcurrentDispatchResult]:
        results: list[ConcurrentDispatchResult] = []
        for task in tasks:
            start = time.time()
            try:
                result = executor(task)
                elapsed = time.time() - start
                results.append(
                    ConcurrentDispatchResult(
                        subtask_id=task.get("id", "unknown"),
                        result=result,
                        elapsed=elapsed,
                    )
                )
            except Exception as e:
                elapsed = time.time() - start
                results.append(
                    ConcurrentDispatchResult(
                        subtask_id=task.get("id", "unknown"),
                        result=None,
                        elapsed=elapsed,
                        timed_out=True,
                        error=str(e),
                    )
                )
        return results

    def resolve_dependencies(self, subtasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if not subtasks:
            return []
        task_map: dict[str, dict[str, Any]] = {t["id"]: t for t in subtasks}
        in_degree: dict[str, int] = {t["id"]: 0 for t in subtasks}
        adj: dict[str, list[str]] = {t["id"]: [] for t in subtasks}

        for task in subtasks:
            for dep in task.get("dependencies", []):
                if dep in task_map:
                    adj[dep].append(task["id"])
                    in_degree[task["id"]] += 1

        waves: list[list[dict[str, Any]]] = []
        processed: set[str] = set()

        while len(processed) < len(subtasks):
            wave: list[dict[str, Any]] = []
            for task in subtasks:
                tid = task["id"]
                if tid not in processed and in_degree.get(tid, 0) == 0:
                    wave.append(task)
            if not wave:
                remaining = [t["id"] for t in subtasks if t["id"] not in processed]
                for tid in remaining:
                    wave.append(task_map[tid])
                waves.append(wave)
                break
            for task in wave:
                processed.add(task["id"])
                for neighbor in adj.get(task["id"], []):
                    in_degree[neighbor] = max(0, in_degree.get(neighbor, 1) - 1)
            waves.append(wave)

        return waves
