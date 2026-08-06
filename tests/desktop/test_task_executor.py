from __future__ import annotations

from maref.desktop.task_executor import (
    TaskExecutor,
    TaskResult,
    TaskStatus,
    TaskStep,
    TaskStepResult,
)


class TestTaskResult:
    def test_init_defaults(self) -> None:
        result = TaskResult(task_id="t1", description="test")
        assert result.status == TaskStatus.PENDING
        assert result.steps == []
        assert result.steps_executed == 0
        assert result.steps_succeeded == 0
        assert result.steps_failed == 0

    def test_steps_succeeded(self) -> None:
        result = TaskResult(task_id="t1", description="test")
        result.steps.append(TaskStepResult(description="s1", success=True))
        result.steps.append(TaskStepResult(description="s2", success=False))
        assert result.steps_executed == 2
        assert result.steps_succeeded == 1
        assert result.steps_failed == 1


class TestTaskExecutor:
    def test_execute_all_success(self) -> None:
        executor = TaskExecutor()
        steps = [
            TaskStep(description="Step 1", action_type="click", action_value="100,200"),
            TaskStep(description="Step 2", action_type="type", action_value="hello"),
        ]
        result = executor.execute(steps, task_id="t1", description="test plan")
        assert result.status == TaskStatus.SUCCESS
        assert len(result.steps) == 2
        assert result.steps_succeeded == 2

    def test_execute_with_mock_agent(self) -> None:
        class MockAgent:
            def execute_operation(self, action_type: str, action_value: str) -> None:
                pass

        executor = TaskExecutor(agent=MockAgent())
        steps = [TaskStep(description="Step 1", action_type="click", action_value="100,200")]
        result = executor.execute(steps, task_id="t2")
        assert result.status == TaskStatus.SUCCESS

    def test_execute_agent_fails_then_retries(self) -> None:
        class FailingAgent:
            def __init__(self):
                self._call_count = 0

            def execute_operation(self, action_type: str, action_value: str) -> None:
                self._call_count += 1
                if self._call_count < 2:
                    raise RuntimeError(f"Attempt {self._call_count} failed")

        agent = FailingAgent()
        executor = TaskExecutor(agent=agent, max_retries=3)
        steps = [TaskStep(description="Step 1", action_type="click", action_value="100,200")]
        result = executor.execute(steps, task_id="t3")
        assert result.status == TaskStatus.SUCCESS
        assert agent._call_count == 2

    def test_execute_agent_always_fails(self) -> None:
        class AlwaysFailingAgent:
            def execute_operation(self, action_type: str, action_value: str) -> None:
                raise RuntimeError("always fails")

        executor = TaskExecutor(agent=AlwaysFailingAgent(), max_retries=1)
        steps = [TaskStep(description="Step 1", action_type="click", action_value="100,200")]
        result = executor.execute(steps, task_id="t4")
        assert result.status == TaskStatus.FAILED
        assert result.steps_failed == 1
        assert "always fails" in result.error_summary

    def test_execute_step_timeout(self) -> None:
        executor = TaskExecutor(max_retries=0)
        # No agent set, so it will succeed without exception
        steps = [TaskStep(description="Step 1", timeout_seconds=1.0)]
        result = executor.execute(steps, task_id="t5")
        assert result.status == TaskStatus.SUCCESS

    def test_execute_with_callbacks(self) -> None:
        executor = TaskExecutor()
        step_starts: list[str] = []
        step_ends: list[str] = []

        def on_start(step: TaskStep) -> None:
            step_starts.append(step.description)

        def on_end(step: TaskStep, step_result: TaskStepResult) -> None:
            step_ends.append(step.description)

        steps = [
            TaskStep(description="Step A"),
            TaskStep(description="Step B"),
        ]
        result = executor.execute(steps, task_id="t6", on_step_start=on_start, on_step_end=on_end)
        assert result.status == TaskStatus.SUCCESS
        assert step_starts == ["Step A", "Step B"]
        assert step_ends == ["Step A", "Step B"]

    def test_execute_with_callback_on_failure(self) -> None:
        class FailingAgent:
            def execute_operation(self, action_type: str, action_value: str) -> None:
                raise RuntimeError("fail")

        executor = TaskExecutor(agent=FailingAgent(), max_retries=0)
        step_ends: list[str] = []

        def on_end(step: TaskStep, step_result: TaskStepResult) -> None:
            step_ends.append(step.description)

        steps = [TaskStep(description="Step X")]
        result = executor.execute(steps, task_id="t7", on_step_end=on_end)
        assert result.status == TaskStatus.FAILED
        assert step_ends == ["Step X"]

    def test_from_template_known(self) -> None:
        steps = TaskExecutor.from_template("open_finder")
        assert len(steps) == 3
        assert steps[0].description == "Open Spotlight"
        assert steps[2].action_value == "enter"

    def test_from_template_browser(self) -> None:
        steps = TaskExecutor.from_template("open_browser")
        assert len(steps) == 3
        assert steps[1].action_value == "Safari"

    def test_from_template_compose_email(self) -> None:
        steps = TaskExecutor.from_template("compose_email")
        assert len(steps) == 4

    def test_from_template_unknown(self) -> None:
        steps = TaskExecutor.from_template("nonexistent")
        assert steps == []

    def test_from_template_file_organize(self) -> None:
        steps = TaskExecutor.from_template("file_organize")
        assert len(steps) == 4

    def test_from_template_terminal_command(self) -> None:
        steps = TaskExecutor.from_template("terminal_command")
        assert len(steps) == 3

    def test_from_template_edit_spreadsheet(self) -> None:
        steps = TaskExecutor.from_template("edit_spreadsheet")
        assert len(steps) == 3
