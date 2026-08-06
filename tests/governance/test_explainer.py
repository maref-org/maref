"""Tests for DecisionExplainer (v0.51 W4-S1 / D1).

Structured reasoning chains: premises, reasoning steps, confidence, alternate
options, uncertainty sources — with mandatory production enforcement.
"""

from __future__ import annotations

import pytest

from maref.governance.explainer import (
    DecisionExplainer,
    ExplainerMode,
    ExplainerRequiredError,
    ReasoningChain,
    ReasoningStep,
)


def test_reasoning_step_serialization() -> None:
    step = ReasoningStep(description="check quota", confidence=0.9, basis="quota table")
    d = step.to_dict()
    assert d["description"] == "check quota"
    assert d["confidence"] == 0.9


def test_reasoning_chain_construction() -> None:
    chain = ReasoningChain(
        decision_id="dec-1",
        conclusion="approve transfer",
        premises=("balance > threshold", "recipient verified"),
        steps=(
            ReasoningStep(description="check balance", confidence=0.95, basis="ledger"),
            ReasoningStep(description="verify recipient", confidence=0.88, basis="registry"),
        ),
        confidence=0.9,
        alternatives=("reject", "escalate"),
        uncertainty_sources=("recipient address unverified",),
    )
    assert len(chain.premises) == 2
    assert len(chain.steps) == 2
    assert chain.confidence == 0.9


def test_reasoning_chain_serialization() -> None:
    chain = ReasoningChain(decision_id="dec-1", conclusion="approve")
    d = chain.to_dict()
    assert d["decision_id"] == "dec-1"
    assert d["conclusion"] == "approve"
    assert d["steps"] == []
    assert d["uncertainty_sources"] == []


def test_mandatory_mode_requires_explanation() -> None:
    explainer = DecisionExplainer(mode=ExplainerMode.MANDATORY)
    with pytest.raises(ExplainerRequiredError):
        explainer.require_explanation(decision_id="dec-1", conclusion="approve")


def test_lazy_mode_auto_produces_explanation() -> None:
    explainer = DecisionExplainer(mode=ExplainerMode.LAZY)
    chain = explainer.require_explanation(decision_id="dec-1", conclusion="approve")
    assert isinstance(chain, ReasoningChain)
    assert chain.decision_id == "dec-1"
    assert "lazy-generated" in chain.steps[0].basis


def test_skipped_mode_returns_none() -> None:
    explainer = DecisionExplainer(mode=ExplainerMode.SKIPPED)
    assert explainer.require_explanation(decision_id="dec-1", conclusion="approve") is None


def test_mandatory_mode_accepts_explicit_chain() -> None:
    explainer = DecisionExplainer(mode=ExplainerMode.MANDATORY)
    chain = ReasoningChain(decision_id="dec-1", conclusion="approve")
    result = explainer.require_explanation(decision_id="dec-1", conclusion="approve", chain=chain)
    assert result == chain


def test_explainer_requires_mode_is_explicit() -> None:
    with pytest.raises(ValueError):
        DecisionExplainer()  # mode 必须显式指定，防止默认弱化
