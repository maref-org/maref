from __future__ import annotations

from maref.metacognition.intention_inference import DeceptionInferenceEngine
from maref.metacognition.models import (
    AgentProfile,
    ConsistencyReport,
    InferenceRecommendation,
    ProbeResult,
    ProbeType,
)


def _make_consistent_report() -> ConsistencyReport:
    return ConsistencyReport(
        agent_id="test-agent",
        baseline_profile=AgentProfile(agent_id="test-agent"),
        current_entropy=2.5,
        entropy_deviation=0.5,
        latency_deviation=0.3,
        capability_suppression=[],
        anomalies=[],
        confidence=0.95,
        is_consistent=True,
    )


def _make_inconsistent_report() -> ConsistencyReport:
    return ConsistencyReport(
        agent_id="deceptive-agent",
        baseline_profile=AgentProfile(agent_id="deceptive-agent"),
        current_entropy=5.0,
        entropy_deviation=4.2,
        latency_deviation=3.5,
        capability_suppression=["code", "security", "math"],
        anomalies=[
            "extreme_entropy_deviation:4.20sigma",
            "extreme_latency_deviation:3.50sigma",
            "unexpected_refusals:3",
        ],
        confidence=0.3,
        is_consistent=False,
    )


class TestDeceptionInferenceEngine:
    def test_low_deception_probability(self) -> None:
        engine = DeceptionInferenceEngine()
        result = engine.infer(_make_consistent_report(), [])
        assert result.deception_probability < 0.3
        assert result.recommendation == InferenceRecommendation.OBSERVE

    def test_high_deception_probability(self) -> None:
        engine = DeceptionInferenceEngine()
        probes = [
            ProbeResult(
                probe_type=ProbeType.HONEYPOT,
                session_id="s1",
                capability_tested="code",
                expected_positive=True,
                response_hides_capability=True,
                response_time=1.5,
                confidence=0.9,
            ),
            ProbeResult(
                probe_type=ProbeType.COUNTERFACTUAL,
                session_id="s1",
                capability_tested="math",
                expected_positive=False,
                response_hides_capability=True,
                response_time=2.0,
                confidence=0.85,
            ),
        ]
        result = engine.infer(_make_inconsistent_report(), probes)
        assert result.deception_probability > 0.3
        assert result.recommendation in (
            InferenceRecommendation.INCREASE_SAMPLING,
            InferenceRecommendation.ESCALATE_AUDIT,
            InferenceRecommendation.HALT,
        )

    def test_halt_recommendation(self) -> None:
        engine = DeceptionInferenceEngine()
        many_probes = [
            ProbeResult(
                probe_type=ProbeType.HONEYPOT,
                session_id=f"s{i}",
                capability_tested="code",
                expected_positive=True,
                response_hides_capability=True,
                response_time=1.0,
                confidence=0.95,
            )
            for i in range(10)
        ]
        result = engine.infer(_make_inconsistent_report(), many_probes)
        assert result.recommendation in (
            InferenceRecommendation.ESCALATE_AUDIT,
            InferenceRecommendation.HALT,
        )

    def test_evidence_gathering(self) -> None:
        engine = DeceptionInferenceEngine()
        result = engine.infer(_make_inconsistent_report(), [])
        assert len(result.supporting_evidence) > 0
        assert any("entropy_deviation" in e for e in result.supporting_evidence)

    def test_confidence_interval_width(self) -> None:
        engine = DeceptionInferenceEngine()
        result = engine.infer(_make_consistent_report(), [])
        lower, upper = result.confidence_interval
        assert 0 <= lower <= upper <= 1
