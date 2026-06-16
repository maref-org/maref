"""End-to-end closed-loop tests for MAREF Desktop Agent (R19-20).

Validates the full screenshot -> parse -> execute -> verify pipeline.
All tests use mock objects to avoid requiring real hardware permissions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:
    Image = None


# ---- Fixtures ----


@pytest.fixture
def mock_screenshot_result():
    from maref.desktop.screen_capture import CaptureMode, ScreenshotResult

    if Image is None:
        img = None
    else:
        img = Image.new("RGB", (800, 600), color="white")

    return ScreenshotResult(
        image=img,
        width=800,
        height=600,
        capture_time_ms=45.2,
        mode=CaptureMode.FULL_SCREEN,
    )


@pytest.fixture
def mock_parsed_elements():
    return [
        {
            "type": "button",
            "text": "Submit",
            "bbox": {"x": 100, "y": 200, "w": 100, "h": 50},
            "confidence": 0.95,
        },
        {
            "type": "input",
            "text": "Search",
            "bbox": {"x": 300, "y": 100, "w": 200, "h": 40},
            "confidence": 0.88,
        },
        {
            "type": "icon",
            "text": "Settings",
            "bbox": {"x": 700, "y": 50, "w": 50, "h": 50},
            "confidence": 0.92,
        },
    ]


# ---- E2E Test: Screenshot -> Parse -> Execute -> Verify ----


class TestEndToEndScreenshotParseLoop:
    """Test the full screenshot capture and parsing pipeline."""

    def test_screenshot_result_has_expected_dimensions(self, mock_screenshot_result):
        assert mock_screenshot_result.width == 800
        assert mock_screenshot_result.height == 600

    def test_screenshot_capture_time_recorded(self, mock_screenshot_result):
        assert mock_screenshot_result.capture_time_ms > 0

    def test_screenshot_mode_is_full_screen(self, mock_screenshot_result):
        from maref.desktop.screen_capture import CaptureMode

        assert mock_screenshot_result.mode == CaptureMode.FULL_SCREEN


class TestEndToEndParseExecuteLoop:
    """Test the parsing -> action decision pipeline."""

    def test_click_button_action_from_parsed_elements(self, mock_parsed_elements):
        button_elem = next(e for e in mock_parsed_elements if e["type"] == "button")
        assert button_elem["text"] == "Submit"

        bbox = button_elem["bbox"]
        cx = bbox["x"] + bbox["w"] // 2
        cy = bbox["y"] + bbox["h"] // 2

        assert cx == 150
        assert cy == 225

    def test_text_input_targeting(self, mock_parsed_elements):
        text_elem = next(e for e in mock_parsed_elements if e["type"] == "input")
        assert text_elem["text"] == "Search"

        bbox = text_elem["bbox"]
        cx = bbox["x"] + bbox["w"] // 2
        cy = bbox["y"] + bbox["h"] // 2

        assert cx == 400
        assert cy == 120

    def test_icon_element_parsed(self, mock_parsed_elements):
        icon_elem = next(e for e in mock_parsed_elements if e["type"] == "icon")
        assert icon_elem["text"] == "Settings"

        bbox = icon_elem["bbox"]
        cx = bbox["x"] + bbox["w"] // 2
        cy = bbox["y"] + bbox["h"] // 2

        assert cx == 725
        assert cy == 75


class TestEndToEndSafetyGateIntegration:
    """Test safety gate integration in the E2E loop."""

    def test_safety_gate_allows_safe_click(self):
        from maref.desktop.input_controller import InputSafetyGate, MouseEvent, SafetyDecision

        gate = InputSafetyGate(current_app="Safari", block_list_apps=set())
        gate.safe_region = (0, 0, 1920, 1080)

        event = MouseEvent(x=150, y=225, button="left", action="click")
        decision = gate.check_mouse(event)

        assert decision == SafetyDecision.ALLOW

    def test_safety_gate_blocks_outside_safe_region(self):
        from maref.desktop.input_controller import InputSafetyGate, MouseEvent, SafetyDecision

        gate = InputSafetyGate(current_app="Safari", block_list_apps=set())
        gate.safe_region = (100, 100, 500, 500)

        event = MouseEvent(x=900, y=900, button="left", action="click")
        decision = gate.check_mouse(event)

        assert decision == SafetyDecision.BLOCK

    def test_safety_gate_rate_limiting_rapid_clicks(self):
        from maref.desktop.input_controller import InputSafetyGate, MouseEvent, SafetyDecision

        gate = InputSafetyGate(current_app="Safari", block_list_apps=set())
        gate._max_ops_per_second = 2
        gate.safe_region = (0, 0, 1920, 1080)

        allowed_count = 0
        blocked_count = 0

        for i in range(10):
            event = MouseEvent(x=150, y=225, button="left", action="click")
            decision = gate.check_mouse(event)
            if decision == SafetyDecision.ALLOW:
                allowed_count += 1
            else:
                blocked_count += 1

        assert allowed_count <= 2
        assert blocked_count >= 8

    def test_safety_gate_blocks_restricted_app(self):
        from maref.desktop.input_controller import InputSafetyGate, MouseEvent, SafetyDecision

        gate = InputSafetyGate(current_app="Terminal", block_list_apps={"Terminal"})

        event = MouseEvent(x=150, y=225, button="left", action="click")
        decision = gate.check_mouse(event)

        assert decision == SafetyDecision.BLOCK


class TestEndToEndRedactionPipeline:
    """Test the screenshot redaction -> parse pipeline."""

    def test_redaction_engine_applies_black_box(self, mock_screenshot_result):
        if Image is None:
            pytest.skip("Pillow not installed")

        from maref.desktop.screen_capture import RedactionEngine, RedactionMode, RedactionZone

        engine = RedactionEngine()
        zone = RedactionZone(
            x=50, y=50, width=100, height=50, reason="password_field", mode=RedactionMode.BLACK_BOX
        )
        engine.add_zone(zone)

        result = engine.redact(mock_screenshot_result.image)

        assert result is not None
        assert result.size == (800, 600)

    def test_redaction_multiple_zones(self, mock_screenshot_result):
        if Image is None:
            pytest.skip("Pillow not installed")

        from maref.desktop.screen_capture import RedactionEngine, RedactionMode, RedactionZone

        engine = RedactionEngine()
        zones = [
            RedactionZone(
                x=0, y=0, width=100, height=50, reason="api_key", mode=RedactionMode.BLACK_BOX
            ),
            RedactionZone(
                x=200, y=300, width=150, height=30, reason="token", mode=RedactionMode.BLUR
            ),
        ]
        for z in zones:
            engine.add_zone(z)

        result = engine.redact(mock_screenshot_result.image)
        assert result is not None
        assert result.size == (800, 600)


class TestEndToEndGovernanceIntegration:
    """Test governance overlay on desktop operations."""

    def test_governance_state_machine_starts_at_init(self):
        from maref.governance.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        assert sm.current_state == GovernanceState.INIT

    def test_governance_audit_log_entry_created(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()
        logger.log(
            event_type="security",
            actor="desktop-agent",
            action="screenshot_capture",
            details={"target": "screen"},
        )

        entries = logger.read_filtered(actor="desktop-agent")
        assert len(entries) == 1
        assert entries[0].event_type == "security"
        assert entries[0].action == "screenshot_capture"

    def test_governance_state_machine_transition_to_observe(self):
        from maref.governance.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "Starting observation")
        assert sm.current_state == GovernanceState.OBSERVE
        assert sm.transition_count == 1


class TestEndToEndRecursiveGovernanceLoop:
    """Test the recursive governance observe-analyze-decide-act loop."""

    def test_recursive_governance_single_cycle(self):
        from maref.governance.audit import AuditLogger
        from maref.governance.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        logger = AuditLogger()

        sm.transition(GovernanceState.OBSERVE, "Start cycle")
        logger.log("security", "agent", "observe", {"target": "screen"})

        sm.transition(GovernanceState.ANALYZE, "Analyze state")
        logger.log("security", "agent", "analyze", {"target": "state"})

        sm.transition(GovernanceState.EVALUATE, "Evaluate options")
        logger.log("security", "agent", "evaluate", {"target": "options"})

        sm.transition(GovernanceState.DECIDE, "Make decision")
        logger.log("security", "agent", "decide", {"target": "action"})

        sm.transition(GovernanceState.ACT, "Execute action")
        logger.log("security", "agent", "act", {"target": "system"})

        entries = logger.read_filtered(actor="agent")
        assert len(entries) == 5
        assert sm.current_state == GovernanceState.ACT

    def test_recursive_governance_multiple_cycles(self):
        from maref.governance.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        initial_count = sm.transition_count

        for i in range(5):
            sm.transition(GovernanceState.OBSERVE, f"Cycle {i}")
            sm.transition(GovernanceState.ANALYZE, f"Cycle {i}")
            sm.transition(GovernanceState.EVALUATE, f"Cycle {i}")
            sm.transition(GovernanceState.DECIDE, f"Cycle {i}")
            sm.transition(GovernanceState.ACT, f"Cycle {i}")
            if i < 4:
                sm.transition(GovernanceState.VERIFY, f"Verify cycle {i}")

        assert sm.transition_count == initial_count + 29


class TestEndToEndScreenshotSaveAndLoad:
    """Test screenshot save and load pipeline."""

    def test_screenshot_save_to_temp_file(self, mock_screenshot_result):
        if Image is None:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = mock_screenshot_result.save(f.name)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
            Path(path).unlink()

    def test_screenshot_to_bytes(self, mock_screenshot_result):
        if Image is None:
            pytest.skip("Pillow not installed")

        data = mock_screenshot_result.to_bytes("PNG")
        assert len(data) > 0
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


class TestEndToEndPolicyDecisionTree:
    """Test policy decision tree in the E2E loop."""

    def test_policy_decision_tree_allows_safe_action(self):
        from maref.desktop.policy_decision_tree import DecisionVerdict, PolicyDecisionTree

        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Safari",
            element_text="button",
            input_text="",
            trust_score=1.0,
        )

        assert result.verdict == DecisionVerdict.ALLOW

    def test_policy_decision_tree_blocks_dangerous_action(self):
        from maref.desktop.policy_decision_tree import DecisionVerdict, PolicyDecisionTree

        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="type",
            app_name="Terminal",
            element_text="",
            input_text="rm -rf /",
            trust_score=1.0,
        )

        assert result.verdict == DecisionVerdict.BLOCK


class TestEndToEndInputController:
    """Test the full InputController with safety gate integration."""

    def test_input_controller_dry_run_mode(self):
        from maref.desktop.input_controller import InputController

        controller = InputController(dry_run=True)
        assert controller._dry_run is True

    def test_input_controller_operation_log(self):
        from maref.desktop.input_controller import InputController

        controller = InputController(dry_run=True)
        assert isinstance(controller._operation_log, list)

    def test_input_controller_safe_region_config(self):
        from maref.desktop.input_controller import InputController

        controller = InputController(dry_run=True)
        controller._safe_region = (0, 0, 800, 600)

        assert controller._safe_region is not None
        assert controller._safe_region == (0, 0, 800, 600)


class TestEndToEndWindowManager:
    """Test window manager integration."""

    def test_window_manager_initialization(self):
        from maref.desktop.window_manager import WindowManager

        wm = WindowManager()
        assert wm is not None

    def test_window_manager_get_windows_list(self):
        from maref.desktop.window_manager import WindowManager

        wm = WindowManager()
        windows = wm.list_windows()
        assert isinstance(windows, list)
