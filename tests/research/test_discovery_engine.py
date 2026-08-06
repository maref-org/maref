"""Comprehensive tests for the DiscoveryEngine module."""

from __future__ import annotations

import statistics
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from research.discovery_engine import (
    ContradictionAlert,
    DiscoveryEngine,
    GeneratedHypothesis,
    TemporalPattern,
)
from research.knowledge_graph import KnowledgeNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str,
    node_type: str,
    content: str,
    timestamp: float = 0.0,
    metadata: dict[str, Any] | None = None,
    confidence: float = 0.8,
) -> KnowledgeNode:
    """Factory for KnowledgeNode dataclasses without I/O side effects."""
    return KnowledgeNode(
        id=node_id,
        type=node_type,
        content=content,
        confidence=confidence,
        source="test",
        timestamp=timestamp,
        metadata=metadata or {},
    )


@pytest.fixture
def mock_kg() -> MagicMock:
    """Return a bare MagicMock that mimics a KnowledgeGraph."""
    kg = MagicMock()
    kg._nodes = {}
    kg.query.return_value = []
    kg.get_open_questions.return_value = []
    return kg


@pytest.fixture
def engine(mock_kg: MagicMock) -> DiscoveryEngine:
    """Return a DiscoveryEngine wired to a mock KnowledgeGraph."""
    return DiscoveryEngine(knowledge_graph=mock_kg)


# ---------------------------------------------------------------------------
# 1. Dataclass construction and defaults
# ---------------------------------------------------------------------------

class TestTemporalPattern:
    def test_construction_all_fields(self) -> None:
        pattern = TemporalPattern(
            pattern_type="seasonal",
            description="peaks in summer",
            confidence=0.95,
            supporting_evidence=["paper_a", "paper_b"],
        )
        assert pattern.pattern_type == "seasonal"
        assert pattern.description == "peaks in summer"
        assert pattern.confidence == 0.95
        assert pattern.supporting_evidence == ["paper_a", "paper_b"]

    def test_default_supporting_evidence(self) -> None:
        pattern = TemporalPattern(pattern_type="trend", description="upward", confidence=0.5)
        assert pattern.supporting_evidence == []


class TestContradictionAlert:
    def test_construction_all_fields(self) -> None:
        alert = ContradictionAlert(
            severity="high",
            description="x contradicts y",
            conflicting_nodes=["n1", "n2"],
            recommendation="re-run experiment",
        )
        assert alert.severity == "high"
        assert alert.description == "x contradicts y"
        assert alert.conflicting_nodes == ["n1", "n2"]
        assert alert.recommendation == "re-run experiment"

    def test_defaults(self) -> None:
        alert = ContradictionAlert(severity="low", description="minor")
        assert alert.conflicting_nodes == []
        assert alert.recommendation == ""


class TestGeneratedHypothesis:
    def test_construction_all_fields(self) -> None:
        hyp = GeneratedHypothesis(
            hypothesis="H1",
            based_on=["m1", "m2"],
            testable=True,
            suggested_experiment="exp_1",
        )
        assert hyp.hypothesis == "H1"
        assert hyp.based_on == ["m1", "m2"]
        assert hyp.testable is True
        assert hyp.suggested_experiment == "exp_1"

    def test_defaults(self) -> None:
        hyp = GeneratedHypothesis(hypothesis="H2", based_on=["a"], testable=False)
        assert hyp.suggested_experiment == ""


# ---------------------------------------------------------------------------
# 2. DiscoveryEngine.__init__
# ---------------------------------------------------------------------------

class TestDiscoveryEngineInit:
    def test_init_with_none_creates_default_kg(self) -> None:
        with patch("research.discovery_engine.KnowledgeGraph") as MockKG:
            instance = MagicMock()
            MockKG.return_value = instance
            engine = DiscoveryEngine(knowledge_graph=None)
            MockKG.assert_called_once_with()
            assert engine._kg is instance

    def test_init_with_provided_kg(self, mock_kg: MagicMock) -> None:
        engine = DiscoveryEngine(knowledge_graph=mock_kg)
        assert engine._kg is mock_kg


# ---------------------------------------------------------------------------
# 3. analyze_trends
# ---------------------------------------------------------------------------

class TestAnalyzeTrends:
    def test_insufficient_metric_nodes(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = [
            _make_node("n1", "metric", "m1", metadata={"value": "1.0"}),
        ]
        result = engine.analyze_trends("metric_name")
        assert result == {"trend": "insufficient_data", "confidence": 0.0}

    def test_insufficient_values(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = [
            _make_node("n1", "metric", "m1", metadata={}),
            _make_node("n2", "metric", "m2", metadata={}),
            _make_node("n3", "metric", "m3", metadata={}),
        ]
        result = engine.analyze_trends("metric_name")
        assert result == {"trend": "insufficient_values", "confidence": 0.0}

    def test_stable_trend(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # 6 identical values → diff = 0 → stable
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": "10.0"}, timestamp=float(i))
            for i in range(6)
        ]
        result = engine.analyze_trends("metric_name")
        assert result["trend"] == "stable"
        assert result["sample_size"] == 6
        assert result["change_rate"] == 0.0

    def test_increasing_trend(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # values rise from 1..6
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        result = engine.analyze_trends("metric_name")
        assert result["trend"] == "increasing"
        assert result["sample_size"] == 6
        assert result["change_rate"] > 0

    def test_decreasing_trend(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # values fall from 6..1
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(6 - i)}, timestamp=float(i))
            for i in range(6)
        ]
        result = engine.analyze_trends("metric_name")
        assert result["trend"] == "decreasing"
        assert result["sample_size"] == 6
        assert result["change_rate"] < 0

    def test_window_size_limits_data(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # 10 values, window=3 → only last 3 used
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(10)
        ]
        result = engine.analyze_trends("metric_name", window_size=3)
        assert result["sample_size"] == 3

    def test_confidence_calculation_with_variance(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # stable high values → low variance → high confidence
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": "100.0"}, timestamp=float(i))
            for i in range(6)
        ]
        result = engine.analyze_trends("metric_name")
        assert result["trend"] == "stable"
        # variance is 0, mean is 100 → confidence = 1.0 - 0 / (100 + 0.001) ≈ 1.0
        assert result["confidence"] > 0.99

    def test_statistics_error_fallback(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # len(values) >= 3, but patch variance to raise
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        with patch.object(statistics, "variance", side_effect=statistics.StatisticsError("err")):
            result = engine.analyze_trends("metric_name")
        assert result["trend"] in ("increasing", "decreasing", "stable")
        assert result["confidence"] == 0.5

    def test_zero_first_half_threshold(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # first_half mean is 0 → threshold should be 0.01
        values = [0.0, 0.0, 0.0, 0.05, 0.05, 0.05]
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(v)}, timestamp=float(i))
            for i, v in enumerate(values)
        ]
        result = engine.analyze_trends("metric_name")
        # diff = 0.05 - 0.0 = 0.05 > 0.01 → increasing
        assert result["trend"] == "increasing"

    def test_non_metric_nodes_filtered(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # query returns mixed types, only metrics count toward the 3-node minimum
        mock_kg.query.return_value = [
            _make_node("n1", "finding", "f1"),
            _make_node("n2", "finding", "f2"),
            _make_node("n3", "metric", "m1", metadata={"value": "1.0"}),
        ]
        result = engine.analyze_trends("metric_name")
        assert result == {"trend": "insufficient_data", "confidence": 0.0}

    def test_sorting_by_timestamp(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # nodes out of order; should sort before slicing
        mock_kg.query.return_value = [
            _make_node("n3", "metric", "m", metadata={"value": "3.0"}, timestamp=3.0),
            _make_node("n1", "metric", "m", metadata={"value": "1.0"}, timestamp=1.0),
            _make_node("n2", "metric", "m", metadata={"value": "2.0"}, timestamp=2.0),
            _make_node("n4", "metric", "m", metadata={"value": "4.0"}, timestamp=4.0),
            _make_node("n5", "metric", "m", metadata={"value": "5.0"}, timestamp=5.0),
            _make_node("n6", "metric", "m", metadata={"value": "6.0"}, timestamp=6.0),
        ]
        result = engine.analyze_trends("metric_name", window_size=3)
        # recent = [4,5,6] → increasing
        assert result["trend"] == "increasing"
        assert result["sample_size"] == 3


# ---------------------------------------------------------------------------
# 4. detect_contradictions
# ---------------------------------------------------------------------------

class TestDetectContradictions:
    def test_no_findings(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {}
        assert engine.detect_contradictions() == []

    def test_single_finding_no_contradiction(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "system improves"),
        }
        assert engine.detect_contradictions() == []

    def test_related_and_opposing(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "the performance increases"),
            "f2": _make_node("f2", "finding", "the performance decreases"),
        }
        alerts = engine.detect_contradictions()
        assert len(alerts) == 1
        assert alerts[0].severity == "medium"
        assert "f1" in alerts[0].conflicting_nodes
        assert "f2" in alerts[0].conflicting_nodes
        assert alerts[0].recommendation == "运行针对性实验解决矛盾"

    def test_not_related(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "aaa bbb ccc increases"),
            "f2": _make_node("f2", "finding", "xxx yyy zzz decreases"),
        }
        assert engine.detect_contradictions() == []

    def test_related_but_not_opposing(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "performance increases"),
            "f2": _make_node("f2", "finding", "performance improves"),
        }
        assert engine.detect_contradictions() == []

    def test_multiple_contradictions(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "the a increases stable"),
            "f2": _make_node("f2", "finding", "the a decreases unstable"),
            "f3": _make_node("f3", "finding", "the b converges positive"),
            "f4": _make_node("f4", "finding", "the b diverges negative"),
        }
        alerts = engine.detect_contradictions()
        # f1-f2 and f3-f4 are each one pair
        assert len(alerts) == 2


# ---------------------------------------------------------------------------
# 5. generate_hypotheses
# ---------------------------------------------------------------------------

class TestGenerateHypotheses:
    def test_metric_pairs_above_threshold(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # Three findings with the same metric pair → count == 3
        mock_kg._nodes = {
            f"f{i}": _make_node(
                f"f{i}",
                "finding",
                "finding",
                metadata={"metrics": ["m1", "m2"]},
            )
            for i in range(3)
        }
        hyps = engine.generate_hypotheses()
        pair_hyps = [h for h in hyps if "m1" in h.hypothesis and "m2" in h.hypothesis]
        assert len(pair_hyps) == 1
        assert pair_hyps[0].testable is True
        assert pair_hyps[0].suggested_experiment == "controlled_experiment_m1_m2"

    def test_metric_pairs_below_threshold(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # Only two findings with the same metric pair → count == 2 (< 3)
        mock_kg._nodes = {
            f"f{i}": _make_node(
                f"f{i}",
                "finding",
                "finding",
                metadata={"metrics": ["m1", "m2"]},
            )
            for i in range(2)
        }
        hyps = engine.generate_hypotheses()
        pair_hyps = [h for h in hyps if "m1" in h.hypothesis and "m2" in h.hypothesis]
        assert len(pair_hyps) == 0

    def test_trend_increasing_hypothesis(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # Inject a strong increasing trend for "convergence_rate"
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        with patch.object(engine, "analyze_trends", return_value={
            "trend": "increasing", "confidence": 0.95
        }):
            hyps = engine.generate_hypotheses()
        trend_hyps = [h for h in hyps if "convergence_rate" in h.hypothesis]
        assert len(trend_hyps) >= 1
        assert trend_hyps[0].testable is True
        assert "verify_convergence_rate_trend" in trend_hyps[0].suggested_experiment

    def test_trend_decreasing_hypothesis(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        with patch.object(engine, "analyze_trends", return_value={
            "trend": "decreasing", "confidence": 0.95
        }):
            hyps = engine.generate_hypotheses()
        trend_hyps = [h for h in hyps if "退化" in h.hypothesis or "degradation" in h.suggested_experiment]
        assert len(trend_hyps) >= 1

    def test_trend_insufficient_data_no_hypothesis(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        with patch.object(engine, "analyze_trends", return_value={
            "trend": "insufficient_data", "confidence": 0.0
        }):
            hyps = engine.generate_hypotheses()
        # No trend-based hypotheses should be generated for insufficient_data
        assert not any("呈现持续改善趋势" in h.hypothesis or "正在退化" in h.hypothesis for h in hyps)

    def test_trend_low_confidence_no_hypothesis(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        with patch.object(engine, "analyze_trends", return_value={
            "trend": "increasing", "confidence": 0.3
        }):
            hyps = engine.generate_hypotheses()
        assert not any("呈现持续改善趋势" in h.hypothesis for h in hyps)

    def test_contradiction_hypotheses(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "the performance increases"),
            "f2": _make_node("f2", "finding", "the performance decreases"),
        }
        hyps = engine.generate_hypotheses()
        contradiction_hyps = [h for h in hyps if "矛盾" in h.hypothesis or "需要解决" in h.hypothesis]
        assert len(contradiction_hyps) == 1
        assert contradiction_hyps[0].testable is True
        assert contradiction_hyps[0].suggested_experiment == "contradiction_resolution"

    def test_contradiction_hypotheses_limited_to_three(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        # Create 5 contradictions; only top 3 should yield hypotheses
        nodes = {}
        for i in range(5):
            nodes[f"f{i}a"] = _make_node(f"f{i}a", "finding", f"the topic{i} increases")
            nodes[f"f{i}b"] = _make_node(f"f{i}b", "finding", f"the topic{i} decreases")
        mock_kg._nodes = nodes
        hyps = engine.generate_hypotheses()
        contradiction_hyps = [h for h in hyps if h.suggested_experiment == "contradiction_resolution"]
        assert len(contradiction_hyps) == 3

    def test_metric_pairs_and_trends_combined(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "f", metadata={"metrics": ["a", "b"]}),
            "f2": _make_node("f2", "finding", "f", metadata={"metrics": ["a", "b"]}),
            "f3": _make_node("f3", "finding", "f", metadata={"metrics": ["a", "b"]}),
        }
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        with patch.object(engine, "analyze_trends", return_value={
            "trend": "increasing", "confidence": 0.95
        }):
            hyps = engine.generate_hypotheses()
        assert len(hyps) >= 2  # at least one from pairs + at least one from trends


# ---------------------------------------------------------------------------
# 6. _are_related
# ---------------------------------------------------------------------------

class TestAreRelated:
    def test_share_two_keywords(self) -> None:
        n1 = _make_node("n1", "finding", "alpha beta gamma")
        n2 = _make_node("n2", "finding", "alpha beta delta")
        assert DiscoveryEngine._are_related(None, n1, n2) is True

    def test_share_one_keyword(self) -> None:
        n1 = _make_node("n1", "finding", "alpha beta gamma")
        n2 = _make_node("n2", "finding", "alpha delta epsilon")
        assert DiscoveryEngine._are_related(None, n1, n2) is False

    def test_share_no_keywords(self) -> None:
        n1 = _make_node("n1", "finding", "alpha beta")
        n2 = _make_node("n2", "finding", "gamma delta")
        assert DiscoveryEngine._are_related(None, n1, n2) is False

    def test_case_insensitive(self) -> None:
        n1 = _make_node("n1", "finding", "Alpha Beta")
        n2 = _make_node("n2", "finding", "alpha beta")
        assert DiscoveryEngine._are_related(None, n1, n2) is True

    def test_punctuation_not_stripped(self) -> None:
        # The implementation splits on whitespace only, so "beta," is a different token
        n1 = _make_node("n1", "finding", "alpha beta,")
        n2 = _make_node("n2", "finding", "alpha beta")
        # Only "alpha" is shared (< 2) because punctuation prevents "beta," == "beta"
        assert DiscoveryEngine._are_related(None, n1, n2) is False


# ---------------------------------------------------------------------------
# 7. _are_opposing
# ---------------------------------------------------------------------------

class TestAreOpposing:
    def test_increases_decreases(self) -> None:
        n1 = _make_node("n1", "finding", "increases")
        n2 = _make_node("n2", "finding", "decreases")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_improves_degrades(self) -> None:
        n1 = _make_node("n1", "finding", "improves")
        n2 = _make_node("n2", "finding", "degrades")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_stable_unstable(self) -> None:
        n1 = _make_node("n1", "finding", "stable")
        n2 = _make_node("n2", "finding", "unstable")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_converges_diverges(self) -> None:
        n1 = _make_node("n1", "finding", "converges")
        n2 = _make_node("n2", "finding", "diverges")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_positive_negative(self) -> None:
        n1 = _make_node("n1", "finding", "positive")
        n2 = _make_node("n2", "finding", "negative")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_reversed_order(self) -> None:
        n1 = _make_node("n1", "finding", "decreases")
        n2 = _make_node("n2", "finding", "increases")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_no_opposites(self) -> None:
        n1 = _make_node("n1", "finding", "hello world")
        n2 = _make_node("n2", "finding", "foo bar")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is False

    def test_case_insensitive(self) -> None:
        n1 = _make_node("n1", "finding", "INCREASES")
        n2 = _make_node("n2", "finding", "Decreases")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is True

    def test_partial_match_not_opposing(self) -> None:
        # "increases" and "increases" are not opposing
        n1 = _make_node("n1", "finding", "increases")
        n2 = _make_node("n2", "finding", "increases")
        assert DiscoveryEngine._are_opposing(None, n1, n2) is False


# ---------------------------------------------------------------------------
# 8. _find_metric_pairs
# ---------------------------------------------------------------------------

class TestFindMetricPairs:
    def test_single_finding_with_metrics(self, engine: DiscoveryEngine) -> None:
        findings = [
            _make_node("f1", "finding", "f", metadata={"metrics": ["a", "b"]}),
        ]
        result = engine._find_metric_pairs(findings)
        assert result == [("a", "b", 1)]

    def test_multiple_findings_same_pair(self, engine: DiscoveryEngine) -> None:
        findings = [
            _make_node("f1", "finding", "f", metadata={"metrics": ["a", "b"]}),
            _make_node("f2", "finding", "f", metadata={"metrics": ["b", "a"]}),
            _make_node("f3", "finding", "f", metadata={"metrics": ["a", "b"]}),
        ]
        result = engine._find_metric_pairs(findings)
        assert result == [("a", "b", 3)]

    def test_no_metrics_key(self, engine: DiscoveryEngine) -> None:
        findings = [_make_node("f1", "finding", "f", metadata={})]
        assert engine._find_metric_pairs(findings) == []

    def test_single_metric(self, engine: DiscoveryEngine) -> None:
        findings = [_make_node("f1", "finding", "f", metadata={"metrics": ["a"]})]
        assert engine._find_metric_pairs(findings) == []

    def test_limit_to_ten(self, engine: DiscoveryEngine) -> None:
        # Create 15 distinct pairs, only top 10 returned
        findings = []
        for i in range(15):
            findings.append(
                _make_node(f"f{i}", "finding", "f", metadata={"metrics": [f"m{i}", f"m{i+1}"]})
            )
        result = engine._find_metric_pairs(findings)
        assert len(result) == 10
        # Each pair appears once
        for r in result:
            assert r[2] == 1

    def test_empty_findings(self, engine: DiscoveryEngine) -> None:
        assert engine._find_metric_pairs([]) == []

    def test_three_metrics_all_pairs(self, engine: DiscoveryEngine) -> None:
        findings = [
            _make_node("f1", "finding", "f", metadata={"metrics": ["a", "b", "c"]}),
        ]
        result = engine._find_metric_pairs(findings)
        # sorted pairs: (a,b), (a,c), (b,c)
        assert set(result) == {("a", "b", 1), ("a", "c", 1), ("b", "c", 1)}


# ---------------------------------------------------------------------------
# 9. get_insights
# ---------------------------------------------------------------------------

class TestGetInsights:
    def test_trend_insight(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        insights = engine.get_insights()
        assert any("收敛率" in ins for ins in insights)

    def test_contradiction_insight(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "the performance increases"),
            "f2": _make_node("f2", "finding", "the performance decreases"),
        }
        insights = engine.get_insights()
        assert any("矛盾" in ins for ins in insights)
        assert any("1 个矛盾" in ins for ins in insights)

    def test_open_questions_insight(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.get_open_questions.return_value = [
            _make_node("h1", "hypothesis", "h", confidence=0.5),
            _make_node("h2", "hypothesis", "h", confidence=0.5),
        ]
        insights = engine.get_insights()
        assert any("假设待验证" in ins for ins in insights)
        assert any("2 个假设待验证" in ins for ins in insights)

    def test_no_insights(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = []
        mock_kg._nodes = {}
        mock_kg.get_open_questions.return_value = []
        insights = engine.get_insights()
        assert insights == []

    def test_combined_insights(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": str(i + 1)}, timestamp=float(i))
            for i in range(6)
        ]
        mock_kg._nodes = {
            "f1": _make_node("f1", "finding", "the a increases"),
            "f2": _make_node("f2", "finding", "the a decreases"),
        }
        mock_kg.get_open_questions.return_value = [_make_node("h1", "hypothesis", "h", confidence=0.5)]
        insights = engine.get_insights()
        assert len(insights) == 3
        assert any("收敛率" in ins for ins in insights)
        assert any("矛盾" in ins for ins in insights)
        assert any("假设待验证" in ins for ins in insights)

    def test_stable_trend_insight(self, engine: DiscoveryEngine, mock_kg: MagicMock) -> None:
        mock_kg.query.return_value = [
            _make_node(f"n{i}", "metric", "m", metadata={"value": "5.0"}, timestamp=float(i))
            for i in range(6)
        ]
        insights = engine.get_insights()
        assert any("stable" in ins or "收敛率" in ins for ins in insights)
