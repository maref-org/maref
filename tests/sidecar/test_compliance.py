from __future__ import annotations

from sidecar.compliance.decision_tree import DecisionResult, DecisionTree, PolicyContext
from sidecar.compliance.unified import CheckActionResult, UnifiedSidecar


class TestDecisionTree:
    def test_allow_default(self) -> None:
        dt = DecisionTree()
        ctx = PolicyContext(action="read")
        result = dt.evaluate(ctx)
        assert result.decision == "allow"
        assert result.rule_id == "R0-default"
        assert result.risk_score == 0.1

    def test_block_critical(self) -> None:
        dt = DecisionTree()
        ctx = PolicyContext(action="write", has_critical_findings=True)
        result = dt.evaluate(ctx)
        assert result.decision == "block"
        assert result.rule_id == "R1-critical"
        assert result.risk_score == 0.9

    def test_warn_cross_border(self) -> None:
        dt = DecisionTree()
        ctx = PolicyContext(action="read", cross_border=True)
        result = dt.evaluate(ctx)
        assert result.decision == "warn"
        assert result.rule_id == "R2-border"
        assert result.risk_score == 0.6

    def test_throttle_high_entropy(self) -> None:
        dt = DecisionTree()
        ctx = PolicyContext(action="process", current_entropy=4.5)
        result = dt.evaluate(ctx)
        assert result.decision == "throttle"
        assert result.rule_id == "R3-entropy"
        assert result.risk_score == 0.5

    def test_critical_overrides_border_and_entropy(self) -> None:
        dt = DecisionTree()
        ctx = PolicyContext(
            action="admin",
            has_critical_findings=True,
            cross_border=True,
            current_entropy=5.0,
        )
        result = dt.evaluate(ctx)
        assert result.decision == "block"

    def test_evaluate_with_dict(self) -> None:
        dt = DecisionTree()
        ctx = {"action": "delete", "has_critical_findings": False, "current_entropy": 2.0}
        result = dt.evaluate(ctx)
        assert result.decision == "allow"

    def test_decision_result_defaults(self) -> None:
        dr = DecisionResult()
        assert dr.decision == "allow"
        assert dr.rule_id == ""
        assert dr.risk_score == 0.0
        assert dr.reason == ""

    def test_policy_context_kwargs(self) -> None:
        ctx = PolicyContext(action="test", resource="file", custom_field="val")
        assert ctx.action == "test"
        assert ctx.resource == "file"
        assert ctx.custom_field == "val"


class TestUnifiedSidecar:
    def test_default_construction(self) -> None:
        us = UnifiedSidecar()
        assert us.agent_id == ""
        assert us.phase == ""
        assert us.routes == {}
        assert us._audit_log == []

    def test_custom_construction(self) -> None:
        us = UnifiedSidecar(agent_id="agent-42", phase="beta")
        assert us.agent_id == "agent-42"
        assert us.phase == "beta"

    def test_check_action_allow_read(self) -> None:
        us = UnifiedSidecar()
        result = us.check_action("read")
        assert result.decision == "allow"
        assert "read" in result.reason

    def test_check_action_block_write(self) -> None:
        us = UnifiedSidecar()
        result = us.check_action("write")
        assert result.decision == "block"

    def test_check_action_block_write_with_type(self) -> None:
        us = UnifiedSidecar()
        result = us.check_action("write", action_type="file")
        assert result.decision == "block"
        assert "file" in result.reason

    def test_audit_log_populated(self) -> None:
        us = UnifiedSidecar(agent_id="agent-1")
        us.check_action("read")
        us.check_action("write")
        assert len(us._audit_log) == 2
        assert us._audit_log[0]["agent_id"] == "agent-1"
        assert us._audit_log[0]["decision"] == "allow"
        assert us._audit_log[1]["decision"] == "block"

    def test_register_and_handle(self) -> None:
        us = UnifiedSidecar()
        def handler(req: str) -> str:
            return f"handled: {req}"
        us.register("/test", handler)
        result = us.handle("/test", "hello")
        assert result == "handled: hello"

    def test_handle_missing_route(self) -> None:
        us = UnifiedSidecar()
        result = us.handle("/nonexistent", "data")
        assert result is None

    def test_check_action_result_defaults(self) -> None:
        car = CheckActionResult()
        assert car.decision == "allow"
        assert car.reason == ""
        assert car.risk_score == 0.0
