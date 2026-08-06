"""D5 tests: M1 integration — DesktopAgent orchestrator + end-to-end pipeline."""

from __future__ import annotations

import pytest

from maref.desktop.agent import (
    DesktopAgent,
    DesktopAgentState,
    DesktopOperation,
    DesktopStep,
    DesktopTask,
    DesktopTaskResult,
)
from maref.desktop.screen_capture import ScreenshotResult
from maref.desktop.screen_parser import ScreenParseResult


def _screen_capture_available() -> bool:
    try:
        from maref.desktop.screen_capture import ScreenCapture
        return ScreenCapture.detect_backend() != "none"
    except Exception:
        return False


requires_display = pytest.mark.skipif(
    not _screen_capture_available(),
    reason="No display available for screen capture",
)


class TestDesktopStep:
    def test_click_step(self):
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_text="Submit",
            description="Click submit button",
        )
        assert step.operation == DesktopOperation.CLICK
        assert step.target_text == "Submit"

    def test_type_step(self):
        step = DesktopStep(
            operation=DesktopOperation.TYPE,
            value="Hello World",
            description="Type greeting",
        )
        assert step.value == "Hello World"

    def test_hotkey_step(self):
        step = DesktopStep(
            operation=DesktopOperation.HOTKEY,
            value="command+c",
            description="Copy",
        )
        assert step.value == "command+c"

    def test_wait_step(self):
        step = DesktopStep(
            operation=DesktopOperation.WAIT,
            wait_seconds=2.0,
            description="Wait for animation",
        )
        assert step.wait_seconds == 2.0

    def test_position_step(self):
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_position=(100, 200),
        )
        assert step.target_position == (100, 200)

    def test_to_dict(self):
        step = DesktopStep(
            operation=DesktopOperation.CLICK, target_text="OK", description="Click OK"
        )
        d = step.to_dict()
        assert d["operation"] == "click"
        assert d["target_text"] == "OK"


class TestDesktopTask:
    def test_create_task(self):
        task = DesktopTask(
            task_id="task-001",
            description="Test task",
            safe_apps=["Finder"],
        )
        assert task.task_id == "task-001"
        assert len(task.steps) == 0

    def test_add_step(self):
        task = DesktopTask(task_id="t1", description="test")
        task.add_step(DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=1.0))
        task.add_step(DesktopStep(operation=DesktopOperation.CLICK, target_text="OK"))
        assert len(task.steps) == 2

    def test_default_max_retries(self):
        task = DesktopTask(task_id="t1", description="test")
        assert task.max_retries == 3


class TestDesktopTaskResult:
    def test_success(self):
        result = DesktopTaskResult(task_id="t1", success=True, steps_executed=3)
        assert result.success
        assert result.steps_executed == 3
        assert result.steps_failed == 0

    def test_failure(self):
        result = DesktopTaskResult(task_id="t1", success=False, error_message="timeout")
        assert not result.success
        assert result.error_message == "timeout"

    def test_to_dict(self):
        result = DesktopTaskResult(
            task_id="t1", success=True, steps_executed=2, total_duration_ms=1500.0
        )
        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert d["success"] is True
        assert d["steps_executed"] == 2
        assert d["total_duration_ms"] == 1500.0


class TestDesktopAgent:
    def test_init_defaults(self):
        agent = DesktopAgent()
        assert agent.dry_run is True
        assert agent.state == DesktopAgentState.IDLE
        assert agent.last_screenshot is None
        assert agent.last_parse_result is None

    def test_init_dry_run_false(self):
        agent = DesktopAgent(dry_run=False)
        assert not agent.dry_run

    def test_capture_screen(self):
        agent = DesktopAgent()
        result = agent.capture_screen()
        assert isinstance(result, ScreenshotResult)
        assert agent.state == DesktopAgentState.CAPTURING
        assert agent.last_screenshot is not None

    def test_parse_screen(self):
        agent = DesktopAgent()
        agent.capture_screen()
        parse = agent.parse_screen()
        assert isinstance(parse, ScreenParseResult)
        assert agent.state == DesktopAgentState.PARSING
        assert agent.last_parse_result is not None
        assert len(parse.elements) == 3

    def test_find_element_by_text(self):
        agent = DesktopAgent()
        parse = agent.parse_screen(agent.capture_screen())
        element = agent.find_element(parse, text="Submit")
        assert element is not None
        assert element.element_type.value == "button"

    def test_find_element_by_id(self):
        agent = DesktopAgent()
        parse = agent.parse_screen(agent.capture_screen())
        element = agent.find_element(parse, element_id="btn_001")
        assert element is not None
        assert element.text == "Submit"

    def test_find_element_missing(self):
        agent = DesktopAgent()
        parse = agent.parse_screen(agent.capture_screen())
        element = agent.find_element(parse, text="NonExistentElement")
        assert element is None

    def test_execute_click_step(self):
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen(agent.capture_screen())
        step = DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit")
        result = agent.execute_step(step, parse)
        assert result.success
        assert result.action_type == "click"

    def test_execute_type_step(self):
        agent = DesktopAgent(dry_run=True)
        step = DesktopStep(operation=DesktopOperation.TYPE, value="hello")
        result = agent.execute_step(step)
        assert result.success
        assert result.action_type == "type"

    def test_execute_hotkey_step(self):
        agent = DesktopAgent(dry_run=True)
        step = DesktopStep(operation=DesktopOperation.HOTKEY, value="command+c")
        result = agent.execute_step(step)
        assert result.success
        assert result.action_type == "hotkey"

    def test_execute_wait_step(self):
        agent = DesktopAgent(dry_run=True)
        step = DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.1)
        result = agent.execute_step(step)
        assert result.success

    def test_execute_step_element_not_found(self):
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen(agent.capture_screen())
        step = DesktopStep(operation=DesktopOperation.CLICK, target_text="ZZZ_Not_Real_ZZZ")
        result = agent.execute_step(step, parse)
        assert not result.success
        assert "not found" in result.details.lower()

    def test_execute_task_success(self):
        agent = DesktopAgent(dry_run=True)
        task = DesktopTask(
            task_id="test-001",
            description="Simple test task",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.05),
                DesktopStep(operation=DesktopOperation.TYPE, value="test"),
            ],
        )
        result = agent.execute_task(task)
        assert result.task_id == "test-001"
        assert result.success
        assert result.steps_executed == 2
        assert result.steps_failed == 0

    def test_execute_task_with_element_interaction(self):
        agent = DesktopAgent(dry_run=True)
        task = DesktopTask(
            task_id="test-002",
            description="Click submit button",
            steps=[
                DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit"),
            ],
        )
        result = agent.execute_task(task)
        assert result.success
        assert result.steps_executed == 1

    def test_run_demo_task(self):
        agent = DesktopAgent(dry_run=True)
        result = agent.run_demo_task()
        assert result.task_id == "demo-m1-001"
        assert result.steps_executed > 0

    def test_task_history(self):
        agent = DesktopAgent(dry_run=True)
        assert len(agent.get_task_history()) == 0
        task = DesktopTask(
            task_id="h1",
            description="history test",
            steps=[DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)],
        )
        agent.execute_task(task)
        assert len(agent.get_task_history()) == 1
        assert agent.get_task_history()[0].task_id == "h1"

    def test_state_transitions(self):
        agent = DesktopAgent(dry_run=True)
        assert agent.state == DesktopAgentState.IDLE
        agent.capture_screen()
        assert agent.state == DesktopAgentState.CAPTURING
        agent.parse_screen()
        assert agent.state == DesktopAgentState.PARSING

    def test_safe_app_enforcement(self):
        agent = DesktopAgent(dry_run=True, safe_apps={"OnlyThisApp"})
        task = DesktopTask(
            task_id="safe-test",
            description="Safe app test",
            safe_apps=["OnlyThisApp"],
            steps=[DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)],
        )
        result = agent.execute_task(task)
        assert result.success


class TestDesktopAgentIntegration:
    """End-to-end integration tests for M1 pipeline."""

    @requires_display
    def test_full_pipeline_simple(self):
        agent = DesktopAgent(dry_run=True)
        screenshot = agent.capture_screen()
        assert screenshot.width > 0 or screenshot.image is not None

        parse = agent.parse_screen(screenshot)
        assert len(parse.elements) >= 0

        submit = agent.find_element(parse, text="Submit")
        if submit:
            assert submit.is_interactive

    @requires_display
    def test_pipeline_with_verification(self):
        agent = DesktopAgent(dry_run=True)
        before = agent.capture_screen()
        agent.parse_screen(before)
        task = DesktopTask(
            task_id="verify-test",
            description="Full pipeline test",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.05),
                DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit"),
            ],
        )
        result = agent.execute_task(task)
        assert result.success
        assert len(result.operation_log) == 2
        assert len(result.screenshot_history) >= 1

    def test_multiple_tasks_history(self):
        agent = DesktopAgent(dry_run=True)
        for i in range(3):
            task = DesktopTask(
                task_id=f"multi-{i}",
                description=f"Task {i}",
                steps=[DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)],
            )
            agent.execute_task(task)
        assert len(agent.get_task_history()) == 3

    @requires_display
    def test_screenshot_save_and_parse(self):
        agent = DesktopAgent(dry_run=True)
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            screenshot = agent.screen.capture_fullscreen(output_path=path)
            assert screenshot.file_path == path
            parse = agent.parse_screen(screenshot)
            assert parse.screen_width > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)
