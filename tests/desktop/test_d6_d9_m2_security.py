"""D6-D9 tests: M2 safety gate, policy decision tree, desktop governance, action recorder."""

from __future__ import annotations

import tempfile

from maref.desktop.action_recorder import (
    ActionRecorder,
    ActionRecording,
    RecordedActionType,
    RecordedStep,
)
from maref.desktop.desktop_governance import (
    DesktopGovernance,
    DesktopGovernanceState,
    GovernanceAction,
    GovernanceEvent,
)
from maref.desktop.policy_decision_tree import (
    DecisionLevel,
    DecisionResult,
    DecisionVerdict,
    OperationMode,
    PolicyDecisionTree,
)
from maref.desktop.safety_gate_desktop import (
    DesktopSafetyGateV2,
    DesktopThreatAssessment,
    DesktopThreatCategory,
    DesktopThreatSeverity,
)


class TestDesktopSafetyGateV2:
    def test_init(self):
        gate = DesktopSafetyGateV2()
        assert not gate.is_locked
        assert gate.consecutive_failures == 0

    def test_assess_safe_ui(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Click here to continue")
        assert not result.threat_detected
        assert not result.blocked

    def test_assess_delete_button(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Delete File")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.HIGH
        assert result.requires_confirmation
        assert not result.blocked

    def test_assess_format_button(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Format Disk")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.CRITICAL
        assert result.blocked

    def test_assess_shutdown_button(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Shut Down Computer")
        assert result.threat_detected
        assert result.blocked

    def test_assess_purchase_button(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Purchase Now")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.MEDIUM
        assert result.requires_confirmation

    def test_assess_install_button(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("Install Application")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.HIGH

    def test_assess_rate_limit(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_rate()
        assert not result.threat_detected

    def test_assess_app_boundary_allowed(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Finder", {"Finder", "Safari"})
        assert not result.threat_detected

    def test_assess_app_boundary_blocked(self):
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Terminal", {"Finder", "Safari"})
        assert result.threat_detected
        assert result.blocked

    def test_record_success_resets_failures(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "button", False)
        gate.record_operation("click", "button", False)
        assert gate.consecutive_failures == 2
        gate.record_operation("click", "button", True)
        assert gate.consecutive_failures == 0

    def test_three_failures_lock(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", False)
        assert gate.is_locked
        assert gate.consecutive_failures == 3

    def test_should_block_when_locked(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", False)
        result = gate.should_block_operation("OK", "Finder", {"Finder"})
        assert result.blocked
        assert result.severity == DesktopThreatSeverity.CRITICAL

    def test_basic_should_block_operation(self):
        gate = DesktopSafetyGateV2()
        result = gate.should_block_operation("Delete All", "Terminal", {"Finder"})
        assert result.blocked

    def test_reset_failure_count(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", False)
        gate.reset_failure_count()
        assert gate.consecutive_failures == 0

    def test_operation_history(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "btn1", True)
        gate.record_operation("type", "hello", True)
        history = gate.get_operation_history()
        assert len(history) == 2

    def test_to_dict(self):
        assessment = DesktopThreatAssessment(
            threat_detected=True,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.HIGH,
            description="Danger!",
            blocked=False,
            requires_confirmation=True,
        )
        d = assessment.to_dict()
        assert d["threat_detected"] is True
        assert d["severity"] == "high"
        assert d["requires_confirmation"] is True


class TestPolicyDecisionTree:
    def test_init_default_mode(self):
        tree = PolicyDecisionTree()
        assert tree.mode == OperationMode.SEMI_AUTO

    def test_set_mode(self):
        tree = PolicyDecisionTree()
        tree.set_mode(OperationMode.FULL_AUTO)
        assert tree.mode == OperationMode.FULL_AUTO

    def test_rule_block_dangerous_system_app(self):
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Terminal",
            element_text="OK",
        )
        assert result.verdict == DecisionVerdict.BLOCK
        assert result.level == DecisionLevel.RULE_BASED

    def test_rule_block_dangerous_command(self):
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="type",
            app_name="Finder",
            input_text="rm -rf /",
        )
        assert result.verdict == DecisionVerdict.BLOCK

    def test_rule_allow_safe_app_click(self):
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Documents",
        )
        assert result.verdict in (DecisionVerdict.ALLOW, DecisionVerdict.ASK_USER)

    def test_ask_mode_always_asks(self):
        tree = PolicyDecisionTree(mode=OperationMode.ASK_MODE)
        result = tree.evaluate(operation="click", app_name="Finder", element_text="OK")
        assert result.verdict == DecisionVerdict.ASK_USER
        assert result.level == DecisionLevel.MODE_BASED

    def test_delete_requires_confirmation(self):
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Delete File",
        )
        assert result.verdict in (DecisionVerdict.ASK_USER, DecisionVerdict.BLOCK)

    def test_format_is_blocked(self):
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Format Disk",
        )
        assert result.verdict == DecisionVerdict.BLOCK

    def test_safe_click_allowed_full_auto(self):
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Open Folder",
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.ALLOW

    def test_low_trust_escalates(self):
        tree = PolicyDecisionTree(trust_score_threshold=0.7)
        tree.set_mode(OperationMode.SEMI_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Open",
            trust_score=0.3,
            safe_apps={"Finder"},
        )
        assert result.verdict == DecisionVerdict.ASK_USER

    def test_decision_log(self):
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Finder", element_text="OK")
        tree.evaluate(operation="click", app_name="Terminal", element_text="OK")
        assert len(tree.get_decision_log()) == 2

    def test_level_distribution(self):
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Terminal", element_text="OK")
        tree.evaluate(operation="click", app_name="Finder", element_text="OK")
        dist = tree.get_level_distribution()
        assert "rule_based" in dist
        assert sum(dist.values()) == 2

    def test_decision_result_to_dict(self):
        result = DecisionResult(
            verdict=DecisionVerdict.ALLOW,
            level=DecisionLevel.RULE_BASED,
            reason="Safe operation",
        )
        d = result.to_dict()
        assert d["verdict"] == "allow"
        assert d["level"] == "rule_based"


class TestDesktopGovernance:
    def test_init_healthy(self):
        gov = DesktopGovernance()
        assert gov.state == DesktopGovernanceState.HEALTHY
        assert gov.is_healthy

    def test_record_success(self):
        gov = DesktopGovernance()
        gov.record_operation_result(True, "click", "btn")
        assert gov.is_healthy

    def test_three_failures_triggers_circuit_break(self):
        gov = DesktopGovernance()
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        assert gov.state == DesktopGovernanceState.LOCKED
        assert not gov.is_healthy
        assert gov.event_log[-1].action == GovernanceAction.CIRCUIT_BREAK

    def test_success_after_lock_restores(self):
        gov = DesktopGovernance()
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        assert gov.state == DesktopGovernanceState.LOCKED
        gov.record_operation_result(True, "click", "btn")
        assert gov.state == DesktopGovernanceState.RECOVERING

    def test_detect_oscillation(self):
        gov = DesktopGovernance()
        for i in range(5):
            gov.detect_oscillation(f"hash_{i}")
        for i in range(5):
            gov.detect_oscillation(f"hash_{i+5}")
        assert gov.state == DesktopGovernanceState.OSCILLATING

    def test_detect_drift(self):
        gov = DesktopGovernance()
        result = gov.detect_drift({"btn_1", "txt_1"}, {"txt_1"})
        assert not result
        result = gov.detect_drift({"btn_1", "txt_2"}, {"txt_2"})
        assert result
        assert gov.state == DesktopGovernanceState.DRIFTING

    def test_check_and_intervene(self):
        gov = DesktopGovernance()
        result = gov.check_and_intervene()
        assert result is None
        gov.degrade_mode("test")
        assert gov.state == DesktopGovernanceState.DEGRADED

    def test_autonomy_level_healthy(self):
        gov = DesktopGovernance()
        assert gov.get_autonomy_level() == 4

    def test_autonomy_level_locked(self):
        gov = DesktopGovernance()
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        assert gov.get_autonomy_level() == 0

    def test_event_to_dict(self):
        event = GovernanceEvent(
            action=GovernanceAction.CIRCUIT_BREAK,
            reason="3 failures",
            previous_state=DesktopGovernanceState.HEALTHY,
            new_state=DesktopGovernanceState.LOCKED,
        )
        d = event.to_dict()
        assert d["action"] == "circuit_break"
        assert d["reason"] == "3 failures"

    def test_escalate_to_human(self):
        gov = DesktopGovernance()
        gov.escalate_to_human("Critical error")
        assert gov.state == DesktopGovernanceState.LOCKED
        assert gov.event_log[-1].action == GovernanceAction.HUMAN_ESCALATE


class TestActionRecorder:
    def test_start_recording(self):
        recorder = ActionRecorder()
        recording = recorder.start_recording("rec-001", "Test Recording")
        assert recording.recording_id == "rec-001"
        assert recording.name == "Test Recording"
        assert recording.step_count == 0

    def test_record_steps(self):
        recorder = ActionRecorder()
        recorder.start_recording("rec-002", "Test")
        s1 = recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
        s2 = recorder.record_step(RecordedActionType.KEYBOARD_TYPE, text="hello")
        assert s1 is not None
        assert s2 is not None

        recording = recorder.stop_recording()
        assert recording is not None
        assert recording.step_count == 2

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = ActionRecorder(storage_dir=tmpdir)
            recorder.start_recording("rec-003", "Save Test", application="Finder")
            recorder.record_step(RecordedActionType.MOUSE_CLICK, x=10, y=20)
            recorder.record_step(RecordedActionType.KEYBOARD_HOTKEY, keys=["command", "c"])
            recorder.stop_recording()

            loaded = recorder.load("rec-003")
            assert loaded is not None
            assert loaded.name == "Save Test"
            assert loaded.application == "Finder"
            assert loaded.step_count == 2

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = ActionRecorder(storage_dir=tmpdir)
            recorder.start_recording("rec-del", "Delete Me")
            recorder.record_step(RecordedActionType.WAIT)
            recorder.stop_recording()
            assert recorder.load("rec-del") is not None
            assert recorder.delete("rec-del")
            assert recorder.load("rec-del") is None

    def test_list_recordings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = ActionRecorder(storage_dir=tmpdir)
            recorder.start_recording("r1", "First")
            recorder.stop_recording()
            recorder.start_recording("r2", "Second")
            recorder.stop_recording()
            recs = recorder.list_recordings()
            assert len(recs) == 2

    def test_get_steps_as_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = ActionRecorder(storage_dir=tmpdir)
            recorder.start_recording("rec-plan", "Plan Test")
            recorder.record_step(RecordedActionType.MOUSE_CLICK, x=50, y=50)
            recorder.record_step(RecordedActionType.KEYBOARD_TYPE, text="plan")
            recorder.stop_recording()

            plan = recorder.get_steps_as_plan("rec-plan")
            assert len(plan) == 2
            assert plan[0]["action_type"] == "mouse_click"
            assert plan[1]["action_type"] == "keyboard_type"

    def test_from_dict(self):
        data = {
            "recording_id": "from-dict",
            "name": "Dict Test",
            "steps": [
                {"step_id": "0000", "action_type": "mouse_click", "timestamp": 0.5, "x": 10, "y": 20},
            ],
            "screen_width": 1920,
            "screen_height": 1080,
        }
        recording = ActionRecording.from_dict(data)
        assert recording.recording_id == "from-dict"
        assert recording.step_count == 1
        assert recording.steps[0].x == 10

    def test_recorded_step_to_dict(self):
        step = RecordedStep(
            step_id="0001",
            action_type=RecordedActionType.KEYBOARD_HOTKEY,
            timestamp=1.0,
            keys=["command", "s"],
            description="Save file",
        )
        d = step.to_dict()
        assert d["step_id"] == "0001"
        assert d["keys"] == ["command", "s"]
        assert d["action_type"] == "keyboard_hotkey"
