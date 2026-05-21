from __future__ import annotations

import pytest

from maref.desktop.opencua_loader import (
    OpenCUABenchmark,
    OpenCUABenchResult,
    OpenCUALoader,
    OpenCUATrajectory,
)
from maref.desktop.workflow_templates import (
    WORKFLOW_TEMPLATES,
    WorkflowCategory,
    WorkflowExecutor,
    WorkflowStep,
    WorkflowTemplate,
)
from maref.desktop.browser_auth import (
    AUTH_STATE_DIR,
    AuthSessionManager,
    AuthState,
)


class TestOpenCUALoader:
    def test_loader_creates_cache(self) -> None:
        loader = OpenCUALoader()
        assert loader._cache.exists()

    def test_load_mock_samples(self) -> None:
        loader = OpenCUALoader()
        trajectories = loader.load_samples(20)
        assert len(trajectories) == 20
        assert loader.loaded_count == 20
        assert isinstance(trajectories[0], OpenCUATrajectory)

    def test_trajectory_steps_have_predicted(self) -> None:
        loader = OpenCUALoader()
        trajs = loader.load_samples(10)
        all_steps = [s for t in trajs for s in t.steps]
        assert all("predicted" in s for s in all_steps)

    def test_download_handles_no_hub(self) -> None:
        loader = OpenCUALoader()
        result = loader.download()
        assert isinstance(result, bool)


class TestOpenCUABenchmark:
    def test_benchmark_computes_accuracy(self) -> None:
        loader = OpenCUALoader()
        trajs = loader.load_samples(50)
        benchmark = OpenCUABenchmark(trajs)
        result = benchmark.evaluate()
        assert 0.0 <= result.action_accuracy <= 1.0
        assert 0.0 <= result.task_success_rate <= 1.0
        assert result.total_trajectories == 50
        assert result.avg_steps > 0

    def test_benchmark_empty(self) -> None:
        benchmark = OpenCUABenchmark([])
        result = benchmark.evaluate()
        assert result.total_trajectories == 0
        assert result.action_accuracy == 0.0


class TestWorkflowTemplates:
    def test_all_templates_present(self) -> None:
        expected = {"compose_email", "edit_spreadsheet", "browser_form", "file_organize", "terminal_command"}
        assert set(WORKFLOW_TEMPLATES.keys()) == expected

    def test_each_template_has_steps(self) -> None:
        for name, template in WORKFLOW_TEMPLATES.items():
            assert len(template.steps) > 0, f"Template {name} has no steps"
            assert template.name == name

    def test_step_to_dict(self) -> None:
        step = WorkflowStep("hotkey", "command+n", wait_seconds=0.5, expected_app="Finder")
        d = step.to_dict()
        assert d["action_type"] == "hotkey"
        assert d["expected_app"] == "Finder"

    def test_template_to_dict(self) -> None:
        tmpl = WORKFLOW_TEMPLATES["compose_email"]
        d = tmpl.to_dict()
        assert d["name"] == "compose_email"
        assert d["category"] == "email"
        assert len(d["steps"]) > 0

    def test_executor_lists_templates(self) -> None:
        executor = WorkflowExecutor()
        templates = executor.list_templates()
        assert len(templates) == 5
        assert all("name" in t for t in templates)

    def test_executor_get_template(self) -> None:
        executor = WorkflowExecutor()
        tmpl = executor.get_template("compose_email")
        assert tmpl is not None
        assert tmpl.name == "compose_email"

    def test_executor_get_nonexistent(self) -> None:
        executor = WorkflowExecutor()
        assert executor.get_template("nonexistent") is None

    def test_executor_execute_dry(self) -> None:
        executor = WorkflowExecutor()
        result = executor.execute("file_organize")
        assert result["success"] is True
        assert result["template"] == "file_organize"

    def test_executor_execute_nonexistent_template(self) -> None:
        executor = WorkflowExecutor()
        result = executor.execute("nonexistent")
        assert result["success"] is False
        assert "error" in result

    def test_save_and_load_template(self, tmp_path) -> None:
        executor = WorkflowExecutor()
        path = tmp_path / "test_workflow.json"
        executor.save_template(WORKFLOW_TEMPLATES["terminal_command"], str(path))
        assert path.exists()
        loaded = executor.load_template(str(path))
        assert loaded is not None
        assert loaded.name == "terminal_command"


class TestBrowserAuth:
    def test_session_manager_create(self) -> None:
        manager = AuthSessionManager()
        state_id = manager.save_state("example.com")
        assert len(state_id) == 16

    def test_session_save_and_load(self) -> None:
        manager = AuthSessionManager()
        state_id = manager.save_state("test.com", cookies=[{"name": "session", "value": "abc123"}])
        state = manager.load_state(state_id)
        assert state is not None
        assert state.domain == "test.com"

    def test_session_list(self) -> None:
        manager = AuthSessionManager()
        sid1 = manager.save_state("a.example.com")
        sid2 = manager.save_state("b.example.com")
        states = manager.list_states()
        assert sid1 in states
        assert sid2 in states

    def test_session_delete(self) -> None:
        manager = AuthSessionManager()
        state_id = manager.save_state("todelete.com")
        assert state_id in manager.list_states()
        manager.delete_state(state_id)
        assert state_id not in manager.list_states()

    def test_load_nonexistent(self) -> None:
        manager = AuthSessionManager()
        assert manager.load_state("nonexistent_id") is None

    def test_auth_state_defaults(self) -> None:
        state = AuthState(domain="test.com")
        assert state.created_at > 0
        assert state.encrypted is False
        assert state.expires_at == 0.0

    def test_encryption_roundtrip(self) -> None:
        manager = AuthSessionManager()
        state_id = manager.save_state("encrypted.test.com", local_storage={"token": "secret-key"})
        state = manager.load_state(state_id)
        assert state is not None
        ls = state.local_storage_json
        assert "token" in ls


class TestDesktopChaos:
    def test_chaos_agent_recovery(self) -> None:
        from maref.desktop.task_executor import TaskExecutor, TaskStep, TaskStatus
        executor = TaskExecutor(max_retries=3)
        steps = [
            TaskStep(description="step 1", action_type="click", action_value="100,200"),
            TaskStep(description="step 2", action_type="type", action_value="hello"),
        ]
        result = executor.execute(steps, task_id="chaos-test")
        assert result.status == TaskStatus.SUCCESS

    def test_chaos_agent_failure_recovery(self) -> None:
        from maref.desktop.task_executor import TaskExecutor, TaskStep, TaskStatus
        import time
        executor = TaskExecutor(max_retries=2)

        class FailingAgent:
            def __init__(self):
                self.attempts = 0

            def execute_operation(self, action_type, action_value):
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("transient error")

        agent = FailingAgent()
        executor.agent = agent
        steps = [TaskStep(description="recovery test", action_type="click", action_value="100,200")]
        result = executor.execute(steps, task_id="recovery-test")
        assert result.status == TaskStatus.SUCCESS
        assert agent.attempts == 3

    def test_chaos_timeout_handling(self) -> None:
        from maref.desktop.task_executor import TaskExecutor, TaskStep
        executor = TaskExecutor(max_retries=1)
        steps = [TaskStep(description="normal step", action_type="hotkey", action_value="enter")]
        result = executor.execute(steps, task_id="timeout-test")
        assert result.total_elapsed_ms >= 0