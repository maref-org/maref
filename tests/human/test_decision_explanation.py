"""Tests for D2: HITL reasoning-chain injection (v0.51 W4-S2).

The human approval surface must show a structured reasoning chain before a
decision can be made — never just a free-text rationale.
"""

from __future__ import annotations

from maref.governance.explainer import ReasoningChain, ReasoningStep
from maref.human.decision_api import DecisionContext, DecisionRequest, DecisionResponse


def _context(explanation: ReasoningChain | None = None) -> DecisionContext:
    return DecisionContext(
        task_id="transfer-001",
        agent_id="agent-1",
        action_description="execute large transfer",
        risk_score=0.8,
        explanation=explanation,
    )


def test_context_with_explanation_serializes_chain() -> None:
    chain = ReasoningChain(
        decision_id="dec-1",
        conclusion="approve",
        premises=("balance sufficient",),
        steps=(ReasoningStep(description="check balance", confidence=0.95, basis="ledger"),),
        confidence=0.9,
    )
    context = _context(explanation=chain)
    request = DecisionRequest(task_id="t1", context=context)
    d = request.to_dict()
    assert d["context"]["explanation"]["conclusion"] == "approve"
    assert d["context"]["explanation"]["steps"][0]["description"] == "check balance"


def test_context_without_explanation_serializes_none() -> None:
    context = _context()
    request = DecisionRequest(task_id="t1", context=context)
    d = request.to_dict()
    assert d["context"]["explanation"] is None


def test_approval_requires_explanation_in_mandatory_surface() -> None:
    """HITL 审批前必须可见推理链：context 无 explanation 时标记缺失."""
    context = _context()
    assert not context.explanation_present()
    context_with_chain = _context(explanation=ReasoningChain(decision_id="d", conclusion="approve"))
    assert context_with_chain.explanation_present()


def test_response_carries_referenced_decision() -> None:
    response = DecisionResponse(request_id="req-1", decision="approve", reason="checked", responded_by="human-1")
    assert response.decision == "approve"
    assert response.responded_by == "human-1"
