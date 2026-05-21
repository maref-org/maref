from __future__ import annotations

from unittest.mock import patch

import pytest

from maref.desktop.input_controller import (
    InputController,
    InputSafetyGate,
    KeyboardAction,
    KeyboardEvent,
    MouseAction,
    MouseEvent,
    SafetyDecision,
)


def _make_gate() -> InputSafetyGate:
    g = InputSafetyGate()
    g._last_operation_time: dict[str, float] = {}
    g._operation_count: dict[str, int] = {}
    return g


def _make_dry_controller(**kwargs) -> InputController:
    return InputController(dry_run=True, **kwargs)


def _make_mock_real_controller(**kwargs) -> InputController:
    c = InputController(dry_run=False, **kwargs)
    c._pyautogui_available = True
    c._pyautogui_configured = True
    return c


class TestInputSafetyGateSafeRegion:
    def test_safe_region_allows_inside(self) -> None:
        gate = _make_gate()
        gate.safe_region = (0, 0, 1920, 1080)
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.ALLOW

    def test_safe_region_blocks_outside(self) -> None:
        gate = _make_gate()
        gate.safe_region = (0, 0, 1920, 1080)
        event = MouseEvent(action=MouseAction.CLICK, x=2500, y=200)
        assert gate.check_mouse(event) == SafetyDecision.BLOCK

    def test_safe_region_none_allows_anything(self) -> None:
        gate = _make_gate()
        gate.safe_region = None
        event = MouseEvent(action=MouseAction.CLICK, x=99999, y=99999)
        assert gate.check_mouse(event) == SafetyDecision.ALLOW

    def test_safe_region_corner_cases(self) -> None:
        g1 = _make_gate()
        g1.safe_region = (100, 100, 500, 500)
        assert g1.check_mouse(MouseEvent(action=MouseAction.CLICK, x=100, y=100)) == SafetyDecision.ALLOW

        g2 = _make_gate()
        g2.safe_region = (100, 100, 500, 500)
        assert g2.check_mouse(MouseEvent(action=MouseAction.CLICK, x=300, y=300)) == SafetyDecision.ALLOW

        g3 = _make_gate()
        g3.safe_region = (100, 100, 500, 500)
        assert g3.check_mouse(MouseEvent(action=MouseAction.CLICK, x=500, y=500)) == SafetyDecision.ALLOW


class TestInputControllerCalibrate:
    def test_calibrate_without_pyautogui(self) -> None:
        controller = _make_dry_controller()
        info = controller.calibrate()
        assert "screen_width" in info
        assert "scale_factor" in info
        assert "is_retina" in info

    def test_calibrate_returns_dict_keys(self) -> None:
        controller = _make_dry_controller()
        info = controller.calibrate()
        for key in ("screen_width", "screen_height", "scale_factor", "is_retina"):
            assert key in info


class TestInputControllerSafeRegion:
    def test_set_safe_region(self) -> None:
        controller = _make_dry_controller()
        controller.set_safe_region(0, 0, 800, 600)
        assert controller._safe_region == (0, 0, 800, 600)
        assert controller._safety_gate.safe_region == (0, 0, 800, 600)

    def test_clear_safe_region(self) -> None:
        controller = _make_dry_controller()
        controller.set_safe_region(0, 0, 800, 600)
        controller.set_safe_region(0, 0, 0, 0)
        assert controller._safe_region is None
        assert controller._safety_gate.safe_region is None


class TestInputControllerRetry:
    def test_retry_succeeds_on_first_attempt(self) -> None:
        controller = _make_dry_controller(max_retries=3)
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=100)
        result = controller._execute_mouse(event)
        assert result.success is True

    def test_retry_with_mock_failure_then_success(self) -> None:
        controller = _make_mock_real_controller(max_retries=3, retry_delay_ms=10)
        call_count = [0]

        def failing_then_ok(event):
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("simulated failure")

        with patch.object(controller, "_do_mouse", side_effect=failing_then_ok):
            event = MouseEvent(action=MouseAction.CLICK, x=100, y=100)
            result = controller._execute_mouse(event)
            assert result.success is True
            assert call_count[0] == 3

    def test_retry_exhausted(self) -> None:
        controller = _make_mock_real_controller(max_retries=2, retry_delay_ms=10)
        with patch.object(controller, "_do_mouse", side_effect=RuntimeError("always fails")):
            event = MouseEvent(action=MouseAction.CLICK, x=100, y=100)
            result = controller._execute_mouse(event)
            assert result.success is False
            assert "retries" in result.error_message


class TestInputControllerRealMode:
    def test_enable_real_mode_without_pyautogui(self) -> None:
        controller = _make_dry_controller()
        result = controller.enable_real_mode()
        assert result is False

    def test_enable_real_mode_with_mock_pyautogui(self) -> None:
        pytest.importorskip("pyautogui", reason="pyautogui not installed")
        controller = _make_mock_real_controller()
        controller._dry_run = True
        controller._pyautogui_configured = False
        result = controller.enable_real_mode()
        assert result is True
        assert controller.dry_run is False

    def test_dry_run_setter_toggles(self) -> None:
        controller = _make_mock_real_controller()
        controller.dry_run = True
        controller.dry_run = False
        assert controller.dry_run is False


class TestInputControllerRateLimiting:
    def test_rate_limit_blocks_rapid_ops(self) -> None:
        """Test rate limiting through actual execution path.

        check_mouse is read-only; quota is consumed by _consume_rate_limit
        inside _execute_mouse. So we must test via InputController execution.
        """
        gate = _make_gate()
        results: list[SafetyDecision] = []
        for _ in range(20):
            decision = gate.check_mouse(MouseEvent(action=MouseAction.CLICK, x=10, y=10))
            results.append(decision)
            if decision != SafetyDecision.BLOCK:
                gate._consume_rate_limit("mouse")
        assert results[0] == SafetyDecision.ALLOW
        assert SafetyDecision.BLOCK in results[1:]

    def test_rate_limit_per_type_independent(self) -> None:
        mouse_gate = _make_gate()
        mouse_gate.check_mouse(MouseEvent(action=MouseAction.CLICK, x=10, y=10))
        mouse_gate._consume_rate_limit("mouse")
        kb_gate = _make_gate()
        result = kb_gate.check_keyboard(KeyboardEvent(action=KeyboardAction.TYPE, text="hello"))
        assert result == SafetyDecision.ALLOW


class TestOperationResultProperties:
    def test_operation_log_accumulates(self) -> None:
        controller = _make_dry_controller()
        controller.click(100, 200)
        controller.type_text("hello")
        assert len(controller.operation_log) == 2
        assert controller.operation_log[0].action_type == "click"
        assert controller.operation_log[1].action_type == "type"

    def test_blocked_operation_logged(self) -> None:
        controller = _make_dry_controller()
        controller._safety_gate.current_app = "Terminal"
        controller._safety_gate.block_list_apps = {"Terminal"}
        result = controller.click(100, 200)
        assert result.success is False
        assert result.safety_decision == SafetyDecision.BLOCK

    def test_safe_region_blocks_mouse(self) -> None:
        controller = _make_dry_controller()
        controller.set_safe_region(0, 0, 800, 600)
        result = controller.click(1200, 800)
        assert result.success is False
        assert result.safety_decision == SafetyDecision.BLOCK
