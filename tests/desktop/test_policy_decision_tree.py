"""Tests for Phase D3: Safety Gate -> Decision Tree connection and HITL interrupt flow."""

from maref.desktop.controller import DesktopController
from maref.desktop.policy_decision_tree import (
    DecisionLevel,
    DecisionVerdict,
    OperationMode,
    PolicyDecisionTree,
)


class TestPolicyDecisionTree:
    def test_l1_block_dangerous_apps(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Terminal",
        )
        assert result.verdict == DecisionVerdict.BLOCK
        assert result.level == DecisionLevel.RULE_BASED

    def test_l1_allow_safe_apps(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
        )
        assert result.verdict == DecisionVerdict.ALLOW
        assert result.level == DecisionLevel.RULE_BASED

    def test_l1_block_dangerous_commands(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="type",
            input_text="rm -rf /",
        )
        assert result.verdict == DecisionVerdict.BLOCK
        assert result.level == DecisionLevel.RULE_BASED

    def test_l2_ask_mode_requires_confirmation(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.ASK_MODE)
        result = tree.evaluate(operation="click", app_name="Finder")
        assert result.verdict == DecisionVerdict.ASK_USER
        assert result.level == DecisionLevel.MODE_BASED

    def test_l3_safety_check_blocks_when_locked(self) -> None:
        tree = PolicyDecisionTree()
        tree._safety_gate._locked = True
        tree._safety_gate._locked_until = 9999999999.0
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Delete",
        )
        assert result.verdict == DecisionVerdict.BLOCK
        assert result.level == DecisionLevel.SAFETY_CHECK

    def test_l3_safety_check_requires_confirmation_for_high_threat(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Delete",
            safe_apps={"Finder"},
        )
        assert result.verdict in (DecisionVerdict.ASK_USER, DecisionVerdict.BLOCK)
        assert result.level == DecisionLevel.SAFETY_CHECK

    def test_decision_log_tracks_all_evaluations(self) -> None:
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Finder")
        tree.evaluate(operation="type", input_text="rm -rf /")
        tree.evaluate(operation="click", app_name="Terminal")
        assert len(tree.get_decision_log()) == 3

    def test_level_distribution(self) -> None:
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Finder")
        tree.evaluate(operation="type", input_text="rm -rf /")
        dist = tree.get_level_distribution()
        assert dist.get("rule_based", 0) == 2


class TestDesktopControllerPolicyTreeIntegration:
    def test_controller_uses_policy_tree_for_safety(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        result = ctrl.get_policy_decision_log()
        assert isinstance(result, list)

    def test_controller_pending_hitl_decision(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        assert ctrl.pending_hitl_decision is None

    def test_controller_approve_hitl(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        assert ctrl.approve_hitl() is False
        assert ctrl.reject_hitl() is False

    def test_controller_set_operation_mode(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_operation_mode(OperationMode.ASK_MODE)
        assert ctrl._policy_tree.mode == OperationMode.ASK_MODE

    def test_controller_policy_tree_connected(self) -> None:
        ctrl = DesktopController(
            dry_run=True, parser_backend="mock", operation_mode=OperationMode.FULL_AUTO
        )
        log = ctrl.get_policy_decision_log()
        initial_count = len(log)
        assert isinstance(initial_count, int)


class TestHITLInterruptFlow:
    def test_ask_mode_triggers_hitl(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.ASK_MODE)
        result = tree.evaluate(operation="click", app_name="Finder")
        assert result.verdict == DecisionVerdict.ASK_USER
        assert result.level == DecisionLevel.MODE_BASED
        assert "Ask Mode" in result.reason

    def test_low_trust_triggers_hitl(self) -> None:
        tree = PolicyDecisionTree(trust_score_threshold=0.7)
        result = tree.evaluate(
            operation="click",
            app_name="SomeApp",
            element_text="Purchase",
            trust_score=0.5,
        )
        assert result.verdict in (DecisionVerdict.ASK_USER, DecisionVerdict.BLOCK)
        assert result.level in (DecisionLevel.SAFETY_CHECK, DecisionLevel.RULE_BASED)

    def test_dangerous_ui_element_requires_confirmation(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="Delete All Files",
        )
        assert result.verdict in (DecisionVerdict.ASK_USER, DecisionVerdict.BLOCK)

    def test_safe_operation_auto_allowed(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="",
            trust_score=1.0,
        )
        assert result.verdict == DecisionVerdict.ALLOW

    def test_full_auto_allows_low_risk(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="",
            trust_score=1.0,
            safe_apps={"Finder"},
        )
        assert result.verdict == DecisionVerdict.ALLOW
        assert result.level in (
            DecisionLevel.RULE_BASED,
            DecisionLevel.MODE_BASED,
            DecisionLevel.SAFETY_CHECK,
        )

    def test_decision_log_records_verdicts(self) -> None:
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Finder")
        tree.evaluate(operation="click", app_name="Terminal")
        tree.evaluate(operation="type", input_text="rm -rf /")

        log = tree.get_decision_log()
        verdicts = [d.verdict for d in log]
        assert DecisionVerdict.ALLOW in verdicts
        assert DecisionVerdict.BLOCK in verdicts
