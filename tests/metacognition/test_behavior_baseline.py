from __future__ import annotations

from maref.metacognition.behavior_baseline import BehaviorBaseline
from maref.metacognition.models import SessionRecord


def _make_session(
    session_id: str,
    outputs: list[str] | None = None,
    capabilities: set[str] | None = None,
    refusal_count: int = 0,
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        agent_id="test-agent",
        outputs=outputs or ["hello world"],
        response_times=[0.5, 0.8, 1.2],
        capabilities_demonstrated=capabilities or {"math"},
        refusal_count=refusal_count,
        refusal_topics=[],
    )


class TestBehaviorBaseline:
    def test_build_profile(self) -> None:
        baseline = BehaviorBaseline()
        sessions = [
            _make_session("s1", outputs=["hello world"]),
            _make_session("s2", outputs=["foo bar baz"]),
            _make_session("s3", outputs=["a b c d e"]),
        ]
        profile = baseline.build_profile("test-agent", sessions)
        assert profile.agent_id == "test-agent"
        assert profile.session_count == 3
        assert profile.sample_count == sum(len(s.outputs) for s in sessions)
        assert profile.output_entropy_mean > 0

    def test_build_profile_empty(self) -> None:
        baseline = BehaviorBaseline()
        profile = baseline.build_profile("empty-agent", [])
        assert profile.session_count == 0
        assert profile.output_entropy_mean == 0.0

    def test_compare_consistent(self) -> None:
        baseline = BehaviorBaseline()
        sessions = [
            _make_session("s1", outputs=["hello world"], capabilities={"math", "code"}),
            _make_session("s2", outputs=["foo bar"], capabilities={"math", "code"}),
        ]
        baseline.build_profile("test-agent", sessions)
        profile = baseline.get_profile("test-agent")
        assert profile is not None
        new_session = _make_session(
            "s3",
            outputs=["another test"],
            capabilities={"math", "code"},
        )
        report = baseline.compare(profile, new_session)
        assert report.is_consistent
        assert report.confidence >= 0.7

    def test_compare_inconsistent_entropy(self) -> None:
        baseline = BehaviorBaseline()
        sessions = [
            _make_session("s1", outputs=["a"] * 100, capabilities={"math"}),
            _make_session("s2", outputs=["b"] * 100, capabilities={"math"}),
        ]
        baseline.build_profile("test-agent", sessions)
        profile = baseline.get_profile("test-agent")
        assert profile is not None
        deviant_session = _make_session(
            "s3",
            outputs=["completely different output with many words and varied characters !@#$%"],
            capabilities={"math"},
        )
        report = baseline.compare(profile, deviant_session)
        assert report.entropy_deviation > 0

    def test_compare_capability_suppression(self) -> None:
        baseline = BehaviorBaseline()
        sessions = [
            _make_session(
                "s1",
                outputs=["test"],
                capabilities={"math", "code", "security", "translation"},
            ),
        ]
        baseline.build_profile("test-agent", sessions)
        profile = baseline.get_profile("test-agent")
        assert profile is not None
        suppressed_session = _make_session(
            "s2",
            outputs=["test"],
            capabilities={"math"},
        )
        report = baseline.compare(profile, suppressed_session)
        assert len(report.capability_suppression) > 0
        assert "code" in report.capability_suppression or "security" in report.capability_suppression

    def test_anomaly_detection(self) -> None:
        baseline = BehaviorBaseline()
        session = _make_session("s1", outputs=["hello world"], capabilities={"math"})
        profile = baseline.build_profile("test-agent", [session])
        anomalous = SessionRecord(
            session_id="s2",
            agent_id="test-agent",
            outputs=["a" * 3],
            response_times=[0.5],
            capabilities_demonstrated={"math"},
            refusal_count=5,
            refusal_topics=["security"],
        )
        report = baseline.compare(profile, anomalous)
        assert len(report.anomalies) > 0

    def test_get_profile_returns_none_for_unknown(self) -> None:
        baseline = BehaviorBaseline()
        assert baseline.get_profile("unknown") is None
