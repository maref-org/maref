"""D1 tests: environment setup + open source evaluation for desktop agent modules."""

from __future__ import annotations

import pytest
from PIL import Image

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
from maref.desktop.screen_capture import (
    CaptureMode,
    DownsampleMethod,
    RedactionEngine,
    RedactionMode,
    RedactionZone,
    ScreenCapture,
    ScreenshotResult,
)
from maref.desktop.screen_parser import (
    BoundingBox,
    InteractionType,
    OmniParserInterface,
    ParsedUIElement,
    ScreenParseResult,
    UIElementType,
)


class TestBoundingBox:
    def test_center_calculation(self):
        bbox = BoundingBox(x=100, y=200, width=50, height=50)
        assert bbox.center == (125, 225)

    def test_area(self):
        bbox = BoundingBox(x=0, y=0, width=100, height=200)
        assert bbox.area == 20000

    def test_overlap_true(self):
        a = BoundingBox(x=0, y=0, width=100, height=100)
        b = BoundingBox(x=50, y=50, width=100, height=100)
        assert a.overlaps(b)

    def test_overlap_false(self):
        a = BoundingBox(x=0, y=0, width=10, height=10)
        b = BoundingBox(x=100, y=100, width=10, height=10)
        assert not a.overlaps(b)

    def test_overlap_edge_touch(self):
        a = BoundingBox(x=0, y=0, width=50, height=50)
        b = BoundingBox(x=50, y=0, width=50, height=50)
        assert not a.overlaps(b)

    def test_to_dict(self):
        bbox = BoundingBox(x=10, y=20, width=30, height=40)
        d = bbox.to_dict()
        assert d == {"x": 10, "y": 20, "width": 30, "height": 40}


class TestParsedUIElement:
    def test_interactive_element(self):
        elem = ParsedUIElement(
            element_type=UIElementType.BUTTON,
            bbox=BoundingBox(0, 0, 100, 40),
            interaction_types=[InteractionType.CLICKABLE],
        )
        assert elem.is_interactive

    def test_non_interactive_element(self):
        elem = ParsedUIElement(
            element_type=UIElementType.LABEL,
            bbox=BoundingBox(0, 0, 100, 40),
            interaction_types=[],
        )
        assert not elem.is_interactive

    def test_to_dict(self):
        elem = ParsedUIElement(
            element_type=UIElementType.BUTTON,
            bbox=BoundingBox(x=10, y=20, width=100, height=40),
            text="Click Me",
            confidence=0.95,
            interaction_types=[InteractionType.CLICKABLE],
            element_id="btn_1",
        )
        d = elem.to_dict()
        assert d["element_type"] == "button"
        assert d["bbox"]["x"] == 10
        assert d["text"] == "Click Me"
        assert d["confidence"] == 0.95
        assert "clickable" in d["interaction_types"]
        assert d["element_id"] == "btn_1"


class TestScreenParseResult:
    def make_result(self):
        return ScreenParseResult(
            screen_width=1920,
            screen_height=1080,
            elements=[
                ParsedUIElement(
                    element_type=UIElementType.BUTTON,
                    bbox=BoundingBox(100, 200, 120, 40),
                    text="Submit",
                    interaction_types=[InteractionType.CLICKABLE],
                    element_id="btn_1",
                ),
                ParsedUIElement(
                    element_type=UIElementType.TEXT_FIELD,
                    bbox=BoundingBox(100, 100, 300, 30),
                    text="Name",
                    interaction_types=[InteractionType.TYPABLE],
                    element_id="txt_1",
                ),
                ParsedUIElement(
                    element_type=UIElementType.LABEL,
                    bbox=BoundingBox(10, 10, 80, 20),
                    text="Title",
                    interaction_types=[],
                    element_id="lbl_1",
                ),
            ],
        )

    def test_find_by_type(self):
        result = self.make_result()
        buttons = result.find_elements_by_type(UIElementType.BUTTON)
        assert len(buttons) == 1
        assert buttons[0].element_id == "btn_1"

    def test_find_by_text_case_insensitive(self):
        result = self.make_result()
        found = result.find_elements_by_text("submit")
        assert len(found) == 1
        assert found[0].element_id == "btn_1"

    def test_find_by_text_case_sensitive_miss(self):
        result = self.make_result()
        found = result.find_elements_by_text("submit", case_sensitive=True)
        assert len(found) == 0

    def test_find_by_text_case_sensitive_hit(self):
        result = self.make_result()
        found = result.find_elements_by_text("Submit", case_sensitive=True)
        assert len(found) == 1

    def test_find_by_id(self):
        result = self.make_result()
        elem = result.find_element_by_id("txt_1")
        assert elem is not None
        assert elem.element_type == UIElementType.TEXT_FIELD

    def test_find_by_id_missing(self):
        result = self.make_result()
        assert result.find_element_by_id("nonexistent") is None

    def test_find_interactive(self):
        result = self.make_result()
        interactive = result.find_interactive_elements()
        assert len(interactive) == 2
        assert all(e.is_interactive for e in interactive)

    def test_to_dict(self):
        result = self.make_result()
        d = result.to_dict()
        assert d["screen_width"] == 1920
        assert d["screen_height"] == 1080
        assert len(d["elements"]) == 3


class TestOmniParserInterface:
    def test_default_backend_is_auto(self):
        parser = OmniParserInterface()
        assert parser.backend == "auto"
        assert not parser.initialized

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="Unsupported backend"):
            OmniParserInterface(backend="invalid_backend")

    def test_mock_initialize(self):
        parser = OmniParserInterface(backend="mock")
        assert parser.initialize()
        assert parser.initialized

    def test_mock_parse(self):
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("fake_path.png")
        assert isinstance(result, ScreenParseResult)
        assert len(result.elements) == 3
        assert result.parse_time_ms >= 0

    def test_mock_parse_element_types(self):
        parser = OmniParserInterface(backend="mock")
        parser.initialize()
        result = parser.parse("fake.png")
        types = {e.element_type for e in result.elements}
        assert UIElementType.BUTTON in types
        assert UIElementType.TEXT_FIELD in types
        assert UIElementType.CHECKBOX in types

    def test_parse_without_init_raises(self):
        parser = OmniParserInterface(backend="mock")
        with pytest.raises(RuntimeError, match="not initialized"):
            parser.parse("fake.png")

    def test_real_backend_init_graceful_fail(self):
        parser = OmniParserInterface(backend="omni_parser")
        assert not parser.initialize()


class TestInputSafetyGate:
    def test_mouse_click_allowed(self):
        gate = InputSafetyGate()
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.ALLOW

    def test_mouse_blocked_on_restricted_app(self):
        gate = InputSafetyGate(current_app="Terminal")
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.BLOCK

    def test_mouse_blocked_on_system_settings(self):
        gate = InputSafetyGate(current_app="System Settings")
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=200)
        assert gate.check_mouse(event) == SafetyDecision.BLOCK

    def test_keyboard_sensitive_hotkey_asks_user(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "shift", "q"])
        assert gate.check_keyboard(event) == SafetyDecision.ASK_USER

    def test_keyboard_normal_hotkey_allowed(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "c"])
        assert gate.check_keyboard(event) == SafetyDecision.ALLOW

    def test_keyboard_rm_rf_blocked(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="rm -rf /")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK

    def test_keyboard_sudo_blocked(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="sudo something")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK

    def test_keyboard_drop_table_blocked(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="DROP TABLE users")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK

    def test_keyboard_safe_text_allowed(self):
        gate = InputSafetyGate()
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="Hello World")
        assert gate.check_keyboard(event) == SafetyDecision.ALLOW

    def test_update_current_app(self):
        gate = InputSafetyGate(current_app="Safari")
        assert gate.current_app == "Safari"
        gate.update_current_app("Terminal")
        assert gate.current_app == "Terminal"

    def test_keyboard_blocked_on_restricted_app(self):
        gate = InputSafetyGate(current_app="Keychain Access")
        event = KeyboardEvent(action=KeyboardAction.TYPE, text="hello")
        assert gate.check_keyboard(event) == SafetyDecision.BLOCK


class TestInputController:
    def test_init_defaults(self):
        controller = InputController()
        assert controller.dry_run is True
        assert len(controller.operation_log) == 0

    def test_click_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.click(100, 200)
        assert result.success
        assert result.action_type == "click"
        assert result.safety_decision == SafetyDecision.ALLOW
        assert len(controller.operation_log) == 1

    def test_double_click_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.double_click(100, 200)
        assert result.success
        assert result.action_type == "double_click"

    def test_right_click_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.right_click(100, 200)
        assert result.success
        assert result.action_type == "right_click"

    def test_drag_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.drag(0, 0, 100, 100)
        assert result.success
        assert result.action_type == "drag"

    def test_move_to_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.move_to(100, 200)
        assert result.success

    def test_scroll_up_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.scroll(3)
        assert result.success
        assert result.action_type == "scroll_up"

    def test_scroll_down_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.scroll(-5)
        assert result.success
        assert result.action_type == "scroll_down"

    def test_type_text_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.type_text("hello")
        assert result.success
        assert result.action_type == "type"

    def test_press_key_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.press_key("enter")
        assert result.success

    def test_hotkey_dry_run(self):
        controller = InputController(dry_run=True)
        result = controller.hotkey("command", "c")
        assert result.success

    def test_click_blocked_on_restricted_app(self):
        gate = InputSafetyGate(current_app="Terminal")
        controller = InputController(safety_gate=gate, dry_run=True)
        result = controller.click(100, 200)
        assert not result.success
        assert result.safety_decision == SafetyDecision.BLOCK

    def test_type_dangerous_text_blocked(self):
        controller = InputController(dry_run=True)
        result = controller.type_text("rm -rf /")
        assert not result.success
        assert result.safety_decision == SafetyDecision.BLOCK

    def test_hotkey_logout_asks_user(self):
        controller = InputController(dry_run=True)
        result = controller.hotkey("command", "shift", "q")
        assert result.safety_decision == SafetyDecision.ASK_USER

    def test_operation_log_accumulates(self):
        controller = InputController(dry_run=True)
        controller.click(0, 0)
        controller.click(1, 1)
        controller.type_text("hi")
        assert len(controller.operation_log) == 3

    def test_dry_run_toggle(self):
        controller = InputController(dry_run=True)
        assert controller.dry_run
        controller.dry_run = False
        assert not controller.dry_run


class TestRedactionEngine:
    def test_empty_by_default(self):
        engine = RedactionEngine()
        img = Image.new("RGB", (100, 100), color="white")
        result = engine.redact(img)
        assert result.size == (100, 100)

    def test_add_and_apply_zone(self):
        engine = RedactionEngine()
        engine.add_zone(RedactionZone(x=0, y=0, width=50, height=50, mode=RedactionMode.BLACK_BOX))
        img = Image.new("RGB", (100, 100), color="white")
        result = engine.redact(img)
        pixel = result.getpixel((10, 10))
        assert pixel == (0, 0, 0)

    def test_blur_zone(self):
        engine = RedactionEngine()
        engine.add_zone(RedactionZone(x=0, y=0, width=100, height=100, mode=RedactionMode.BLUR))
        img = Image.new("RGB", (100, 100), color="white")
        result = engine.redact(img)
        assert result.size == (100, 100)

    def test_pixelate_zone(self):
        engine = RedactionEngine()
        engine.add_zone(RedactionZone(x=0, y=0, width=64, height=64, mode=RedactionMode.PIXELATE))
        img = Image.new("RGB", (64, 64), color=(255, 0, 0))
        result = engine.redact(img)
        assert result.size == (64, 64)

    def test_clear_zones(self):
        engine = RedactionEngine()
        engine.add_zone(RedactionZone(x=0, y=0, width=10, height=10))
        engine.clear_zones()
        img = Image.new("RGB", (100, 100), color="white")
        result = engine.redact(img)
        pixel = result.getpixel((5, 5))
        assert pixel == (255, 255, 255)

    def test_sensitive_pattern_detection(self):
        engine = RedactionEngine(auto_detect=True)
        elements = [
            {"text": "password_field", "bbox": {"x": 10, "y": 20, "width": 200, "height": 30}},
            {"text": "username", "bbox": {"x": 10, "y": 60, "width": 200, "height": 30}},
        ]
        zones = engine._detect_sensitive_zones(elements)
        assert len(zones) == 1
        assert zones[0].x == 10
        assert zones[0].y == 20
        assert "password" in zones[0].reason

    def test_no_sensitive_pattern(self):
        engine = RedactionEngine(auto_detect=True)
        elements = [
            {"text": "username", "bbox": {"x": 10, "y": 60, "width": 200, "height": 30}},
            {"text": "email", "bbox": {"x": 10, "y": 100, "width": 200, "height": 30}},
        ]
        zones = engine._detect_sensitive_zones(elements)
        assert len(zones) == 0


class TestScreenCapture:
    def test_init_defaults(self):
        capture = ScreenCapture()
        assert capture.downsample_factor == 1.0
        assert capture.downsample_method == DownsampleMethod.NONE

    def test_init_invalid_frame_factor(self):
        with pytest.raises(ValueError, match="between 0.1 and 1.0"):
            ScreenCapture(downsample_factor=0.05)

    def test_init_invalid_high_factor(self):
        with pytest.raises(ValueError, match="between 0.1 and 1.0"):
            ScreenCapture(downsample_factor=1.5)

    def test_capture_fullscreen_fallback(self):
        capture = ScreenCapture()
        result = capture.capture_fullscreen()
        assert isinstance(result, ScreenshotResult)
        assert result.mode == CaptureMode.FULL_SCREEN

    def test_capture_region(self):
        capture = ScreenCapture()
        result = capture.capture_region(0, 0, 100, 100)
        assert isinstance(result, ScreenshotResult)
        assert result.mode == CaptureMode.REGION

    def test_capture_active_window(self):
        capture = ScreenCapture()
        result = capture.capture_active_window()
        assert isinstance(result, ScreenshotResult)
        assert result.mode == CaptureMode.ACTIVE_WINDOW

    def test_screenshot_result_save(self):
        import os
        import tempfile

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="blue")
        result = ScreenshotResult(image=img, width=100, height=100)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            saved = result.save(path)
            assert saved == path
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_screenshot_result_save_no_image(self):
        result = ScreenshotResult()
        with pytest.raises(ValueError, match="No image data"):
            result.save("/tmp/test.png")

    def test_screenshot_result_to_bytes(self):
        img = Image.new("RGB", (10, 10), color="red")
        result = ScreenshotResult(image=img)
        data = result.to_bytes()
        assert len(data) > 0
        assert isinstance(data, bytes)

    def test_downsample_bilinear(self):
        capture = ScreenCapture(
            downsample_method=DownsampleMethod.BILINEAR,
            downsample_factor=0.5,
        )
        result = capture.capture_fullscreen()
        if result.image:
            assert result.image.size[0] <= result.width

    def test_downsample_lanczos(self):
        capture = ScreenCapture(
            downsample_method=DownsampleMethod.LANCZOS,
            downsample_factor=0.25,
        )
        result = capture.capture_fullscreen()
        if result.image:
            assert result.image.size[0] <= result.width


class TestRedactionZone:
    def test_region_property(self):
        zone = RedactionZone(x=10, y=20, width=100, height=50)
        assert zone.region == (10, 20, 110, 70)

    def test_default_mode(self):
        zone = RedactionZone(x=0, y=0, width=10, height=10)
        assert zone.mode == RedactionMode.BLACK_BOX


class TestEventToDict:
    def test_mouse_event_to_dict(self):
        event = MouseEvent(action=MouseAction.DRAG, x=10, y=20, dx=30, dy=40, duration=0.5)
        d = event.to_dict()
        assert d["action"] == "drag"
        assert d["x"] == 10
        assert d["dx"] == 30
        assert d["dy"] == 40
        assert d["duration"] == 0.5

    def test_keyboard_event_to_dict(self):
        event = KeyboardEvent(action=KeyboardAction.HOTKEY, keys=["command", "c"])
        d = event.to_dict()
        assert d["action"] == "hotkey"
        assert d["keys"] == ["command", "c"]

    def test_operation_result_to_dict(self):
        result = OperationResult(
            success=False,
            action_type="click",
            details="Blocked",
            safety_decision=SafetyDecision.BLOCK,
            error_message="dangerous",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["safety_decision"] == "block"
        assert d["error_message"] == "dangerous"


class TestOmniParserBackendEnum:
    def test_supported_backends(self):
        assert "mock" in OmniParserInterface.SUPPORTED_BACKENDS
        assert "omni_parser" in OmniParserInterface.SUPPORTED_BACKENDS
        assert "cog_agent" in OmniParserInterface.SUPPORTED_BACKENDS
        assert "auto" in OmniParserInterface.SUPPORTED_BACKENDS
        assert len(OmniParserInterface.SUPPORTED_BACKENDS) == 5

    def test_cog_agent_graceful_init_fail(self):
        parser = OmniParserInterface(backend="cog_agent")
        assert not parser.initialize()
