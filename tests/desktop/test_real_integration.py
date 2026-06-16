"""Real hardware integration tests for MAREF Desktop Agent.

These tests require macOS with Accessibility permissions granted.
They are marked with @pytest.mark.real and skip gracefully when
permissions are not available.

Run: pytest tests/desktop/test_real_integration.py -v -m real
"""

from __future__ import annotations

import os
import platform
import subprocess

import pytest

from maref.desktop.agent import DesktopAgent, DesktopOperation, DesktopStep, DesktopTask
from maref.desktop.input_controller import InputController, InputSafetyGate
from maref.desktop.screen_capture import ScreenCapture
from maref.desktop.screen_parser import OmniParserInterface
from maref.desktop.window_manager import WindowManager

pytestmark = []

IS_MACOS = platform.system() == "Darwin"
IS_CI = bool(os.environ.get("CI"))


def _macos_accessibility_granted() -> bool:
    if not IS_MACOS:
        return False
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to return count of every process',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip().isdigit()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _screen_capture_available() -> bool:
    try:
        from maref.desktop.screen_capture import ScreenCapture
        return ScreenCapture.detect_backend() != "none"
    except Exception:
        return False

requires_accessibility = pytest.mark.skipif(
    not _macos_accessibility_granted(),
    reason="macOS Accessibility permissions not granted. "
    "Grant in System Preferences → Privacy & Security → Accessibility.",
)

requires_macos = pytest.mark.skipif(not IS_MACOS, reason="Requires macOS")

requires_display = pytest.mark.skipif(
    not _screen_capture_available(),
    reason="No display available for screen capture",
)


# ── Environment checks ────────────────────────────────────────────────


class TestEnvironmentChecks:
    """Verify runtime environment readiness."""

    def test_python_version(self) -> None:
        assert platform.python_version_tuple() >= ("3", "10")

    @requires_macos
    def test_platform_is_macos(self) -> None:
        assert IS_MACOS

    def test_pyautogui_importable(self) -> None:
        try:
            import pyautogui  # noqa: F401
        except ImportError:
            pytest.skip("PyAutoGUI not installed")

    def test_pillow_importable(self) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")


# ── InputController real-mode tests ───────────────────────────────────


@pytest.mark.real
class TestInputControllerReal:
    """Test InputController real-mode activation and safety."""

    def test_dry_run_default(self) -> None:
        controller = InputController()
        assert controller.dry_run is True

    def test_enable_real_mode(self) -> None:
        if not IS_MACOS:
            pytest.skip("Real mode only supported on macOS")
        controller = InputController(dry_run=True)
        if not controller.pyautogui_available:
            pytest.skip("PyAutoGUI not available")
        result = controller.enable_real_mode()
        assert result is True
        assert controller.dry_run is False

    def test_dry_run_setter_toggles_configuration(self) -> None:
        controller = InputController(dry_run=True)
        if not controller.pyautogui_available:
            pytest.skip("PyAutoGUI not available")
        controller.dry_run = False
        assert controller.dry_run is False

    def test_permissions_check_returns_dict(self) -> None:
        controller = InputController()
        perms = controller.check_permissions()
        assert isinstance(perms, dict)
        assert "pyautogui" in perms

    @requires_macos
    def test_permissions_check_macos_keys(self) -> None:
        controller = InputController()
        perms = controller.check_permissions()
        assert "accessibility" in perms

    def test_safety_gate_blocks_dangerous_hotkey(self) -> None:
        gate = InputSafetyGate()
        from maref.desktop.input_controller import KeyboardAction, KeyboardEvent

        event = KeyboardEvent(
            action=KeyboardAction.HOTKEY,
            keys=["command", "option", "esc"],
        )
        decision = gate.check_keyboard(event)
        # force_quit should be ASK_USER or BLOCK, not ALLOW
        assert decision.value != "allow"

    def test_safety_gate_blocks_rm_rf(self) -> None:
        gate = InputSafetyGate()
        from maref.desktop.input_controller import KeyboardAction, KeyboardEvent

        event = KeyboardEvent(
            action=KeyboardAction.TYPE,
            text="rm -rf /important",
        )
        decision = gate.check_keyboard(event)
        assert decision.value == "block"


# ── Screen capture real tests ─────────────────────────────────────────


class TestScreenCaptureReal:
    """Test screen capture on real hardware."""

    @requires_macos
    @requires_display
    def test_capture_fullscreen_mock(self) -> None:
        capture = ScreenCapture()
        result = capture.capture_fullscreen()
        assert result.width > 0
        assert result.height > 0

    def test_redaction_engine_config(self) -> None:
        from maref.desktop.screen_capture import RedactionEngine

        engine = RedactionEngine(auto_detect=True)
        assert len(engine.SENSITIVE_PATTERNS) > 0


# ── Window Manager real tests ─────────────────────────────────────────


class TestWindowManagerReal:
    """Test window manager backend detection and enumeration."""

    def test_backend_info(self) -> None:
        wm = WindowManager()
        info = wm.backend_info
        assert "system" in info
        assert "accessibility" in info
        assert "active_backend" in info

    @requires_accessibility
    def test_accessibility_available(self) -> None:
        wm = WindowManager()
        assert wm.accessibility_available is True

    @requires_accessibility
    def test_list_windows_returns_results(self) -> None:
        wm = WindowManager()
        windows = wm.list_windows()
        assert isinstance(windows, list)
        if IS_CI:
            return
        assert len(windows) > 0

    @requires_accessibility
    def test_get_active_window(self) -> None:
        wm = WindowManager()
        active = wm.get_active_window()
        if IS_CI:
            return
        assert active is not None
        assert active.app_name
        assert active.width > 0
        assert active.height > 0

    @requires_accessibility
    def test_find_windows_by_app(self) -> None:
        wm = WindowManager()
        finder_windows = wm.find_windows_by_app("Finder")
        assert isinstance(finder_windows, list)
        for w in finder_windows:
            assert "Finder" in w.app_name

    def test_is_safe_app(self) -> None:
        wm = WindowManager()
        assert wm.is_safe_app("Finder") is True
        assert wm.is_safe_app("Terminal") is True
        assert wm.is_safe_app("rm -rf") is False


# ── Screen Parser backend tests ───────────────────────────────────────


class TestScreenParserBackends:
    """Test all OmniParser backends init and parse."""

    def test_mock_backend_initializes(self) -> None:
        parser = OmniParserInterface(backend="mock")
        assert parser.initialize() is True
        assert parser.initialized is True

    def test_mock_parse_returns_elements(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        assert len(result.elements) >= 3
        assert result.parse_time_ms >= 0

    def test_mock_parse_find_interactive(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        interactive = result.find_interactive_elements()
        assert len(interactive) > 0

    def test_mock_parse_find_by_text(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        matches = result.find_elements_by_text("Submit")
        assert len(matches) >= 1

    def test_mock_parse_find_by_type(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        from maref.desktop.screen_parser import UIElementType

        buttons = result.find_elements_by_type(UIElementType.BUTTON)
        assert len(buttons) > 0

    def test_omni_parser_backend_graceful_fallback(self) -> None:
        if IS_CI:
            pytest.skip("OmniParser model download not suitable for CI")
        parser = OmniParserInterface(backend="omni_parser")
        ok = parser.initialize()
        if not ok:
            info = parser.backend_info
            assert "error" in info

    def test_cog_agent_backend_graceful_fallback(self) -> None:
        if IS_CI:
            pytest.skip("CogAgent model download not suitable for CI")
        parser = OmniParserInterface(backend="cog_agent")
        ok = parser.initialize()
        if not ok:
            info = parser.backend_info
            assert "error" in info

    def test_invalid_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported backend"):
            OmniParserInterface(backend="invalid_backend")

    def test_parse_before_init_raises(self) -> None:
        parser = OmniParserInterface(backend="mock")
        with pytest.raises(RuntimeError, match="not initialized"):
            parser.parse("/tmp/test.png")

    def test_backend_info_mock(self) -> None:
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        info = parser.backend_info
        assert info["backend"] == "mock"
        assert info["loaded"] is True


# ── DesktopAgent end-to-end tests ─────────────────────────────────────


class TestDesktopAgentEndToEnd:
    """Test end-to-end DesktopAgent pipeline (dry-run)."""

    def test_agent_initializes(self) -> None:
        agent = DesktopAgent(dry_run=True)
        assert agent.state.value == "idle"
        assert agent.dry_run is True

    @requires_display
    def test_agent_capture_screen_mock(self) -> None:
        agent = DesktopAgent(dry_run=True)
        screenshot = agent.capture_screen()
        assert screenshot.width > 0
        assert screenshot.height > 0

    def test_agent_parse_screen_mock(self) -> None:
        agent = DesktopAgent(dry_run=True)
        parse_result = agent.parse_screen()
        assert len(parse_result.elements) >= 3

    def test_agent_run_demo_task_dry_run(self) -> None:
        agent = DesktopAgent(dry_run=True)
        result = agent.run_demo_task()
        assert result.task_id == "demo-m1-001"
        assert result.success is True
        assert result.steps_executed >= 1

    def test_agent_task_with_safe_apps(self) -> None:
        agent = DesktopAgent(dry_run=True, safe_apps={"Finder"})
        task = DesktopTask(
            task_id="safe-test-001",
            description="Safe Finder task",
            safe_apps=["Finder"],
            steps=[
                DesktopStep(
                    operation=DesktopOperation.HOTKEY,
                    value="command+n",
                    description="New Finder window",
                    wait_seconds=0.3,
                ),
            ],
        )
        result = agent.execute_task(task)
        assert result.task_id == "safe-test-001"
        assert result.success is True

    def test_agent_step_with_target_position(self) -> None:
        agent = DesktopAgent(dry_run=True)
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_position=(100, 200),
            description="Click at position",
        )
        result = agent.execute_step(step)
        assert result.success is True

    def test_agent_step_target_not_found(self) -> None:
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen()
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="nonexistent_id",
            description="Click missing element",
        )
        result = agent.execute_step(step, parse)
        assert result.success is False

    def test_agent_find_element_by_text(self) -> None:
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen()
        element = agent.find_element(parse, text="Submit")
        assert element is not None
        assert element.text == "Submit"

    def test_agent_task_history(self) -> None:
        agent = DesktopAgent(dry_run=True)
        agent.run_demo_task()
        history = agent.get_task_history()
        assert len(history) >= 1
        assert history[0].task_id == "demo-m1-001"


# ── Real hardware smoke tests ─────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.real
class TestRealDesktopSmoke:
    """Minimal real-hardware smoke tests. Requires accessibility + PyAutoGUI."""

    @requires_accessibility
    def test_real_input_controller_noop_click(self) -> None:
        """Execute a single safe click in dry-run only — verifies pipeline integrity."""
        controller = InputController(dry_run=True)
        result = controller.click(100, 100)
        assert result.success is True
        assert len(controller.operation_log) == 1

    @requires_accessibility
    def test_real_window_enumeration(self) -> None:
        """Verify window enumeration returns valid data."""
        wm = WindowManager()
        windows = wm.list_windows()
        if IS_CI:
            return
        assert len(windows) > 0
        first = windows[0]
        assert isinstance(first.app_name, str)
        assert len(first.app_name) > 0

    @requires_accessibility
    @requires_display
    def test_real_desktop_agent_dry_run_pipeline(self) -> None:
        """Full pipeline: capture → parse → execute (dry-run) → verify."""
        agent = DesktopAgent(dry_run=True)
        screenshot = agent.capture_screen()
        parse = agent.parse_screen(screenshot)

        assert screenshot.width > 0
        assert len(parse.elements) >= 3
        assert agent.state.value in ("parsing", "deciding")

        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_position=(100, 100),
            description="Dry-run click at (100, 100)",
        )
        result = agent.execute_step(step)
        assert result.success is True
