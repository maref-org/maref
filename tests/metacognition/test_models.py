from __future__ import annotations

from maref.metacognition.models import (
    AgentProfile,
    InferenceRecommendation,
    InferenceResult,
    ProbeType,
    SessionRecord,
)


class TestAgentProfile:
    def test_default_values(self) -> None:
        p = AgentProfile(agent_id="test-agent")
        assert p.agent_id == "test-agent"
        assert p.output_entropy_mean == 0.0
        assert p.session_count == 0

    def test_entropy_histogram(self) -> None:
        p = AgentProfile(
            agent_id="a1",
            output_entropy_mean=2.5,
            output_entropy_std=0.5,
            sample_count=100,
        )
        h = p.entropy_histogram()
        assert h["mean"] == 2.5
        assert h["std"] == 0.5
        assert h["samples"] == 100

    def test_latency_histogram(self) -> None:
        p = AgentProfile(
            agent_id="a1",
            response_latency_mean=1.2,
            response_latency_std=0.3,
            sample_count=50,
        )
        h = p.latency_histogram()
        assert h["mean"] == 1.2
        assert h["std"] == 0.3


class TestSessionRecord:
    def test_create_session(self) -> None:
        s = SessionRecord(
            session_id="s1",
            agent_id="a1",
            outputs=["hello", "world"],
            response_times=[0.5, 0.8],
            capabilities_demonstrated={"math", "code"},
            refusal_count=0,
            refusal_topics=[],
        )
        assert s.session_id == "s1"
        assert len(s.outputs) == 2


class TestInferenceResult:
    def test_to_dict(self) -> None:
        r = InferenceResult(
            agent_id="a1",
            deception_probability=0.75,
            evidence_strength=0.6,
            recommendation=InferenceRecommendation.HALT,
            supporting_evidence=["entropy_deviation:3.2sigma"],
            confidence_interval=(0.5, 0.9),
        )
        d = r.to_dict()
        assert d["agent_id"] == "a1"
        assert d["deception_probability"] == 0.75
        assert d["recommendation"] == "halt"

    def test_recommendation_enum(self) -> None:
        assert InferenceRecommendation.OBSERVE.value == "observe"
        assert InferenceRecommendation.HALT.value == "halt"


class TestProbeType:
    def test_enum_values(self) -> None:
        assert ProbeType.HONEYPOT.value == "honeypot"
        assert ProbeType.COUNTERFACTUAL.value == "counterfactual"
