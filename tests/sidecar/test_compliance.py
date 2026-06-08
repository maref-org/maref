"""
Tests for Unified MAREF-Test Compliance Sidecar.

Covers:
  - Decision tree 4-level evaluation
  - UnifiedSidecar action checking
  - Compliance policy rules
  - TLA+ theorem runtime verification via sidecar
"""

from __future__ import annotations

import json

import pytest

from sidecar.compliance.decision_tree import (
    DecisionLevel,
    DecisionTree,
    PolicyCategory,
    PolicyContext,
    PolicyDecision,
)
from sidecar.compliance.policy import (
    FULL_AUDIT_RULES,
    check_business_rule_version,
    check_data_residency,
)
from sidecar.compliance.unified import UnifiedSidecar


class TestDecisionTree:
    def test_allow_no_violations(self):
        tree = DecisionTree()
        ctx = PolicyContext(agent_id="a1", action="read_file", action_type="tool_execution", agent_phase="OLD_YANG")
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.ALLOW
        assert decision.is_allowed

    def test_block_critical_compliance(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="write_file",
            action_type="tool_execution",
            has_critical_findings=True,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.BLOCK
        assert decision.is_blocked
        assert decision.rule_id == "rule-block-critical-compliance"

    def test_block_old_yin_execution(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="execute_tool",
            action_type="tool_execution",
            agent_phase="OLD_YIN",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.BLOCK
        assert decision.rule_id == "rule-block-old-yin-action"

    def test_block_old_yin_self_modify(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="modify_code",
            action_type="self_modify",
            agent_phase="OLD_YIN",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.BLOCK

    def test_block_unauthorized_cross_boundary(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="transfer_data",
            action_type="cross_boundary",
            cross_border=True,
            agent_phase="LESSER_YIN",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.BLOCK
        assert decision.rule_id == "rule-block-unauthorized-cross-border"

    def test_allow_cross_boundary_in_old_yang(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="transfer_data",
            action_type="cross_boundary",
            cross_border=True,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.ALLOW

    def test_throttle_high_entropy(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="process",
            action_type="tool_execution",
            current_entropy=3.5,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.THROTTLE
        assert decision.rule_id == "rule-throttle-high-entropy"

    def test_throttle_low_eval_score(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="process",
            action_type="tool_execution",
            eval_score=30.0,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.THROTTLE
        assert decision.rule_id == "rule-throttle-low-eval-score"

    def test_warn_cross_border_inconsistency(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="store_data",
            data_residency="US",
            model_backend="EU",
            cross_border=False,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.WARN
        assert decision.category == PolicyCategory.CROSS_BORDER

    def test_warn_moderate_entropy(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="process",
            action_type="tool_execution",
            current_entropy=2.0,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.WARN

    def test_decision_priority_block_overrides_warn(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="process",
            action_type="tool_execution",
            has_critical_findings=True,
            current_entropy=2.0,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.BLOCK

    def test_priority_throttle_overrides_warn(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="a1",
            action="process",
            action_type="tool_execution",
            current_entropy=3.5,
            eval_score=30.0,
            agent_phase="OLD_YANG",
        )
        decision = tree.evaluate(ctx)
        assert decision.decision == DecisionLevel.THROTTLE

    def test_decision_to_dict(self):
        d = PolicyDecision(
            decision=DecisionLevel.BLOCK,
            category=PolicyCategory.COMPLIANCE,
            rule_id="rule-test",
            reason="test",
        )
        d2 = d.to_dict()
        assert d2["decision"] == "block"
        assert d2["decision_level"] == 3

    def test_rate_limiter(self):
        from sidecar.compliance.decision_tree import RateLimiter
        rl = RateLimiter(default_limit=5)
        agent = "test-agent"
        count, limit = rl.check(agent, 5)
        assert count == 1
        assert limit == 5
        for _ in range(4):
            rl.check(agent, 5)
        count, limit = rl.check(agent, 5)
        assert count == 6
        assert limit == 5


class TestUnifiedSidecar:
    def test_default_state(self):
        sc = UnifiedSidecar(agent_id="a1")
        assert sc.agent_id == "a1"
        assert sc.governance_state == "INIT"

    def test_check_action_block(self):
        sc = UnifiedSidecar(agent_id="a1")
        sc._has_critical_findings = True
        decision = sc.check_action("deploy", "tool_execution")
        assert decision.is_blocked

    def test_check_action_allow(self):
        sc = UnifiedSidecar(agent_id="a1", phase="OLD_YANG")
        decision = sc.check_action("read_log", "tool_execution")
        assert decision.is_allowed

    def test_block_with_reason(self):
        sc = UnifiedSidecar(agent_id="a1")
        sc.block_with_reason("COMPLIANCE_VIOLATION")
        assert sc.governance_state == "HALT"

    def test_ingest_eval_report(self):
        sc = UnifiedSidecar(agent_id="a1")
        report = json.dumps({
            "overall_score": 45.0,
            "findings_summary": {"critical": 2, "high": 1},
        })
        sc.ingest_eval_report(report)
        assert sc._eval_score == 45.0
        assert sc._has_critical_findings is True

    def test_ingest_agent_card(self):
        sc = UnifiedSidecar(agent_id="a1")
        card = json.dumps({
            "agent_id": "a2",
            "data_residency": "US",
            "model_backend_location": "EU",
            "cross_border": True,
        })
        sc.ingest_agent_card(card)
        assert sc.agent_id == "a2"
        assert sc.data_residency == "US"
        assert sc.model_backend == "EU"
        assert sc.cross_border is True

    def test_audit_log(self):
        sc = UnifiedSidecar(agent_id="a1", phase="OLD_YANG")
        sc.check_action("read", "tool_execution")
        sc.check_action("write", "tool_execution")
        assert len(sc.audit_log) == 2
        assert sc.audit_log[0]["action"] == "read"

    def test_to_dict(self):
        sc = UnifiedSidecar(agent_id="a1")
        d = sc.to_dict()
        assert d["agent_id"] == "a1"
        assert d["governance_state"] == "INIT"
        assert d["phase"] == "OLD_YIN"


class TestCompliancePolicy:
    def test_full_audit_rules_exist(self):
        assert len(FULL_AUDIT_RULES) > 0

    def test_data_residency_check_pass(self):
        import asyncio
        result = asyncio.run(check_data_residency("US", "US", False))
        assert result.passed is True

    def test_data_residency_check_fail(self):
        import asyncio
        result = asyncio.run(check_data_residency("US", "EU", False))
        assert result.passed is False

    def test_business_rule_version_fail(self):
        import asyncio
        result = asyncio.run(check_business_rule_version([
            {"skill_id": "s1", "name": "search"},
        ]))
        assert result.passed is False

    def test_business_rule_version_pass(self):
        import asyncio
        result = asyncio.run(check_business_rule_version([
            {"skill_id": "s1", "name": "search", "business_rule_version": "1.0"},
        ]))
        assert result.passed is True


class TestTLATheoremsViaSidecar:
    def test_cross_border_consistency_theorem(self):
        sc = UnifiedSidecar(agent_id="a1", data_residency="US", model_backend="EU", cross_border=False)
        decision = sc.check_action("store", "data_operation")
        assert decision.decision >= DecisionLevel.WARN
        assert decision.category == PolicyCategory.CROSS_BORDER

    def test_compliance_quarantine_safety_theorem(self):
        sc = UnifiedSidecar(agent_id="a1")
        sc._has_critical_findings = True
        decision = sc.check_action("deploy", "tool_execution")
        assert decision.is_blocked
        sc.block_with_reason("VERIFIED: ComplianceQuarantineSafety")
        assert sc.governance_state == "HALT"

    def test_eval_to_governance_liveness_theorem(self):
        sc = UnifiedSidecar(agent_id="a1", phase="OLD_YANG")
        sc._eval_score = 30.0
        decision = sc.check_action("execute", "tool_execution")
        assert decision.decision == DecisionLevel.THROTTLE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
