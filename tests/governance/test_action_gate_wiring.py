"""行动闸装配：破坏性门与预算熔断在 GovernedPipeline 中真实生效。"""

from __future__ import annotations

from maref.governance.budget_breaker import BudgetBreaker
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline


def _pipeline(tmp_path, **overrides) -> GovernedPipeline:
    return GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        **overrides,
    )


class TestDestructiveGateWiring:
    def test_high_risk_action_blocked(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        result = pipeline.govern(
            GovernanceRequest(
                action="shell.exec rm -rf /", agent_id="agent-a", trust_score=90
            )
        )
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "destructive_gate"

    def test_destructive_tool_escalates_to_hitl(self, tmp_path):
        from maref.governance.trust_boundary import TrustBoundaryManager

        # 信任边界默认对 HIGH 动作 fail-closed；此处放行以单独验证破坏性门。
        pipeline = _pipeline(tmp_path, boundary=TrustBoundaryManager(fail_closed=False))
        result = pipeline.govern(
            GovernanceRequest(action="delete_file", agent_id="agent-a")
        )
        assert result.verdict == Verdict.ASK_USER
        assert result.matched_rule == "destructive_gate_hitl"
        assert result.hitl_event_id

    def test_benign_action_allowed(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        )
        assert result.verdict == Verdict.ALLOW

    def test_block_decision_is_audited(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        pipeline.govern(GovernanceRequest(action="shell.exec rm -rf /", agent_id="agent-a"))

        decisions = [
            entry
            for entry in pipeline.audit.read_all()
            if entry.event_type == "governance_decision"
        ]
        assert decisions[-1].metadata["matched_rule"] == "destructive_gate"
        assert "Destructive" in decisions[-1].details

    def test_gate_enabled_by_default(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        assert pipeline.destructive_gate.enabled is True


class TestBudgetBreakerWiring:
    def test_over_budget_denied(self, tmp_path):
        breaker = BudgetBreaker(max_per_agent=10.0)
        breaker.record_spend("agent-a", "task-1", 25.0)
        pipeline = _pipeline(tmp_path, budget_breaker=breaker)

        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        )

        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "budget_breaker"

    def test_breaker_installed_by_default(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        assert isinstance(pipeline.budget_breaker, BudgetBreaker)


class TestBudgetRecovery:
    def test_open_half_open_closed_transitions(self):
        breaker = BudgetBreaker(max_per_agent=10.0, cooldown_seconds=0.0)

        assert breaker.check_agent_budget("agent-a", 20.0) is False
        assert breaker.is_open("agent-a") is True

        assert breaker.check_agent_budget("agent-a", 20.0) is True
        breaker.record_success("agent-a")

        assert breaker.get_stats("agent-a")["state"] == "closed"
