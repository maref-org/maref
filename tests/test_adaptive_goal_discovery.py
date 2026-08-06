"""Tests for AdaptiveGoalDiscoverer."""

from maref.learning.adaptive_goal_discovery import (
    AdaptiveGoalDiscoverer, ImprovementGoal, GoalDiscoveryReport,
)


class TestAdaptiveGoalDiscoverer:
    def test_discover_from_scores(self):
        discoverer = AdaptiveGoalDiscoverer(min_score_threshold=70.0)
        scores = {"correctness": 85.0, "testing": 55.0, "security": 90.0}
        goals = discoverer.discover_from_scores(scores)
        assert len(goals) == 1
        assert goals[0].dimension == "testing"
        assert goals[0].priority == 1  # 55 < 70*0.8 = 56

    def test_discover_from_scores_medium_priority(self):
        discoverer = AdaptiveGoalDiscoverer(min_score_threshold=70.0)
        scores = {"code_quality": 60.0}  # 60 >= 56 so priority 2
        goals = discoverer.discover_from_scores(scores)
        assert len(goals) == 1
        assert goals[0].priority == 2

    def test_no_goals_if_all_above_threshold(self):
        discoverer = AdaptiveGoalDiscoverer(min_score_threshold=70.0)
        scores = {"correctness": 95.0, "testing": 80.0}
        goals = discoverer.discover_from_scores(scores)
        assert len(goals) == 0

    def test_discover_from_conflicts(self):
        discoverer = AdaptiveGoalDiscoverer()
        conflicts = [
            {"dimension_a": "correctness", "dimension_b": "performance"},
        ]
        goals = discoverer.discover_from_conflicts(conflicts)
        assert len(goals) == 1
        assert "conflict" in goals[0].name.lower()

    def test_discover_from_trends(self):
        discoverer = AdaptiveGoalDiscoverer()
        trends = {"testing": [80.0, 75.0, 70.0]}
        goals = discoverer.discover_from_trends(trends)
        assert len(goals) == 1
        assert "decline" in goals[0].name.lower()

    def test_no_trend_if_not_consistently_declining(self):
        discoverer = AdaptiveGoalDiscoverer()
        trends = {"testing": [70.0, 80.0, 75.0]}
        goals = discoverer.discover_from_trends(trends)
        assert len(goals) == 0

    def test_discover_all_combined(self):
        discoverer = AdaptiveGoalDiscoverer(max_goals_per_run=10)
        report = discoverer.discover_all(
            scores={"testing": 55.0, "security": 90.0},
            conflicts=[{"dimension_a": "correctness", "dimension_b": "performance"}],
            trends={"code_quality": [85.0, 80.0, 75.0]},
        )
        assert report.total_discovered >= 1
        assert len(report.dimensions_covered) >= 1

    def test_max_goals_limit(self):
        discoverer = AdaptiveGoalDiscoverer(max_goals_per_run=2)
        scores = {f"dim{i}": 50.0 for i in range(10)}
        goals = discoverer.discover_from_scores(scores)
        assert len(goals) <= 2

    def test_cooldown_prevents_duplicates(self):
        discoverer = AdaptiveGoalDiscoverer()
        scores1 = {"testing": 55.0}
        goals1 = discoverer.discover_from_scores(scores1)
        assert len(goals1) == 1

        goals2 = discoverer.discover_from_scores(scores1)
        assert len(goals2) == 0  # Cooldown active

    def test_clear_cooldown(self):
        discoverer = AdaptiveGoalDiscoverer()
        discoverer.discover_from_scores({"testing": 55.0})
        discoverer.clear_cooldown()
        goals = discoverer.discover_from_scores({"testing": 55.0})
        assert len(goals) == 1

    def test_report_structure(self):
        report = GoalDiscoveryReport(
            goals=[ImprovementGoal(
                name="Test goal", dimension="testing",
                current_score=50.0, target_score=70.0,
                priority=1, source="test", rationale="test",
            )],
            total_discovered=1,
            dimensions_covered=["testing"],
            generated_at="2026-07-02T12:00:00",
        )
        d = report.goals[0]
        assert d.name == "Test goal"
        assert d.priority == 1
        assert d.status == "proposed"
