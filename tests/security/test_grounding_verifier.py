"""Tests for GroundingVerifier (v0.51 W5-S1 / E1).

RAG faithfulness scoring: generated assertion ↔ retrieved evidence, with a
pluggable LLM judge interface.
"""

from __future__ import annotations

from maref.security.grounding_verifier import (
    GroundingScore,
    GroundingVerifier,
    SupportLevel,
)


def _verifier() -> GroundingVerifier:
    return GroundingVerifier()


def test_fully_supported_assertion_scores_high() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="customer count increased by 12%",
        evidence=["Customer count rose 12% in Q2"],
    )
    assert score.score >= 0.8
    assert score.support_level == SupportLevel.SUPPORTED


def test_contradictory_evidence_scores_low() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="revenue doubled last quarter",
        evidence=["Revenue was flat last quarter"],
    )
    assert score.score < 0.5


def test_reverse_direction_conflict_scores_low() -> None:
    """I2 回归：负向断言 vs 正向证据同样判矛盾."""
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="revenue declined last quarter",
        evidence=["Revenue increased last quarter"],
    )
    assert score.score < 0.5
    assert score.support_level == SupportLevel.CONTRADICTED


def test_irrelevant_evidence_scores_low() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="the sky is blue",
        evidence=["The stock market rallied on Tuesday"],
    )
    assert score.score < 0.5


def test_empty_evidence_is_unverifiable() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(assertion="claim", evidence=[])
    assert score.support_level == SupportLevel.UNVERIFIABLE
    assert score.score == 0.0


def test_grounding_score_serialization() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="alpha channel is live",
        evidence=["The alpha channel is now live"],
    )
    d = score.to_dict()
    assert d["support_level"] == "supported"
    assert d["evidence_ids"] == []
    assert 0.0 <= d["score"] <= 1.0


def test_pluggable_llm_judge_override() -> None:
    def fake_judge(assertion: str, evidence: list[str]) -> float:
        return 0.42

    verifier = GroundingVerifier(llm_judge=fake_judge)
    score = verifier.verify_assertion(assertion="anything", evidence=["anything"])
    assert score.score == 0.42


def test_passes_threshold_detection() -> None:
    verifier = _verifier()
    score = verifier.verify_assertion(
        assertion="customer count increased by 12%",
        evidence=["Customer count rose 12% in Q2"],
    )
    assert verifier.is_grounded(score, threshold=0.7)
    assert not verifier.is_grounded(score, threshold=0.95)
