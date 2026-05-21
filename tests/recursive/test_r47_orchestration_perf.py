from __future__ import annotations

from maref.recursive.orchestration_perf import (
    CacheStats,
    ConcurrentOrchestrator,
    OrchestrationCache,
    TimeoutConfig,
    TimeoutController,
)


class TestOrchestrationCache:
    def test_put_and_get(self) -> None:
        cache = OrchestrationCache(max_size=10)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.size == 1

    def test_miss_returns_none(self) -> None:
        cache = OrchestrationCache()
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self) -> None:
        cache = OrchestrationCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_access_reorders(self) -> None:
        cache = OrchestrationCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        cache.put("c", 3)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_clear(self) -> None:
        cache = OrchestrationCache()
        cache.put("a", 1)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_cache_stats_hit(self) -> None:
        cache = OrchestrationCache()
        cache.put("a", 1)
        cache.get("a")
        assert cache.stats.hits == 1
        assert cache.stats.misses == 0
        assert cache.stats.total_requests == 1

    def test_cache_stats_miss(self) -> None:
        cache = OrchestrationCache()
        cache.get("nonexistent")
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0

    def test_hit_rate(self) -> None:
        cache = OrchestrationCache()
        cache.put("a", 1)
        cache.get("a")
        cache.get("b")
        cache.get("c")
        assert cache.stats.hit_rate == 1.0 / 3.0

    def test_hit_rate_empty(self) -> None:
        stats = CacheStats()
        assert stats.hit_rate == 0.0


class TestTimeoutController:
    def test_execute_within_timeout(self) -> None:
        config = TimeoutConfig(llm_decompose_timeout=5.0)
        controller = TimeoutController(config)
        result, tr = controller.execute_with_timeout(
            "llm_decompose",
            lambda: "success",
        )
        assert result == "success"
        assert tr.timed_out is False
        assert tr.operation == "llm_decompose"

    def test_execute_exception_is_timeout(self) -> None:
        controller = TimeoutController()

        def failing() -> str:
            raise RuntimeError("fail")

        result, tr = controller.execute_with_timeout("dispatch", failing)
        assert result is None
        assert tr.timed_out is True

    def test_execute_with_override(self) -> None:
        controller = TimeoutController()
        result, tr = controller.execute_with_timeout(
            "llm_decompose",
            lambda: "ok",
            timeout_override=0.01,
        )
        assert result == "ok"

    def test_timeout_config_defaults(self) -> None:
        config = TimeoutConfig()
        assert config.llm_decompose_timeout == 5.0
        assert config.dispatch_timeout == 2.0
        assert config.handoff_timeout == 30.0
        assert config.sync_timeout == 10.0


class TestConcurrentOrchestrator:
    def test_dispatch_concurrent_all_success(self) -> None:
        orch = ConcurrentOrchestrator()
        tasks = [
            {"id": "task_a", "data": 1},
            {"id": "task_b", "data": 2},
            {"id": "task_c", "data": 3},
        ]

        def executor(task: dict) -> str:
            return f"executed_{task['id']}"

        results = orch.dispatch_concurrent(tasks, executor)
        assert len(results) == 3
        for r in results:
            assert "executed" in str(r.result)
            assert r.timed_out is False
            assert r.error == ""

    def test_dispatch_concurrent_with_error(self) -> None:
        orch = ConcurrentOrchestrator()
        tasks = [
            {"id": "task_a"},
            {"id": "task_b"},
        ]

        def executor(task: dict) -> str:
            if task["id"] == "task_b":
                raise RuntimeError("task failed")
            return "ok"

        results = orch.dispatch_concurrent(tasks, executor)
        assert results[0].timed_out is False
        assert results[1].timed_out is True
        assert "task failed" in results[1].error

    def test_resolve_dependencies_linear(self) -> None:
        orch = ConcurrentOrchestrator()
        subtasks = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": ["a"]},
            {"id": "c", "dependencies": ["b"]},
        ]
        waves = orch.resolve_dependencies(subtasks)
        assert len(waves) == 3
        assert [t["id"] for t in waves[0]] == ["a"]
        assert [t["id"] for t in waves[1]] == ["b"]
        assert [t["id"] for t in waves[2]] == ["c"]

    def test_resolve_dependencies_parallel(self) -> None:
        orch = ConcurrentOrchestrator()
        subtasks = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": []},
            {"id": "c", "dependencies": ["a", "b"]},
        ]
        waves = orch.resolve_dependencies(subtasks)
        assert len(waves) == 2
        assert {t["id"] for t in waves[0]} == {"a", "b"}
        assert [t["id"] for t in waves[1]] == ["c"]

    def test_resolve_dependencies_diamond(self) -> None:
        orch = ConcurrentOrchestrator()
        subtasks = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": ["a"]},
            {"id": "c", "dependencies": ["a"]},
            {"id": "d", "dependencies": ["b", "c"]},
        ]
        waves = orch.resolve_dependencies(subtasks)
        assert len(waves) == 3
        assert [t["id"] for t in waves[0]] == ["a"]
        assert {t["id"] for t in waves[1]} == {"b", "c"}
        assert [t["id"] for t in waves[2]] == ["d"]

    def test_resolve_dependencies_empty(self) -> None:
        orch = ConcurrentOrchestrator()
        waves = orch.resolve_dependencies([])
        assert waves == []

    def test_resolve_dependencies_no_deps(self) -> None:
        orch = ConcurrentOrchestrator()
        subtasks = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": []},
        ]
        waves = orch.resolve_dependencies(subtasks)
        assert len(waves) == 1
        assert {t["id"] for t in waves[0]} == {"a", "b"}
