"""Tests for evaluation-to-PERCV feedback loop."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.percv.feedback_loop import (
    EvalToResearchFeedback,
    FeedbackPriority,
    ResearchDirection,
)


class TestFeedbackPriority:
    def test_priority_values(self):
        assert FeedbackPriority.CRITICAL.value == "critical"
        assert FeedbackPriority.HIGH.value == "high"
        assert FeedbackPriority.MEDIUM.value == "medium"
        assert FeedbackPriority.LOW.value == "low"


class TestResearchDirection:
    def test_direction_creation(self):
        d = ResearchDirection(
            topic="Improve multi-agent coordination",
            priority=FeedbackPriority.HIGH,
            source="eval_layer5",
            score_gap=20.0,
            rationale="MAS Dimension score below threshold",
        )
        assert d.topic == "Improve multi-agent coordination"
        assert d.priority == FeedbackPriority.HIGH
        assert d.score_gap == 20.0

    def test_to_dict(self):
        d = ResearchDirection(
            topic="Test topic",
            priority=FeedbackPriority.LOW,
            source="test",
            score_gap=5.0,
        )
        result = d.to_dict()
        assert result["topic"] == "Test topic"
        assert result["priority"] == "low"


class TestEvalToResearchFeedback:
    def test_create_with_eval_observer(self):
        eval_obs = MagicMock()
        fb = EvalToResearchFeedback(eval_observer=eval_obs)
        assert fb.eval_observer is eval_obs
        assert len(fb.directions) == 0

    def test_generate_from_full_run_report(self):
        report = MagicMock()
        report.layers = [
            MagicMock(layer_number=1, score=100.0),
            MagicMock(layer_number=2, score=90.0),
            MagicMock(layer_number=3, score=70.0),
            MagicMock(layer_number=4, score=60.0),
            MagicMock(layer_number=5, score=45.0),
        ]
        report.mas_dimension_score = 45.0

        fb = EvalToResearchFeedback()
        directions = fb.generate_from_report(report)

        assert len(directions) >= 1
        mas_directions = [d for d in directions if "MAS" in d.source]
        assert len(mas_directions) >= 1
        assert mas_directions[0].priority == FeedbackPriority.CRITICAL

    def test_generate_with_all_high_scores(self):
        report = MagicMock()
        report.layers = [
            MagicMock(layer_number=n, score=95.0)
            for n in range(1, 6)
        ]
        report.mas_dimension_score = 95.0

        fb = EvalToResearchFeedback()
        directions = fb.generate_from_report(report)

        low_priority = [d for d in directions if d.priority == FeedbackPriority.LOW]
        assert len(low_priority) == 5

    def test_generate_from_quality_gate_failure(self):
        qg_result = MagicMock()
        qg_result.verdict.value = "rejected"
        qg_result.score = 55.0
        qg_result.cycle_id = "c1"
        qg_result.reason = "Score below threshold"

        fb = EvalToResearchFeedback()
        directions = fb.generate_from_quality_gate(qg_result)

        assert len(directions) >= 1
        assert directions[0].priority == FeedbackPriority.CRITICAL
        assert "quality_gate" in directions[0].source

    def test_generate_from_eval_history(self):
        eval_obs = MagicMock()
        eval_obs.get_eval_history.return_value = [
            {"agent_id": "a1", "score": 80.0, "mas_score": 75.0, "status": "PASS"},
            {"agent_id": "a1", "score": 65.0, "mas_score": 50.0, "status": "FAIL"},
            {"agent_id": "a1", "score": 55.0, "mas_score": 40.0, "status": "FAIL"},
        ]

        fb = EvalToResearchFeedback(eval_observer=eval_obs)
        directions = fb.generate_from_history("a1")

        assert len(directions) >= 1
        assert directions[0].priority in (FeedbackPriority.HIGH, FeedbackPriority.CRITICAL)

    def test_get_all_directions(self):
        fb = EvalToResearchFeedback()
        fb.directions = [
            ResearchDirection("t1", FeedbackPriority.HIGH, "src", 10.0),
            ResearchDirection("t2", FeedbackPriority.LOW, "src", 5.0),
        ]
        all_dirs = fb.get_all_directions()
        assert len(all_dirs) == 2

    def test_clear_directions(self):
        fb = EvalToResearchFeedback()
        fb.directions = [ResearchDirection("t1", FeedbackPriority.HIGH, "src", 10.0)]
        fb.clear_directions()
        assert len(fb.directions) == 0

    def test_summary(self):
        fb = EvalToResearchFeedback()
        fb.directions = [
            ResearchDirection("t1", FeedbackPriority.CRITICAL, "src1", 30.0),
            ResearchDirection("t2", FeedbackPriority.HIGH, "src2", 20.0),
            ResearchDirection("t3", FeedbackPriority.LOW, "src3", 5.0),
        ]
        summary = fb.summary()
        assert summary["total"] == 3
        assert summary["by_priority"]["critical"] == 1
        assert summary["by_priority"]["high"] == 1
