from __future__ import annotations

from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.metacognition.auditor import MetaCognitiveAuditor
from maref.metacognition.models import (
    InferenceRecommendation,
    SessionRecord,
)


def _make_session(session_id: str, capabilities: set[str] | None = None) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        agent_id="test-agent",
        outputs=["hello world", "this is a test output with enough variety !@#"],
        response_times=[0.5, 0.8, 1.2],
        capabilities_demonstrated=capabilities or {"math", "code"},
        refusal_count=0,
        refusal_topics=[],
    )


class TestMetaCognitiveAuditor:
    def test_assess_clean_agent(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        auditor = MetaCognitiveAuditor(state_machine=sm, circuit_breaker=cb)
        session = _make_session("s1", capabilities={"math", "code"})
        result = auditor.assess("test-agent", session, known_capabilities=["math"])

        assert result.recommendation == InferenceRecommendation.OBSERVE
        assert result.deception_probability < 0.3
        assert not sm.is_terminal()

    def test_assess_detects_deception(self) -> None:
        auditor = MetaCognitiveAuditor()
        normal = _make_session("n1", capabilities={"math", "code", "security", "translation"})
        auditor.assess("agent", normal, known_capabilities=[])

        anomalous = SessionRecord(
            session_id="a1", agent_id="agent",
            outputs=["completely different varied output !@#$%^&*() XZ with high entropy"],
            response_times=[0.5, 0.8, 1.2],
            capabilities_demonstrated=set(),
            refusal_count=10, refusal_topics=["security", "code", "math"],
        )
        result = auditor.assess("agent", anomalous, known_capabilities=["code", "security", "math"])
        assert result.deception_probability > 0

    def test_governance_halt_on_high_deception(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(cooldown_seconds=300, max_consecutive_failures=3)
        auditor = MetaCognitiveAuditor(state_machine=sm, circuit_breaker=cb)

        normal = _make_session("n1", capabilities={"math", "code", "security", "translation"})
        auditor.assess("agent", normal, known_capabilities=[])

        for i in range(4):
            session = SessionRecord(
                session_id=f"s{i}", agent_id="agent",
                outputs=[f"high entropy varied output !@#$%^ XZ {i}"],
                response_times=[5.0, 10.0],
                capabilities_demonstrated=set(),
                refusal_count=5, refusal_topics=["security", "code", "math"],
            )
            auditor.assess("agent", session, known_capabilities=["code", "security", "math"])

        assert cb.state == BreakerState.OPEN or sm.is_terminal()

    def test_get_history(self) -> None:
        auditor = MetaCognitiveAuditor()
        session = _make_session("s1")
        auditor.assess("test-agent", session)
        history = auditor.get_history("test-agent")
        assert len(history) == 1

    def test_get_history_empty(self) -> None:
        auditor = MetaCognitiveAuditor()
        assert auditor.get_history("nonexistent") == []

    def test_get_profile(self) -> None:
        auditor = MetaCognitiveAuditor()
        session = _make_session("s1")
        auditor.assess("test-agent", session)
        profile = auditor.get_profile("test-agent")
        assert profile is not None
        assert profile.agent_id == "test-agent"

    def test_get_profile_unknown(self) -> None:
        auditor = MetaCognitiveAuditor()
        assert auditor.get_profile("unknown") is None

    def test_get_stats(self) -> None:
        auditor = MetaCognitiveAuditor()
        session = _make_session("s1")
        auditor.assess("agent-a", session)
        auditor.assess("agent-b", session)
        stats = auditor.get_stats()
        assert stats["agents_tracked"] == 2
        assert stats["total_assessments"] == 2

    def test_no_governance_integration(self) -> None:
        auditor = MetaCognitiveAuditor()
        session = _make_session("s1")
        result = auditor.assess("standalone", session)
        assert result.recommendation == InferenceRecommendation.OBSERVE
