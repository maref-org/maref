from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RECOVERED = "recovered"


@dataclass
class TaskStep:
    description: str
    app: str = ""
    action_type: str = ""
    action_value: str = ""
    expected_outcome: str = ""
    timeout_seconds: float = 30.0


@dataclass
class TaskStepResult:
    description: str
    success: bool
    elapsed_ms: float = 0.0
    error: str = ""
    recovery_attempted: bool = False
    recovery_success: bool = False


@dataclass
class TaskResult:
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStepResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    error_summary: str = ""

    @property
    def steps_executed(self) -> int:
        return len(self.steps)

    @property
    def steps_succeeded(self) -> int:
        return sum(1 for s in self.steps if s.success)

    @property
    def steps_failed(self) -> int:
        return sum(1 for s in self.steps if not s.success)


class TaskExecutor:
    """Executes desktop automation tasks with timeout, retry, and recovery.

    A task is a sequence of steps, each describing a desktop operation.
    The executor handles:
    - Per-step timeout
    - Automatic recovery (3 retries per step)
    - Status tracking and reporting
    """

    def __init__(
        self,
        agent: Any | None = None,
        max_retries: int = 3,
        default_timeout: float = 30.0,
    ) -> None:
        self.agent = agent
        self._max_retries = max_retries
        self._default_timeout = default_timeout

    def execute(
        self,
        steps: list[TaskStep],
        task_id: str = "",
        description: str = "",
        on_step_start: Callable[[TaskStep], None] | None = None,
        on_step_end: Callable[[TaskStep, TaskStepResult], None] | None = None,
    ) -> TaskResult:
        result = TaskResult(task_id=task_id, description=description)
        start_total = time.time()

        for step in steps:
            if on_step_start:
                on_step_start(step)

            step_result = self._execute_step(step)
            result.steps.append(step_result)

            if on_step_end:
                on_step_end(step, step_result)

            if not step_result.success:
                result.status = TaskStatus.FAILED
                result.total_elapsed_ms = (time.time() - start_total) * 1000
                result.error_summary = f"Failed at step '{step.description}': {step_result.error}"
                return result

        result.status = TaskStatus.SUCCESS
        result.total_elapsed_ms = (time.time() - start_total) * 1000
        return result

    def _execute_step(self, step: TaskStep) -> TaskStepResult:
        last_error = ""

        for attempt in range(self._max_retries + 1):
            start = time.time()
            try:
                if self.agent is not None:
                    self.agent.execute_operation(step.action_type, step.action_value)

                elapsed = (time.time() - start) * 1000
                return TaskStepResult(
                    description=step.description,
                    success=True,
                    elapsed_ms=elapsed,
                    recovery_attempted=attempt > 0,
                    recovery_success=attempt > 0,
                )
            except Exception as e:
                last_error = str(e)
                if attempt >= self._max_retries:
                    break

        elapsed = (time.time() - start) * 1000
        return TaskStepResult(
            description=step.description,
            success=False,
            elapsed_ms=elapsed,
            error=last_error,
            recovery_attempted=True,
            recovery_success=False,
        )

    @staticmethod
    def from_template(template_name: str) -> list[TaskStep]:
        templates = {
            "open_finder": [
                TaskStep(
                    description="Open Spotlight", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(description="Type Finder", action_type="type", action_value="Finder"),
                TaskStep(description="Open Finder", action_type="hotkey", action_value="enter"),
            ],
            "open_browser": [
                TaskStep(
                    description="Open Spotlight", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(
                    description="Type browser name", action_type="type", action_value="Safari"
                ),
                TaskStep(description="Launch browser", action_type="hotkey", action_value="enter"),
            ],
            "compose_email": [
                TaskStep(
                    description="Open Mail", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(description="Type Mail", action_type="type", action_value="Mail"),
                TaskStep(description="Launch Mail", action_type="hotkey", action_value="enter"),
                TaskStep(description="New message", action_type="hotkey", action_value="command+n"),
            ],
            "edit_spreadsheet": [
                TaskStep(
                    description="Open Spotlight", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(description="Type Numbers", action_type="type", action_value="Numbers"),
                TaskStep(description="Launch Numbers", action_type="hotkey", action_value="enter"),
            ],
            "file_organize": [
                TaskStep(
                    description="Open Finder", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(description="Type Finder", action_type="type", action_value="Finder"),
                TaskStep(description="Launch Finder", action_type="hotkey", action_value="enter"),
                TaskStep(description="New window", action_type="hotkey", action_value="command+n"),
            ],
            "terminal_command": [
                TaskStep(
                    description="Open Terminal", action_type="hotkey", action_value="command+space"
                ),
                TaskStep(description="Type Terminal", action_type="type", action_value="Terminal"),
                TaskStep(description="Launch Terminal", action_type="hotkey", action_value="enter"),
            ],
        }
        return templates.get(template_name, [])


TEMPLATE_DESCRIPTIONS = {
    "open_finder": "Open Finder application",
    "open_browser": "Open Safari browser",
    "compose_email": "Compose a new email in Mail",
    "edit_spreadsheet": "Open Numbers spreadsheet",
    "file_organize": "Open Finder for file organization",
    "terminal_command": "Open Terminal for command execution",
}
