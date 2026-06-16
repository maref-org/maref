from __future__ import annotations

from maref.integration.feature_dev.feature_cycle import CycleSnapshot
from maref.integration.feature_dev.progress_tracker import (
    ConvergenceReport,
    LayerTrend,
    ProgressTracker,
    _direction,
)
from maref.integration.test_platform.schema import EvalStatus


class TestLayerTrend:
    def test_slope_two_points(self) -> None:
        lt = LayerTrend("Test", [50.0, 60.0], "converging", 20.0)
        assert lt.slope == 10.0

    def test_slope_single_point(self) -> None:
        lt = LayerTrend("Test", [50.0], "insufficient_data", 30.0)
        assert lt.slope == 0.0

    def test_slope_empty(self) -> None:
        lt = LayerTrend("Test", [], "insufficient_data", 80.0)
        assert lt.slope == 0.0

    def test_is_on_track_above_threshold(self) -> None:
        assert LayerTrend("Test", [60.0, 62.0], "converging", 18.0).is_on_track
        assert not LayerTrend("Test", [59.0], "insufficient_data", 21.0).is_on_track
        assert not LayerTrend("Test", [], "insufficient_data", 80.0).is_on_track

    def test_is_on_track_steep_drop(self) -> None:
        assert not LayerTrend("Test", [80.0, 60.0, 57.0], "diverging", 23.0).is_on_track

    def test_convergence_ratio_few_points(self) -> None:
        lt = LayerTrend("Test", [50.0], "insufficient_data", 30.0)
        assert lt.convergence_ratio == 1.0

    def test_convergence_ratio_many_points(self) -> None:
        lt = LayerTrend("Test", [50.0, 60.0, 70.0, 80.0], "converging", 0.0)
        assert lt.convergence_ratio > 1.0


class TestDirection:
    def test_converging(self) -> None:
        assert _direction([50, 55, 60, 65]) == "converging"

    def test_diverging(self) -> None:
        assert _direction([80, 70, 60, 50]) == "diverging"

    def test_fluctuating(self) -> None:
        assert _direction([50, 80, 40, 90]) == "fluctuating"

    def test_insufficient_data_single(self) -> None:
        assert _direction([50]) == "insufficient_data"

    def test_insufficient_data_empty(self) -> None:
        assert _direction([]) == "insufficient_data"


class TestProgressTracker:
    def _snap(self, score: float, layers: dict | None = None) -> CycleSnapshot:
        return CycleSnapshot(
            cycle_number=1,
            topic="t",
            layer_scores=layers or {"A": score},
            overall_score=score,
            overall_status=EvalStatus.CONDITIONAL,
            verdict="ok",
            feedback_injected="",
            duration_seconds=1.0,
            artifacts={"stages_covered": set()},
        )

    def test_empty_snapshots(self) -> None:
        pt = ProgressTracker("Test")
        r = pt.generate_report()
        assert r.total_cycles == 0
        assert r.avg_score == 0.0
        assert r.overall_trend == "insufficient_data"

    def test_single_snapshot(self) -> None:
        pt = ProgressTracker("Test")
        pt.add_snapshot(self._snap(75.0))
        r = pt.generate_report()
        assert r.total_cycles == 1
        assert r.avg_score == 75.0

    def test_full_report(self, sample_snapshot: CycleSnapshot) -> None:
        pt = ProgressTracker("Test Feature")
        pt.add_snapshot(sample_snapshot)
        pt.add_snapshot(sample_snapshot)
        r = pt.generate_report()
        assert r.total_cycles == 2
        assert r.feature_name == "Test Feature"
        assert len(r.layer_trends) == 5
        assert len(r.deploy_gates) == 3
        assert r.budget_spent == 200.0

    def test_report_generates_recommendations(self) -> None:
        pt = ProgressTracker("Test")
        snap = self._snap(50.0, {"Static Audit": 30.0})
        snap.artifacts = {
            "characters": [],
            "scripts": [],
            "stages_covered": set(),
            "requirements_covered": 0,
        }
        pt.add_snapshot(snap)
        r = pt.generate_report()
        assert len(r.recommendations) > 0
        assert any("Static Audit" in rec for rec in r.recommendations)

    def test_report_deploy_ready(self) -> None:
        pt = ProgressTracker("Test")
        snap = self._snap(90.0, {"A": 90.0, "B": 85.0, "C": 88.0, "D": 82.0, "E": 91.0})
        snap.artifacts = {
            "characters": [{"name": "A"}],
            "scripts": [{"title": "1"}],
            "stages_covered": {"mvp"},
            "requirements_covered": 1,
        }
        pt.add_snapshot(snap)
        r = pt.generate_report()
        assert r.deploy_gates["no_diverging_trends"]

    def test_content_stats_in_report(self) -> None:
        pt = ProgressTracker("Test")
        snap = self._snap(70.0)
        snap.artifacts = {
            "characters": [{"name": "A"}, {"name": "B"}],
            "scripts": [{"title": "1"}, {"title": "2"}, {"title": "3"}],
            "stages_covered": {"mvp", "mixed"},
            "requirements_covered": 5,
        }
        pt.add_snapshot(snap)
        r = pt.generate_report()
        assert r.content_stats["characters"] == 2
        assert r.content_stats["scripts"] == 3
        assert "mixed" in r.content_stats["stages_covered"]
        assert r.content_stats["reqs_covered"] == 5

    def test_final_decision_carried(self) -> None:
        pt = ProgressTracker("Test")
        snap = self._snap(40.0)
        snap.go_nogo_decision = "KILL"
        pt.add_snapshot(snap)
        r = pt.generate_report()
        assert r.final_decision == "KILL"

    def test_deploy_blocked_when_low(self) -> None:
        pt = ProgressTracker("Test")
        snap = self._snap(55.0, {"A": 55.0})
        snap.artifacts = {
            "characters": [{"name": "A"}],
            "scripts": [{"title": "1"}],
            "stages_covered": set(),
            "requirements_covered": 0,
        }
        pt.add_snapshot(snap)
        r = pt.generate_report()
        assert not r.deploy_ready
        assert any("blocked" in rec.lower() for rec in r.recommendations)


class TestConvergenceReport:
    def test_avg_score_empty(self) -> None:
        r = ConvergenceReport(
            feature_name="T",
            total_cycles=0,
            total_duration_seconds=0.0,
            overall_trend="insufficient_data",
            layer_trends=[],
            deploy_ready=False,
            deploy_gates={},
            recommendations=[],
        )
        assert r.avg_score == 0.0

    def test_to_dict(self) -> None:
        lt = LayerTrend("A", [70.0], "insufficient_data", 10.0)
        r = ConvergenceReport(
            feature_name="T",
            total_cycles=1,
            total_duration_seconds=10.0,
            overall_trend="converging",
            layer_trends=[lt],
            deploy_ready=True,
            deploy_gates={"g1": True},
            recommendations=["Good"],
            cycle_scores=[80.0],
            final_decision="GO",
            budget_spent=100.0,
            content_stats={"chars": 2},
        )
        d = r.to_dict()
        assert d["feature_name"] == "T"
        assert d["final_decision"] == "GO"
        assert len(d["layer_trends"]) == 1
