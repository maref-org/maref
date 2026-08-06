from __future__ import annotations

from maref.desktop.input_controller import (
    InputController,
    InputSafetyGate,
    KeyboardAction,
    KeyboardEvent,
    MouseAction,
    MouseEvent,
    OperationResult,
    SafetyDecision,
)


class TestMouseEvent:
    def test_to_dict(self) -> None:
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        d = event.to_dict()
        assert d["action"] == "click"
        assert d["x"] == 100


class TestKeyboardEvent:
    def test_to_dict(self) -> None:
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "c"])
        d = event.to_dict()
        assert d["action"] == "hotkey"
        assert d["keys"] == ["command", "c"]


class TestOperationResult:
    def test_to_dict(self) -> None:
        result = OperationResult(
            success=True,
            action_type="click",
            details="Clicked at (100, 200)",
            duration_ms=50.0,
            safety_decision=SafetyDecision.ALLOW,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["action_type"] == "click"
        assert d["safety_decision"] == "allow"


class TestInputSafetyGate:
    def test_check_mouse_blocked_in_restricted_app(self) -> None:
        gate = InputSafetyGate(current_app="Terminal")
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.BLOCK

    def test_check_mouse_allowed_in_normal_app(self) -> None:
        gate = InputSafetyGate(current_app="Finder")
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.ALLOW

    def test_check_mouse_blocked_outside_safe_region(self) -> None:
        gate = InputSafetyGate()
        gate.safe_region = (0, 0, 100, 100)
        event = MouseEvent(action=MouseAction.CLICK, x=200, y=200)
        assert gate.check_mouse(event) == SafetyDecision.BLOCK

    def test_check_mouse_allowed_inside_safe_region(self) -> None:
        gate = InputSafetyGate()
        gate.safe_region = (0, 0, 200, 200)
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=100)
        assert gate.check_mouse(event) == SafetyDecision.ALLOW

    def test_check_keyboard_blocked_in_restricted_app(self) -> None:
        gate = InputSafetyGate(current_app="System Settings")
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="hello")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK

    def test_check_keyboard_sensitive_hotkey_asks_user(self) -> None:
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "shift", "q"])
        assert gate.check_keyboard(event) == SafetyDecision.ASK_USER

    def test_check_keyboard_normal_hotkey_allowed(self) -> None:
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "c"])
        assert gate.check_keyboard(event) == SafetyDecision.ALLOW

    def test_check_keyboard_blocked_text_pattern(self) -> None:
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="sudo rm -rf /")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK

    def test_check_keyboard_normal_text_allowed(self) -> None:
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="hello world")
        assert gate.check_keyboard(event) == SafetyDecision.ALLOW

    def test_update_current_app(self) -> None:
        gate = InputSafetyGate()
        gate.update_current_app("Safari")
        assert gate.current_app == "Safari"


class TestInputController:
    def test_dry_run_default(self) -> None:
        ctrl = InputController()
        assert ctrl.dry_run

    def test_click_in_dry_run(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.click(100, 200)
        assert result.success
        assert result.action_type == "click"

    def test_click_in_blocked_app(self) -> None:
        gate = InputSafetyGate(current_app="Terminal")
        ctrl = InputController(safety_gate=gate, dry_run=True)
        result = ctrl.click(100, 200)
        assert not result.success
        assert result.safety_decision == SafetyDecision.BLOCK

    def test_double_click_in_dry_run(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.double_click(100, 200)
        assert result.success

    def test_right_click(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.right_click(100, 200)
        assert result.success

    def test_type_text(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.type_text("hello")
        assert result.success

    def test_type_text_blocked_pattern(self) -> None:
        gate = InputSafetyGate()
        ctrl = InputController(safety_gate=gate, dry_run=True)
        result = ctrl.type_text("sudo rm -rf /")
        assert not result.success

    def test_hotkey(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.hotkey("command", "c")
        assert result.success

    def test_hotkey_asks_user(self) -> None:
        gate = InputSafetyGate()
        ctrl = InputController(safety_gate=gate, dry_run=True)
        result = ctrl.hotkey("command", "shift", "q")
        assert result.success

    def test_scroll_positive(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.scroll(5)
        assert result.success

    def test_scroll_negative(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.scroll(-3)
        assert result.success

    def test_drag(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.drag(0, 0, 100, 100)
        assert result.success

    def test_move_to(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.move_to(100, 200)
        assert result.success

    def test_press_key(self) -> None:
        ctrl = InputController(dry_run=True)
        result = ctrl.press_key("enter")
        assert result.success

    def test_set_safe_region(self) -> None:
        ctrl = InputController(dry_run=True)
        ctrl.set_safe_region(0, 0, 100, 100)
        assert ctrl._safe_region is not None

    def test_clear_safe_region(self) -> None:
        ctrl = InputController(dry_run=True)
        ctrl.set_safe_region(0, 0, 0, 0)
        assert ctrl._safe_region is None

    def test_operation_log(self) -> None:
        ctrl = InputController(dry_run=True)
        ctrl.click(100, 200)
        ctrl.type_text("hello")
        assert len(ctrl.operation_log) == 2

    def test_enable_real_mode_no_pyautogui(self) -> None:
        ctrl = InputController(dry_run=True)
        ctrl._pyautogui_available = False
        result = ctrl.enable_real_mode()
        assert not result

    def test_check_permissions(self) -> None:
        ctrl = InputController(dry_run=True)
        perms = ctrl.check_permissions()
        assert "pyautogui" in perms

    def test_calibrate(self) -> None:
        ctrl = InputController(dry_run=True)
        info = ctrl.calibrate()
        assert "screen_width" in info
        assert "scale_factor" in info

    def test_pyautogui_available_property(self) -> None:
        ctrl = InputController(dry_run=True)
        assert isinstance(ctrl.pyautogui_available, bool)
