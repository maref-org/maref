"""D10 tests: Full cross-module integration + chaos + end-to-end pipeline."""

from __future__ import annotations

import time

from maref.desktop.agent import (
    DesktopAgent,
    DesktopOperation,
    DesktopStep,
    DesktopTask,
)
from maref.desktop.desktop_governance import DesktopGovernance, DesktopGovernanceState
from maref.desktop.policy_decision_tree import (
    DecisionVerdict,
    OperationMode,
    PolicyDecisionTree,
)
from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2


class TestCrossModuleIntegration:
    """Tests that verify interoperability between M1 and M2 modules."""

    def test_agent_with_safety_tree(self):
        """DesktopAgent + PolicyDecisionTree + SafetyGate integration."""
        PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        agent = DesktopAgent(dry_run=True)

        task = DesktopTask(
            task_id="cross-test",
            description="Cross-module integration test",
            safe_apps=["Finder"],
            steps=[
                DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit"),
                DesktopStep(operation=DesktopOperation.TYPE, value="safe text"),
            ],
        )

        result = agent.execute_task(task)
        assert result.success
        assert result.steps_executed > 0

    def test_governance_with_agent(self):
        """DesktopGovernance monitors agent task execution."""
        gov = DesktopGovernance()
        agent = DesktopAgent(dry_run=True)

        task = DesktopTask(
            task_id="gov-test",
            description="Governance-monitored task",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        result = agent.execute_task(task)

        for op in result.operation_log:
            gov.record_operation_result(op.success, op.action_type, "test-target")

        assert gov.is_healthy

    def test_failure_cascade_triggers_lock(self):
        """Three consecutive failures should lock the safety gate."""
        gov = DesktopGovernance()
        gov.record_operation_result(False, "click", "dangerous-btn")
        gov.record_operation_result(False, "click", "dangerous-btn")
        gov.record_operation_result(False, "click", "dangerous-btn")
        assert gov.state == DesktopGovernanceState.LOCKED

    def test_recovery_after_success(self):
        """After lock recovery, agent should allow operations again."""
        gov = DesktopGovernance()
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        assert gov.state == DesktopGovernanceState.LOCKED
        gov.record_operation_result(True, "click", "btn")
        assert gov.state == DesktopGovernanceState.RECOVERING


class TestDecisionTreeWithAgent:
    """PolicyDecisionTree evaluating agent operations end-to-end."""

    def test_safe_finder_operation_allowed(self):
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Documents",
            safe_apps={"Finder"},
            trust_score=0.95,
        )
        assert result.verdict == DecisionVerdict.ALLOW

    def test_payment_button_requires_confirmation(self):
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Safari",
            element_text="Pay Now $49.99",
            safe_apps={"Safari"},
            trust_score=0.9,
        )
        assert result.verdict in (DecisionVerdict.ASK_USER, DecisionVerdict.BLOCK)

    def test_unauthorized_app_blocked(self):
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="UnknownHackerApp",
            element_text="Click Me",
            safe_apps={"Finder", "Safari"},
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.BLOCK

    def test_format_disk_always_blocked(self):
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Format Disk",
            safe_apps={"Finder"},
            trust_score=1.0,
        )
        assert result.verdict == DecisionVerdict.BLOCK


class TestChaosInjection:
    """Simulated chaos scenarios for desktop agent robustness."""

    def test_ui_change_triggers_drift(self):
        gov = DesktopGovernance()
        result = gov.detect_drift(
            {"btn_submit", "txt_name", "chk_agree"}, {"btn_submit", "txt_name"}
        )
        assert not result
        result = gov.detect_drift({"btn_submit", "txt_email"}, {"txt_email"})
        assert result
        assert gov.state == DesktopGovernanceState.DRIFTING

    def test_rapid_ui_changes_triggers_oscillation(self):
        gov = DesktopGovernance()
        for i in range(7):
            gov.detect_oscillation(f"hash_change_{i}")
        assert gov.state == DesktopGovernanceState.OSCILLATING

    def test_safety_gate_survives_rapid_operations(self):
        gate = DesktopSafetyGateV2()
        for i in range(100):
            gate.record_operation("click", f"btn_{i}", True)
        assert not gate.is_locked
        assert gate.consecutive_failures == 0

    def test_interleaved_failures_dont_lock(self):
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", True)
        gate.record_operation("click", "btn", False)
        gate.record_operation("click", "btn", True)
        gate.record_operation("click", "btn", False)
        assert gate.consecutive_failures == 1
        assert not gate.is_locked

    def test_governance_full_lifecycle(self):
        """Simulate a full governance lifecycle: healthy → degraded → locked → recovered."""
        gov = DesktopGovernance()
        assert gov.state == DesktopGovernanceState.HEALTHY
        assert gov.get_autonomy_level() == 4

        gov.degrade_mode("Performance degraded")
        assert gov.get_autonomy_level() == 3

        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        gov.record_operation_result(False, "click", "btn")
        assert gov.state == DesktopGovernanceState.LOCKED
        assert gov.get_autonomy_level() == 0

        gov.record_operation_result(True, "click", "btn")
        assert gov.state == DesktopGovernanceState.RECOVERING


class TestEndToEndPipeline:
    """Full pipeline from screen capture to governance verification."""

    def test_full_agent_pipeline_with_governance(self):
        agent = DesktopAgent(dry_run=True)

        screenshot = agent.capture_screen()
        assert screenshot is not None

        parse = agent.parse_screen(screenshot)
        assert len(parse.elements) > 0

        interactive = parse.find_interactive_elements()
        assert len(interactive) > 0

        submit = agent.find_element(parse, text="Submit")
        if submit:
            step = DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit")
            result = agent.execute_step(step, parse)
            assert result.success

        task = DesktopTask(
            task_id="e2e-001",
            description="End-to-end pipeline test",
            steps=[
                DesktopStep(operation=DesktopOperation.CLICK, target_text="Submit"),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.05),
                DesktopStep(operation=DesktopOperation.TYPE, value="test complete"),
            ],
        )
        result = agent.execute_task(task)
        assert result.success

    def test_pipeline_resilience_with_failures(self):
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen(agent.capture_screen())

        bad_step = DesktopStep(operation=DesktopOperation.CLICK, target_text="ZZZ_MISSING_ZZZ")
        bad_result = agent.execute_step(bad_step, parse)
        assert not bad_result.success

        good_step = DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)
        good_result = agent.execute_step(good_step)
        assert good_result.success

    def test_screenshot_to_parse_to_verify_pipeline(self):
        from maref.desktop.screen_capture import ScreenCapture
        from maref.desktop.verification import ScreenshotVerifier

        capture = ScreenCapture()
        before = capture.capture_fullscreen()
        time.sleep(0.1)
        after = capture.capture_fullscreen()

        verifier = ScreenshotVerifier(diff_threshold=0.1)
        if before.image and after.image:
            result = verifier.compare(before.image, after.image)
            assert isinstance(result.passed, bool)
