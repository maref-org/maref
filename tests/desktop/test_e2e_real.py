"""End-to-end real mode tests for MAREF Desktop Agent.

Tests for environment checks, screen capture benchmarks, input controller
calibration, verification benchmarks, and DesktopAgent real mode.
All tests requiring accessibility permissions are marked with @pytest.mark.real.
"""

from __future__ import annotations

import os
import platform
import subprocess

import pytest

from maref.desktop.agent import (
    DesktopAgent,
    DesktopOperation,
    DesktopStep,
    DesktopTask,
    SelfHealingExecutor,
)
from maref.desktop.input_controller import InputController
from maref.desktop.screen_capture import ScreenCapture
from maref.desktop.verification import ScreenshotVerifier

IS_MACOS = platform.system() == "Darwin"
IS_CI = bool(os.environ.get("CI"))


def _macos_accessibility_granted() -> bool:
    if not IS_MACOS:
        return False
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return count of every process'],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip().isdigit()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requires_accessibility = pytest.mark.skipif(
    not _macos_accessibility_granted(),
    reason="macOS Accessibility permissions not granted.",
)

requires_macos = pytest.mark.skipif(not IS_MACOS, reason="Requires macOS")


class TestEnvironmentCheck:
    def test_agent_check_environment(self) -> None:
        agent = DesktopAgent(dry_run=True)
        env = agent.check_environment()
        assert "platform" in env
        assert "python_version" in env
        assert "permissions" in env
        assert "pyautogui_available" in env
        assert "parser_backend" in env
        assert "parser_actual_backend" in env
        assert "parser_initialized" in env
        assert "parser_info" in env

    def test_agent_check_environment_parser_auto(self) -> None:
        agent = DesktopAgent(dry_run=True)
        env = agent.check_environment()
        assert env["parser_backend"] == "auto"
        assert env["parser_actual_backend"] in ("omni_parser", "mock")


class TestScreenCaptureBenchmark:
    def test_benchmark_capture_returns_stats(self) -> None:
        bm = ScreenCapture.benchmark_capture(num_runs=3)
        assert "backend" in bm
        assert "avg_latency_ms" in bm
        assert "num_runs" in bm
        assert "successful_runs" in bm

    def test_detect_backend_returns_string(self) -> None:
        backend = ScreenCapture.detect_backend()
        assert backend in ("pyautogui", "screencapture_cli", "none")

    @requires_macos
    def test_detect_backend_macos(self) -> None:
        backend = ScreenCapture.detect_backend()
        assert backend != "none"


class TestInputControllerCalibration:
    def test_calibrate_returns_screen_info(self) -> None:
        controller = InputController()
        info = controller.calibrate()
        assert "screen_width" in info
        assert "screen_height" in info
        assert "scale_factor" in info
        assert "is_retina" in info

    @requires_macos
    def test_calibrate_macos_detects_retina(self) -> None:
        controller = InputController()
        info = controller.calibrate()
        assert info["scale_factor"] >= 1.0

    def test_check_permissions_returns_dict(self) -> None:
        controller = InputController()
        perms = controller.check_permissions()
        assert isinstance(perms, dict)
        assert "pyautogui" in perms


class TestVerificationBenchmark:
    def test_benchmark_returns_stats(self) -> None:
        bm = ScreenshotVerifier.benchmark(image_size=(800, 600))
        assert isinstance(bm, dict)
        if "error" in bm:
            pytest.skip(bm["error"])
        assert "avg_comparison_ms" in bm
        assert bm["image_size"] == (800, 600)

    def test_benchmark_default_size(self) -> None:
        bm = ScreenshotVerifier.benchmark()
        assert isinstance(bm, dict)
        if "error" in bm:
            pytest.skip(bm["error"])
        assert bm["image_size"] == (1920, 1080)


@pytest.mark.real
class TestDesktopAgentRealMode:
    def test_enable_real_returns_bool(self) -> None:
        agent = DesktopAgent(dry_run=True)
        result = agent.enable_real()
        assert isinstance(result, bool)

    def test_execute_task_real_dry_run_safe(self) -> None:
        agent = DesktopAgent(dry_run=True)
        task = DesktopTask(
            task_id="real-test-001",
            description="Safe real mode test in dry run",
            steps=[
                DesktopStep(
                    operation=DesktopOperation.WAIT,
                    wait_seconds=0.01,
                    description="Safe wait step",
                ),
            ],
        )
        result = agent.execute_task(task)
        assert result.task_id == "real-test-001"
        assert result.success is True

    @requires_accessibility
    def test_enable_real_mode_with_accessibility(self) -> None:
        agent = DesktopAgent(dry_run=True)
        result = agent.enable_real()
        if agent.input.pyautogui_available:
            assert agent.dry_run is False
            assert result is True

    @requires_accessibility
    def test_execute_task_real_raises_without_pyautogui(self) -> None:
        agent = DesktopAgent(dry_run=True)
        if not agent.input.pyautogui_available:
            with pytest.raises(PermissionError, match="Real mode requires PyAutoGUI"):
                agent.execute_task_real(DesktopTask(task_id="test", description="test"))


class TestSelfHealingExecutor:
    def test_healing_executor_initializes(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        assert executor.consecutive_failures == 0
        assert executor.circuit_open is False

    def test_healing_executor_successful_step(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        step = DesktopStep(
            operation=DesktopOperation.WAIT,
            wait_seconds=0.01,
        )
        result = executor.execute_step(step)
        assert result.success is True
        assert executor.consecutive_failures == 0

    def test_healing_executor_recovers_from_failure(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        parse = agent.parse_screen()
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="nonexistent_element_zzz",
        )
        result = executor.execute_step(step, parse)
        assert result.success is False or executor.circuit_open

    def test_healing_executor_task_with_retry(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        task = DesktopTask(
            task_id="healing-test-001",
            description="Task with healing",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        result = executor.execute_task(task)
        assert result.task_id == "healing-test-001"
        assert result.success is True

    def test_circuit_breaker_triggers_after_consecutive_failures(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=2)
        parse = agent.parse_screen()
        bad_step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="definitely_missing_element_xyz",
        )
        executor.execute_step(bad_step, parse)
        executor.execute_step(bad_step, parse)
        assert executor.circuit_open is True or executor.consecutive_failures >= 2

    def test_circuit_reset_works(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=1)
        parse = agent.parse_screen()
        bad_step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="missing_element_abc",
        )
        executor.execute_step(bad_step, parse)
        executor.reset_circuit()
        assert executor.circuit_open is False
        assert executor.consecutive_failures == 0

    def test_run_demo_task_dry_run_param(self) -> None:
        agent = DesktopAgent(dry_run=True)
        result = agent.run_demo_task(dry_run=True)
        assert result.task_id == "demo-m1-001"
        assert result.success is True


class TestActionRecorderIntegration:
    """Test ActionRecorder integration with DesktopAgent."""

    @pytest.mark.real
    def test_start_stop_recording(self) -> None:
        agent = DesktopAgent(dry_run=True)
        recording = agent.start_recording(
            recording_id="test-rec-001",
            name="Test Recording",
            application="Finder",
            description="Test recording integration",
        )
        assert recording.recording_id == "test-rec-001"
        assert recording.name == "Test Recording"
        assert agent.recording_active is True

        task = DesktopTask(
            task_id="rec-test",
            description="Task for recording test",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(operation=DesktopOperation.TYPE, value="hello", wait_seconds=0.01),
            ],
        )
        agent.execute_task(task)

        stopped = agent.stop_recording()
        assert stopped is not None
        assert stopped.recording_id == "test-rec-001"
        assert stopped.step_count == 2
        assert agent.recording_active is False

    @pytest.mark.real
    def test_recording_steps_match_operations(self) -> None:
        agent = DesktopAgent(dry_run=True)
        agent.start_recording(
            recording_id="test-rec-002",
            name="Operation Types Test",
        )

        task = DesktopTask(
            task_id="rec-ops-test",
            description="Test for recording step types",
            steps=[
                DesktopStep(operation=DesktopOperation.CLICK, target_position=(100, 100)),
                DesktopStep(operation=DesktopOperation.HOTKEY, value="command+c"),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        agent.execute_task(task)

        recording = agent.stop_recording()
        assert recording is not None
        assert recording.step_count == 3

        action_types = [s.action_type.value for s in recording.steps]
        assert "mouse_click" in action_types
        assert "keyboard_hotkey" in action_types
        assert "wait" in action_types

    @pytest.mark.real
    def test_replay_recording_dry_run(self) -> None:
        agent = DesktopAgent(dry_run=True)
        agent.start_recording(
            recording_id="test-rec-003",
            name="Replay Test",
        )

        task = DesktopTask(
            task_id="replay-src",
            description="Task for replay source",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        agent.execute_task(task)
        agent.stop_recording()

        result = agent.replay_recording("test-rec-003", dry_run=True)
        assert result.success is True
        assert result.task_id == "replay-test-rec-003"

    @pytest.mark.real
    def test_replay_nonexistent_recording(self) -> None:
        agent = DesktopAgent(dry_run=True)
        result = agent.replay_recording("nonexistent-recording-id")
        assert result.success is False
        assert "not found" in result.error_message

    @pytest.mark.real
    def test_recorder_property_accessible(self) -> None:
        agent = DesktopAgent(dry_run=True)
        assert agent.recorder is not None
        assert agent.recording_active is False

    @pytest.mark.real
    def test_stop_recording_when_not_recording(self) -> None:
        agent = DesktopAgent(dry_run=True)
        assert agent.recording_active is False
        result = agent.stop_recording()
        assert result is None

    @pytest.mark.real
    def test_recording_without_id_generates_timestamp(self) -> None:
        agent = DesktopAgent(dry_run=True)
        recording = agent.start_recording(name="Auto ID Test")
        assert recording.recording_id.startswith("rec-")
        agent.stop_recording()

    @pytest.mark.real
    def test_recording_persists_and_loaded(self) -> None:
        agent = DesktopAgent(dry_run=True)
        agent.start_recording(
            recording_id="test-rec-persist",
            name="Persistence Test",
        )
        agent.execute_task(DesktopTask(
            task_id="persist-task",
            description="Task for persistence test",
            steps=[DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)],
        ))
        agent.stop_recording()

        loaded = agent.recorder.load("test-rec-persist")
        assert loaded is not None
        assert loaded.name == "Persistence Test"
        assert loaded.step_count >= 1
