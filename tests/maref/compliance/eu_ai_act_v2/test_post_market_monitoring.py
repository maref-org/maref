from __future__ import annotations

from maref.compliance.eu_ai_act_v2.post_market_monitoring import (
    PMMManager,
    PMMObservation,
    PMMPlan,
    PMMTrendAnalysis,
    PeriodicReport,
    _compute_slope,
)


class TestPMMPlan:
    def test_defaults(self) -> None:
        plan = PMMPlan(
            plan_id="p1",
            system_name="MAREF",
            system_version="1.0",
            monitoring_objectives=["accuracy"],
            data_sources=["logs"],
            kpis=[{"name": "latency", "threshold": 100}],
        )
        assert plan.plan_id == "p1"
        assert plan.system_name == "MAREF"
        assert plan.review_interval_days == 365
        assert plan.last_review_at == ""


class TestPMMObservation:
    def test_defaults(self) -> None:
        obs = PMMObservation(
            obs_id="o1",
            plan_id="p1",
            source="api",
            metric="latency",
            value=50.0,
        )
        assert obs.threshold is None
        assert obs.threshold_breached is False
        assert obs.timestamp == ""

    def test_breach(self) -> None:
        obs = PMMObservation(
            obs_id="o2",
            plan_id="p1",
            source="api",
            metric="latency",
            value=200.0,
            threshold=100.0,
            threshold_breached=True,
        )
        assert obs.threshold_breached is True


class TestPMMTrendAnalysis:
    def test_defaults(self) -> None:
        ta = PMMTrendAnalysis(
            period_start="2026-01-01",
            period_end="2026-06-30",
            metric_trends={"latency": {"slope": 0.5, "mean": 100.0}},
            thresholds_breached=["latency"],
            incident_correlation=[],
            overall_assessment="stable",
        )
        assert ta.overall_assessment == "stable"
        assert ta.metric_trends["latency"]["slope"] == 0.5


class TestPeriodicReport:
    def test_defaults(self) -> None:
        report = PeriodicReport(
            report_id="r1",
            plan_id="p1",
            period_start="2026-01-01",
            period_end="2026-06-30",
            observation_count=100,
        )
        assert report.trend_analysis is None
        assert report.incidents_in_period == []
        assert report.generated_at == ""


class TestComputeSlope:
    def test_ascending(self) -> None:
        slope = _compute_slope([1.0, 2.0, 3.0])
        assert slope == 1.0

    def test_descending(self) -> None:
        slope = _compute_slope([3.0, 2.0, 1.0])
        assert slope == -1.0

    def test_flat(self) -> None:
        slope = _compute_slope([5.0, 5.0, 5.0])
        assert slope == 0.0

    def test_single_value(self) -> None:
        assert _compute_slope([42.0]) == 0.0

    def test_empty(self) -> None:
        assert _compute_slope([]) == 0.0


class TestPMMManager:
    def test_init(self) -> None:
        mgr = PMMManager()
        assert mgr._plans == {}

    def test_create_plan(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            system_name="MAREF",
            objectives=["monitor accuracy"],
            data_sources=["api_logs"],
            kpis=[{"name": "accuracy", "threshold": 0.95}],
        )
        assert plan.system_name == "MAREF"
        assert plan.plan_id in mgr._plans

    def test_record_observation(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["src"], [{"name": "m", "threshold": 100}])
        obs = mgr.record_observation(
            plan_id=plan.plan_id,
            source="api",
            metric="latency",
            value=50.0,
        )
        assert obs.metric == "latency"
        assert obs.value == 50.0

    def test_record_observation_no_plan(self) -> None:
        mgr = PMMManager()
        obs = mgr.record_observation(
            plan_id="nonexistent",
            source="api",
            metric="latency",
            value=50.0,
        )
        assert obs is not None
        assert obs.plan_id == "nonexistent"

    def test_record_observation_breach(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["src"], [{"name": "latency", "threshold": 100.0}])
        obs = mgr.record_observation(
            plan_id=plan.plan_id,
            source="api",
            metric="latency",
            value=200.0,
            threshold=100.0,
        )
        assert obs.threshold_breached is True


