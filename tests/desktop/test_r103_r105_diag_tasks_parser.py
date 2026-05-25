from __future__ import annotations

from unittest.mock import patch

from maref.desktop.screen_parser import OmniParserInterface


class TestCheckDesktopEnvExpanded:
    def test_gpu_check(self) -> None:
        from scripts.check_desktop_env import check_gpu
        gpu = check_gpu()
        assert "cuda" in gpu
        assert "mps" in gpu
        assert "available" in gpu
        assert "device" in gpu

    def test_network_check(self) -> None:
        from scripts.check_desktop_env import check_network
        net = check_network()
        assert "huggingface" in net
        assert "pypi" in net

    def test_disk_check(self) -> None:
        from scripts.check_desktop_env import check_disk_space
        disk = check_disk_space()
        assert "sufficient" in disk
        assert "cache_path" in disk

    def test_screen_resolution_check(self) -> None:
        from scripts.check_desktop_env import check_screen_resolution
        res = check_screen_resolution()
        assert "width" in res
        assert "height" in res
        assert "adequate" in res

    def test_multi_display_check(self) -> None:
        from scripts.check_desktop_env import check_multi_display
        md = check_multi_display()
        assert "count" in md
        assert md["count"] >= 1

    def test_sandbox_check(self) -> None:
        from scripts.check_desktop_env import check_sandbox_mode
        sb = check_sandbox_mode()
        assert "dry_run_ready" in sb
        assert "live_mode_ready" in sb

    def test_audit_check(self) -> None:
        from scripts.check_desktop_env import check_audit_log
        al = check_audit_log()
        for name in ("governance_audit.jsonl", "recursive_governance_audit.jsonl"):
            assert name in al
            assert "exists" in al[name]

    def test_main_json_output(self) -> None:
        import sys
        test_args = ["check_desktop_env.py", "--json"]
        with patch.object(sys, "argv", test_args):
            from scripts.check_desktop_env import main
            try:
                result = main()
                assert result == 0
            except SystemExit:
                pass

    def test_dependency_check_expanded(self) -> None:
        from scripts.check_desktop_env import check_dependencies
        deps = check_dependencies()
        assert "Pillow" in deps
        assert "PyAutoGUI" in deps
        assert "transformers" in deps
        assert "networkx" in deps
        assert "huggingface_hub" in deps


class TestTaskExecutor:
    def test_task_executor_creation(self) -> None:
        from maref.desktop.task_executor import TaskExecutor
        executor = TaskExecutor()
        assert executor._max_retries == 3

    def test_task_executor_executes_steps(self) -> None:
        from maref.desktop.task_executor import TaskExecutor, TaskStatus, TaskStep
        executor = TaskExecutor()
        steps = [
            TaskStep(description="step 1", action_type="hotkey", action_value="enter"),
            TaskStep(description="step 2", action_type="type", action_value="hello"),
        ]
        result = executor.execute(steps, task_id="test-1", description="test task")
        assert result.status == TaskStatus.SUCCESS
        assert result.steps_executed == 2
        assert result.steps_succeeded == 2

    def test_task_executor_template_finder(self) -> None:
        from maref.desktop.task_executor import TaskExecutor
        steps = TaskExecutor.from_template("open_finder")
        assert len(steps) == 3
        assert steps[0].action_type == "hotkey"

    def test_task_executor_template_browser(self) -> None:
        from maref.desktop.task_executor import TaskExecutor
        steps = TaskExecutor.from_template("open_browser")
        assert len(steps) == 3

    def test_task_executor_template_nonexistent(self) -> None:
        from maref.desktop.task_executor import TaskExecutor
        steps = TaskExecutor.from_template("nonexistent_template")
        assert steps == []

    def test_task_result_properties(self) -> None:
        from maref.desktop.task_executor import TaskResult, TaskStatus, TaskStepResult
        result = TaskResult(task_id="t1", description="test")
        result.status = TaskStatus.SUCCESS
        assert result.total_elapsed_ms == 0.0
        result.steps = [
            TaskStepResult(description="s1", success=True),
            TaskStepResult(description="s2", success=True),
        ]
        assert result.steps_executed == 2
        assert result.steps_succeeded == 2
        assert result.steps_failed == 0


class TestScreenParserBenchmark:
    def test_benchmark_returns_metrics(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        bench = parser.benchmark(num_runs=3)
        assert bench["backend"] == "mock"
        assert bench["num_runs"] == 3
        assert bench["avg_latency_ms"] >= 0
        assert bench["avg_elements"] >= 0
        assert "model" in bench

    def test_benchmark_default_runs(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        bench = parser.benchmark()
        assert bench["num_runs"] == 5

    def test_benchmark_uninitialized(self) -> None:
        parser = OmniParserInterface(backend="mock")
        bench = parser.benchmark(num_runs=2)
        assert "avg_latency_ms" in bench

    def test_benchmark_p99(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        bench = parser.benchmark(num_runs=5)
        assert "p99_latency_ms" in bench
        assert bench["p99_latency_ms"] >= 0
