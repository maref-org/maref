"""v0.53 S7: 预算/破坏性门接入 GovernancePipeline。

验证：
1. 预算超限时 govern 返回 DENY (budget_breaker)
2. 破坏性操作 BLOCK 时返回 DENY (destructive_gate)
3. 破坏性操作 HITL_REQUIRED 时升级 ASK_USER 并创建审批事件
4. 未注入 gate 时行为不变（向后兼容）
"""

from __future__ import annotations

from maref.governance.budget_breaker import BudgetBreaker
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)
from maref.governance.destructive_gate import (
    DestructiveOperationGate,
    GateDecision,
    GateVerdict,
)


def _req(action: str = "file.read", agent: str = "agent-a") -> GovernanceRequest:
    return GovernanceRequest(action=action, agent_id=agent)


class TestBudgetBreaker:
    def test_over_budget_denied(self):
        breaker = BudgetBreaker(max_per_agent=10.0, max_per_task=5.0)
        breaker.record_spend("agent-a", "task-1", 50.0)  # 超限
        pipe = GovernancePipeline(budget_breaker=breaker)

        result = pipe.govern(_req("file.read", "agent-a"))
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "budget_breaker"

    def test_within_budget_allowed(self):
        breaker = BudgetBreaker(max_per_agent=1000.0)
        breaker.record_spend("agent-a", "task-1", 5.0)
        pipe = GovernancePipeline(budget_breaker=breaker)

        result = pipe.govern(_req("file.read", "agent-a"))
        assert result.verdict == Verdict.ALLOW

    def test_no_breaker_preserves_behavior(self):
        pipe = GovernancePipeline()
        assert pipe.govern(_req()).verdict == Verdict.ALLOW


class TestDestructiveGate:
    def test_block_denied(self):
        gate = DestructiveOperationGate(hitl_threshold=0.3, block_above=0.5)
        pipe = GovernancePipeline(destructive_gate=gate)

        result = pipe.govern(_req("shell.exec rm -rf /", "agent-a"))
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "destructive_gate"

    def test_hitl_required_upgrades_to_ask_user(self):
        gate = DestructiveOperationGate(hitl_threshold=0.2, block_above=0.95)
        pipe = GovernancePipeline(destructive_gate=gate)

        result = pipe.govern(_req("shell.exec rm -rf /", "agent-a"))
        assert result.verdict == Verdict.ASK_USER
        assert result.matched_rule == "destructive_gate_hitl"
        assert result.hitl_event_id

    def test_benign_action_allowed(self):
        gate = DestructiveOperationGate()
        pipe = GovernancePipeline(destructive_gate=gate)

        result = pipe.govern(_req("file.read", "agent-a"))
        assert result.verdict == Verdict.ALLOW

    def test_disabled_gate_allows(self):
        gate = DestructiveOperationGate(enabled=False)
        pipe = GovernancePipeline(destructive_gate=gate)

        result = pipe.govern(_req("file.read", "agent-a"))
        assert result.verdict == Verdict.ALLOW


class TestGateDecision:
    def test_gate_verdict_enum(self):
        assert GateVerdict.BLOCK.value == "BLOCK"
        assert GateDecision is not None
