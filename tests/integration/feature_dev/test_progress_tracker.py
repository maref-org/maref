from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.integration.feature_dev.feature_cycle import CycleSnapshot
from maref.integration.feature_dev.progress_tracker import (
    ConvergenceReport,
    LayerTrend,
    ProgressTracker,
    _direction,
)
from maref.integration.test_platform.schema import EvalStatus


class TestLayerTrend:
    def test_slope_with_two_scores(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[50.0, 80.0], direction="converging", current_gap=0.0
        )
        assert t.slope == 30.0

    def test_slope_single_score(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[50.0], direction="insufficient_data", current_gap=30.0
        )
        assert t.slope == 0.0

    def test_slope_decreasing(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[80.0, 60.0], direction="diverging", current_gap=20.0
        )
        assert t.slope == -20.0

    def test_is_on_track_single_score_above_60(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[65.0], direction="insufficient_data", current_gap=15.0
        )
        assert t.is_on_track is True

    def test_is_on_track_below_60(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[40.0], direction="insufficient_data", current_gap=40.0
        )
        assert t.is_on_track is False

    def test_is_on_track_declining_rapidly(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[80.0, 50.0], direction="diverging", current_gap=30.0
        )
        assert t.is_on_track is False  # slope=-30, < -2

    def test_is_on_track_declining_slowly(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[80.0, 79.0], direction="fluctuating", current_gap=1.0
        )
        assert t.is_on_track is True  # slope=-1, >= -2

    def test_convergence_ratio_improving(self) -> None:
        t = LayerTrend(
            layer_name="SA",
            scores=[40.0, 50.0, 60.0, 80.0],
            direction="converging",
            current_gap=0.0,
        )
        ratio = t.convergence_ratio
        assert ratio >= 1.0

    def test_convergence_ratio_fewer_than_3(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[40.0, 80.0], direction="converging", current_gap=0.0
        )
        assert t.convergence_ratio == 1.0

    def test_empty_scores_is_on_track_false(self) -> None:
        t = LayerTrend(
            layer_name="SA", scores=[], direction="insufficient_data", current_gap=80.0
        )
        assert t.is_on_track is False


class TestConvergenceReport:
    def test_avg_score(self) -> None:
        report = ConvergenceReport(
            feature_name="Test",
            total_cycles=3,
            total_duration_seconds=30.0,
            overall_trend="converging",
            layer_trends=[
                LayerTrend("SA", [80.0, 85.0, 90.0], "converging", 0.0),
                LayerTrend("RA", [70.0, 75.0, 80.0], "converging", 0.0),
            ],
            deploy_ready=True,
            deploy_gates={"g1": True},
            recommendations=["All good"],
        )
        assert report.avg_score == 85.0

    def test_avg_score_no_trends(self) -> None:
        report = ConvergenceReport(
            feature_name="Test",
            total_cycles=0,
            total_duration_seconds=0.0,
            overall_trend="insufficient_data",
            layer_trends=[],
            deploy_ready=False,
            deploy_gates={},
            recommendations=["N/A"],
        )
        assert report.avg_score == 0.0

    def test_to_dict_structure(self) -> None:
        report = ConvergenceReport(
            feature_name="F",
            total_cycles=5,
            total_duration_seconds=100.0,
            overall_trend="converging",
            layer_trends=[
                LayerTrend("SA", [60.0, 70.0, 80.0], "converging", 0.0),
            ],
            deploy_ready=True,
            deploy_gates={"g1": True, "g2": True},
            recommendations=["Good"],
            cycle_scores=[60.0, 70.0, 80.0],
            final_decision="go",
            budget_spent=500.0,
            content_stats={"characters": 3, "scripts": 5},
        )
        d = report.to_dict()
        assert d["feature_name"] == "F"
        assert d["total_cycles"] == 5
        assert d["overall_trend"] == "converging"
        assert d["avg_score"] == 80.0
        assert d["final_decision"] == "go"
        assert d["budget_spent"] == 500.0
        assert d["content_stats"]["characters"] == 3
        assert len(d["layer_trends"]) == 1


class TestDirection:
    def test_converging(self) -> None:
        assert _direction([50.0, 60.0, 70.0, 80.0]) == "converging"

    def test_diverging(self) -> None:
        assert _direction([80.0, 70.0, 60.0, 50.0]) == "diverging"

    def test_fluctuating(self) -> None:
        assert _direction([50.0, 80.0, 40.0, 90.0]) == "fluctuating"

    def test_insufficient_data(self) -> None:
        assert _direction([]) == "insufficient_data"
        assert _direction([80.0]) == "insufficient_data"


def _make_snap(
    number: int,
    scores: dict[str, float],
    overall: float,
    status: EvalStatus = EvalStatus.CONDITIONAL,
    verdict: str = "pending",
    feedback: str = "",
    duration: float = 1.0,
    artifacts: dict | None = None,
    go_nogo: str = "monitoring",
    budget: float = 0.0,
) -> CycleSnapshot:
    return CycleSnapshot(
        cycle_number=number,
        topic="T",
        layer_scores=scores,
        overall_score=overall,
        overall_status=status,
        verdict=verdict,
        feedback_injected=feedback,
        duration_seconds=duration,
        artifacts=artifacts or {},
        go_nogo_decision=go_nogo,
        budget_used=budget,
    )


class TestProgressTracker:
    def test_empty_report(self) -> None:
        tracker = ProgressTracker(feature_name="Empty")
        report = tracker.generate_report()
        assert report.feature_name == "Empty"
        assert report.total_cycles == 0
        assert report.deploy_ready is False

    def test_single_snapshot(self) -> None:
        tracker = ProgressTracker(feature_name="Single")
        tracker.add_snapshot(
            _make_snap(
                1,
                {"SA": 80.0, "RA": 70.0},
                overall=75.0,
                go_nogo="monitoring",
            )
        )
        report = tracker.generate_report()
        assert report.total_cycles == 1
        assert len(report.layer_trends) == 2

    def test_multiple_snapshots(self) -> None:
        tracker = ProgressTracker(feature_name="Multi")
        for i in range(3):
            tracker.add_snapshot(
                _make_snap(
                    i + 1,
                    {"SA": float(60 + i * 10), "RA": float(50 + i * 10)},
                    overall=float(55 + i * 10),
                    go_nogo="monitoring" if i < 2 else "CONTINUE",
                    budget=float(i * 100),
                )
            )
        report = tracker.generate_report()
        assert report.total_cycles == 3
        assert len(report.cycle_scores) == 3
        assert report.budget_spent == 300.0

    def test_deploy_ready_when_all_gates_pass(self) -> None:
        tracker = ProgressTracker(feature_name="Ready")
        for i in range(3):
            tracker.add_snapshot(
                _make_snap(
                    i + 1,
                    {"Static Audit": 80.0, "Reasoning Metrics": 80.0},
                    overall=(80.0 + 80.0 + 10.0 * i),  # ensures last >= 80
                )
            )
        report = tracker.generate_report()
        assert report.deploy_ready is True

    def test_generates_recommendations_for_gaps(self) -> None:
        tracker = ProgressTracker(feature_name="Gaps")
        tracker.add_snapshot(
            _make_snap(
                1,
                {"Static Audit": 30.0, "MAS Dimensions": 20.0},
                overall=25.0,
            )
        )
        report = tracker.generate_report()
        assert len(report.recommendations) > 0
        sa_recs = [r for r in report.recommendations if "Static Audit" in r]
        mas_recs = [r for r in report.recommendations if "MAS Dimensions" in r]
        assert len(sa_recs) > 0
        assert len(mas_recs) > 0

    def test_content_stats(self) -> None:
        tracker = ProgressTracker(feature_name="Stats")
        tracker.add_snapshot(
            _make_snap(
                1,
                {"SA": 80.0},
                overall=80.0,
                artifacts={
                    "characters": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                    "scripts": [{"title": "S1"}, {"title": "S2"}],
                    "stages_covered": {"mvp", "mixed"},
                    "requirements_covered": 12,
                },
            )
        )
        report = tracker.generate_report()
        assert report.content_stats["characters"] == 3
        assert report.content_stats["scripts"] == 2
        assert report.content_stats["reqs_covered"] == 12

    def test_final_decision_from_last_snapshot(self) -> None:
        tracker = ProgressTracker(feature_name="Final")
        tracker.add_snapshot(
            _make_snap(1, {"SA": 50.0}, overall=50.0, go_nogo="monitoring")
        )
        tracker.add_snapshot(
            _make_snap(2, {"SA": 85.0}, overall=85.0, go_nogo="GO (score=85.0)")
        )
        report = tracker.generate_report()
        assert report.final_decision == "GO (score=85.0)"

    def test_missing_layer_scores_handled(self) -> None:
        tracker = ProgressTracker(feature_name="Partial")
        tracker.add_snapshot(
            _make_snap(1, {"SA": 80.0}, overall=80.0)
        )
        tracker.add_snapshot(
            _make_snap(2, {"SA": 85.0, "RA": 90.0}, overall=87.5)
        )
        report = tracker.generate_report()
        # Layer names from last snapshot: SA, RA
        assert len(report.layer_trends) == 2
        # SA trend should have 2 entries
        sa_trend = [t for t in report.layer_trends if t.layer_name == "SA"][0]
        assert len(sa_trend.scores) == 2

    def test_layer_trend_current_gap(self) -> None:
        tracker = ProgressTracker(feature_name="Gap")
        tracker.add_snapshot(
            _make_snap(1, {"SA": 40.0}, overall=40.0)
        )
        report = tracker.generate_report()
        sa_trend = [t for t in report.layer_trends if t.layer_name == "SA"][0]
        assert sa_trend.current_gap == 40.0  # 80 - 40
