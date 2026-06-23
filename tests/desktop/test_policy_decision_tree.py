"""Tests for Phase D3: Safety Gate -> Decision Tree connection and HITL interrupt flow."""

from unittest.mock import MagicMock

from maref.desktop.controller import DesktopController
from maref.desktop.policy_decision_tree import (
    AlwaysAllowKnownSafeApp,
    BlockDangerousCommands,
    BlockDangerousSystemApps,
    DecisionLevel,
    DecisionResult,
    DecisionVerdict,
    OperationMode,
    PolicyDecisionTree,
    SafetyRule,
)
from maref.desktop.safety_gate_desktop import DesktopThreatAssessment, DesktopThreatCategory, DesktopThreatSeverity


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


class TestDecisionResult:
    def test_to_dict_with_threat(self) -> None:
        threat = DesktopThreatAssessment(
            threat_detected=True,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.HIGH,
            description="test threat",
            blocked=True,
            requires_confirmation=True,
        )
        result = DecisionResult(
            verdict=DecisionVerdict.BLOCK,
            level=DecisionLevel.SAFETY_CHECK,
            reason="test",
            threat_assessment=threat,
            metadata={"key": "value"},
        )
        d = result.to_dict()
        assert d["verdict"] == "block"
        assert d["level"] == "safety_check"
        assert d["threat"] is not None
        assert d["metadata"]["key"] == "value"

    def test_to_dict_without_threat(self) -> None:
        result = DecisionResult(
            verdict=DecisionVerdict.ALLOW,
            level=DecisionLevel.RULE_BASED,
            reason="ok",
        )
        d = result.to_dict()
        assert d["threat"] is None


class TestSafetyRule:
    def test_default_evaluate_returns_none(self) -> None:
        rule = SafetyRule(rule_id="test", description="test")
        assert rule.evaluate({"app_name": "Finder"}) is None


class TestAlwaysAllowKnownSafeApp:
    def test_dangerous_word_aborts(self) -> None:
        rule = AlwaysAllowKnownSafeApp()
        result = rule.evaluate({
            "app_name": "Finder",
            "operation": "click",
            "element_text": "delete",
            "input_text": "",
            "trust_score": 1.0,
        })
        assert result is None

    def test_low_trust_aborts(self) -> None:
        rule = AlwaysAllowKnownSafeApp()
        result = rule.evaluate({
            "app_name": "Finder",
            "operation": "click",
            "element_text": "",
            "input_text": "",
            "trust_score": 0.3,
        })
        assert result is None

    def test_unsafe_app_returns_none(self) -> None:
        rule = AlwaysAllowKnownSafeApp()
        result = rule.evaluate({
            "app_name": "UnknownApp",
            "operation": "click",
            "element_text": "",
            "input_text": "",
            "trust_score": 1.0,
        })
        assert result is None

    def test_safe_app_allows(self) -> None:
        rule = AlwaysAllowKnownSafeApp()
        result = rule.evaluate({
            "app_name": "Finder",
            "operation": "click",
            "element_text": "",
            "input_text": "",
            "trust_score": 1.0,
        })
        assert result is not None
        assert result.verdict == DecisionVerdict.ALLOW
        assert result.level == DecisionLevel.RULE_BASED

    def test_custom_safe_apps(self) -> None:
        rule = AlwaysAllowKnownSafeApp(safe_apps={"CustomApp"})
        result = rule.evaluate({
            "app_name": "CustomApp",
            "operation": "scroll",
            "element_text": "",
            "input_text": "",
            "trust_score": 1.0,
        })
        assert result is not None
        assert result.verdict == DecisionVerdict.ALLOW


class TestBlockDangerousSystemApps:
    def test_blocks_terminal(self) -> None:
        rule = BlockDangerousSystemApps()
        result = rule.evaluate({"app_name": "Terminal"})
        assert result is not None
        assert result.verdict == DecisionVerdict.BLOCK

    def test_allows_safe_app(self) -> None:
        rule = BlockDangerousSystemApps()
        result = rule.evaluate({"app_name": "Finder"})
        assert result is None

    def test_blocks_system_settings(self) -> None:
        rule = BlockDangerousSystemApps()
        result = rule.evaluate({"app_name": "System Settings"})
        assert result is not None
        assert result.verdict == DecisionVerdict.BLOCK

    def test_empty_app_name(self) -> None:
        rule = BlockDangerousSystemApps()
        result = rule.evaluate({"app_name": ""})
        assert result is None

    def test_keychain_access(self) -> None:
        rule = BlockDangerousSystemApps()
        result = rule.evaluate({"app_name": "Keychain Access"})
        assert result is not None
        assert result.verdict == DecisionVerdict.BLOCK


class TestBlockDangerousCommands:
    def test_blocks_rm_rf(self) -> None:
        rule = BlockDangerousCommands()
        result = rule.evaluate({"input_text": "rm -rf /"})
        assert result is not None
        assert result.verdict == DecisionVerdict.BLOCK

    def test_blocks_drop_table(self) -> None:
        rule = BlockDangerousCommands()
        result = rule.evaluate({"input_text": "DROP TABLE users"})
        assert result is not None
        assert result.verdict == DecisionVerdict.BLOCK

    def test_allows_safe_text(self) -> None:
        rule = BlockDangerousCommands()
        result = rule.evaluate({"input_text": "ls -la"})
        assert result is None

    def test_empty_input(self) -> None:
        rule = BlockDangerousCommands()
        result = rule.evaluate({"input_text": ""})
        assert result is None


class TestPolicyDecisionTreeAdvanced:
    def test_set_mode(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.SEMI_AUTO)
        assert tree.mode == OperationMode.SEMI_AUTO
        tree.set_mode(OperationMode.FULL_AUTO)
        assert tree.mode == OperationMode.FULL_AUTO

    def test_safety_gate_property(self) -> None:
        tree = PolicyDecisionTree()
        assert tree.safety_gate is tree._safety_gate

    def test_full_auto_unauthorized_app(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="UnknownApp",
            safe_apps={"Finder"},
        )
        assert result.verdict == DecisionVerdict.BLOCK
        assert result.level == DecisionLevel.MODE_BASED

    def test_full_auto_low_risk(self) -> None:
        tree = PolicyDecisionTree(mode=OperationMode.FULL_AUTO)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="",
            safe_apps={"Finder"},
            trust_score=1.0,
        )
        assert result.verdict == DecisionVerdict.ALLOW

    def test_safety_check_low_trust(self) -> None:
        tree = PolicyDecisionTree(trust_score_threshold=0.7)
        result = tree.evaluate(
            operation="click",
            app_name="SomeApp",
            element_text="friendly text",
            safe_apps={"SomeApp"},
            trust_score=0.5,
        )
        assert result.verdict == DecisionVerdict.ASK_USER
        assert result.level == DecisionLevel.SAFETY_CHECK

    def test_safety_check_circuit_breaker(self) -> None:
        tree = PolicyDecisionTree()
        tree._safety_gate._locked = True
        tree._safety_gate._locked_until = 9999999999.0
        result = tree.evaluate(
            operation="click",
            app_name="SomeApp",
            element_text="friendly",
            safe_apps={"SomeApp"},
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.BLOCK

    def test_safety_check_confirmation_needed(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="SomeApp",
            element_text="purchase",
            safe_apps={"SomeApp"},
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.ASK_USER
        assert result.level == DecisionLevel.SAFETY_CHECK

    def test_safety_check_allow(self) -> None:
        tree = PolicyDecisionTree()
        result = tree.evaluate(
            operation="click",
            app_name="SomeApp",
            element_text="friendly text",
            safe_apps={"SomeApp"},
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.ALLOW
        assert result.level == DecisionLevel.SAFETY_CHECK

    def test_custom_safety_gate(self) -> None:
        gate = MagicMock()
        gate.assess_app_boundary.return_value = DesktopThreatAssessment(
            threat_detected=False,
            threat_category="unauthorized_app",
            severity=DesktopThreatSeverity.NONE,
            description="ok",
            blocked=False,
        )
        gate.assess_ui_interaction.return_value = DesktopThreatAssessment(
            threat_detected=False,
            threat_category="dangerous_ui",
            severity=DesktopThreatSeverity.NONE,
            description="ok",
            blocked=False,
        )
        gate.should_block_operation.return_value = DesktopThreatAssessment(
            threat_detected=False,
            threat_category="dangerous_ui",
            severity=DesktopThreatSeverity.NONE,
            description="ok",
            blocked=False,
        )
        gate.is_locked = False
        tree = PolicyDecisionTree(safety_gate=gate)
        result = tree.evaluate(
            operation="click",
            app_name="Finder",
            element_text="hi",
            trust_score=0.9,
        )
        assert result.verdict == DecisionVerdict.ALLOW

    def test_get_level_distribution(self) -> None:
        tree = PolicyDecisionTree()
        tree.evaluate(operation="click", app_name="Finder")
        tree.evaluate(operation="click", app_name="Terminal")
        tree.evaluate(operation="click", app_name="Finder", element_text="format")
        dist = tree.get_level_distribution()
        assert "rule_based" in dist
        assert "safety_check" in dist
