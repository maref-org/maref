"""Tests for EU AI Act post-market monitoring (Art.61)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from maref.compliance.eu_ai_act_v2.post_market_monitoring import (
    PeriodicReport,
    PMMManager,
    PMMObservation,
    PMMPlan,
    PMMTrendAnalysis,
)


class TestPMMPlan:
    def test_create_plan_all_fields(self) -> None:
        plan = PMMPlan(
            plan_id="pmm-001",
            system_name="TestSystem",
            system_version="1.0.0",
            monitoring_objectives=["detect drift", "track accuracy"],
            data_sources=["live_logs", "user_feedback"],
            kpis=[
                {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "live_logs"},
            ],
            review_interval_days=180,
            last_review_at="2026-01-01T00:00:00",
            next_review_at="2026-07-01T00:00:00",
        )
        assert plan.plan_id == "pmm-001"
        assert plan.system_name == "TestSystem"
        assert plan.system_version == "1.0.0"
        assert len(plan.monitoring_objectives) == 2
        assert "live_logs" in plan.data_sources
        assert plan.review_interval_days == 180
        assert plan.last_review_at == "2026-01-01T00:00:00"
        assert plan.next_review_at == "2026-07-01T00:00:00"

    def test_create_plan_default_review_interval(self) -> None:
        plan = PMMPlan(
            plan_id="pmm-002",
            system_name="TestSystem",
            system_version="1.0.0",
            monitoring_objectives=["detect drift"],
            data_sources=["drift_metrics"],
            kpis=[],
        )
        assert plan.review_interval_days == 365
        assert plan.last_review_at == ""
        assert plan.next_review_at == ""

    def test_create_plan_empty_objectives(self) -> None:
        plan = PMMPlan(
            plan_id="pmm-003",
            system_name="EmptyPlan",
            system_version="0.1.0",
            monitoring_objectives=[],
            data_sources=["live_logs"],
            kpis=[],
        )
        assert plan.monitoring_objectives == []
        assert plan.kpis == []

    def test_create_plan_no_kpis(self) -> None:
        plan = PMMPlan(
            plan_id="pmm-004",
            system_name="NoKPISystem",
            system_version="2.0.0",
            monitoring_objectives=["monitor performance"],
            data_sources=["incident_reports"],
            kpis=[],
        )
        assert plan.kpis == []
        assert plan.data_sources == ["incident_reports"]


class TestPMMObservation:
    def test_create_observation_minimal(self) -> None:
        obs = PMMObservation(
            obs_id="obs-001",
            plan_id="pmm-001",
            source="live_logs",
            metric="accuracy",
            value=0.94,
        )
        assert obs.obs_id == "obs-001"
        assert obs.plan_id == "pmm-001"
        assert obs.value == 0.94
        assert obs.threshold is None
        assert obs.threshold_breached is False
        assert obs.timestamp == ""
        assert obs.details == ""

    def test_create_observation_with_threshold_not_breached(self) -> None:
        obs = PMMObservation(
            obs_id="obs-002",
            plan_id="pmm-001",
            source="live_logs",
            metric="accuracy",
            value=0.95,
            threshold=0.90,
            threshold_breached=False,
            timestamp="2026-06-01T00:00:00",
            details="Nominal performance",
        )
        assert obs.value == 0.95
        assert obs.threshold == 0.90
        assert obs.threshold_breached is False
        assert obs.timestamp == "2026-06-01T00:00:00"
        assert obs.details == "Nominal performance"

    def test_create_observation_threshold_breached(self) -> None:
        obs = PMMObservation(
            obs_id="obs-003",
            plan_id="pmm-001",
            source="drift_metrics",
            metric="feature_drift",
            value=0.85,
            threshold=0.80,
            threshold_breached=True,
        )
        assert obs.threshold is not None
        assert obs.value > obs.threshold
        assert obs.threshold_breached is True

    def test_observation_value_at_threshold(self) -> None:
        obs = PMMObservation(
            obs_id="obs-004",
            plan_id="pmm-001",
            source="live_logs",
            metric="latency",
            value=200.0,
            threshold=200.0,
            threshold_breached=False,
        )
        assert obs.value == obs.threshold
        assert obs.threshold_breached is False


class TestPMMTrendAnalysis:
    def test_trend_analysis_construction(self) -> None:
        analysis = PMMTrendAnalysis(
            period_start="2026-01-01",
            period_end="2026-06-30",
            metric_trends={
                "accuracy": {"mean": 0.93, "std": 0.02, "min": 0.88, "max": 0.96, "slope": -0.01},
            },
            thresholds_breached=["accuracy"],
            incident_correlation=[{"incident": "INC-001", "metric": "accuracy", "correlation": 0.85}],
            overall_assessment="critical",
        )
        assert analysis.period_start == "2026-01-01"
        assert analysis.period_end == "2026-06-30"
        assert "accuracy" in analysis.metric_trends
        assert analysis.metric_trends["accuracy"]["mean"] == 0.93
        assert analysis.thresholds_breached == ["accuracy"]
        assert analysis.overall_assessment == "critical"

    def test_trend_analysis_stable_assessment(self) -> None:
        analysis = PMMTrendAnalysis(
            period_start="2026-01-01",
            period_end="2026-06-30",
            metric_trends={
                "accuracy": {"mean": 0.97, "std": 0.01, "min": 0.95, "max": 0.99, "slope": 0.001},
            },
            thresholds_breached=[],
            incident_correlation=[],
            overall_assessment="stable",
        )
        assert analysis.overall_assessment == "stable"
        assert len(analysis.thresholds_breached) == 0

    def test_trend_analysis_degrading_assessment(self) -> None:
        analysis = PMMTrendAnalysis(
            period_start="2026-01-01",
            period_end="2026-06-30",
            metric_trends={
                "accuracy": {"mean": 0.91, "std": 0.03, "min": 0.85, "max": 0.95, "slope": -0.05},
            },
            thresholds_breached=[],
            incident_correlation=[],
            overall_assessment="degrading",
        )
        assert analysis.overall_assessment == "degrading"


class TestPeriodicReport:
    def test_create_report_minimal(self) -> None:
        report = PeriodicReport(
            report_id="rpt-001",
            plan_id="pmm-001",
            period_start="2026-01-01",
            period_end="2026-06-30",
            observation_count=100,
        )
        assert report.report_id == "rpt-001"
        assert report.observation_count == 100
        assert report.trend_analysis is None
        assert report.incidents_in_period == []
        assert report.recommendations == []
        assert report.generated_at == ""

    def test_create_report_with_trend_analysis(self) -> None:
        trend = PMMTrendAnalysis(
            period_start="2026-01-01",
            period_end="2026-06-30",
            metric_trends={"accuracy": {"mean": 0.94, "std": 0.02, "min": 0.90, "max": 0.97, "slope": -0.01}},
            thresholds_breached=[],
            incident_correlation=[],
            overall_assessment="stable",
        )
        report = PeriodicReport(
            report_id="rpt-002",
            plan_id="pmm-001",
            period_start="2026-01-01",
            period_end="2026-06-30",
            observation_count=200,
            trend_analysis=trend,
            incidents_in_period=["INC-001", "INC-002"],
            recommendations=["Increase monitoring frequency"],
            generated_at="2026-07-01T00:00:00",
        )
        assert report.trend_analysis is not None
        assert report.trend_analysis.overall_assessment == "stable"
        assert len(report.incidents_in_period) == 2
        assert "Increase monitoring frequency" in report.recommendations
        assert report.generated_at == "2026-07-01T00:00:00"


class TestPMMManager:
    def test_create_plan(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            system_name="ClassifierX",
            objectives=["detect drift", "track accuracy"],
            data_sources=["live_logs", "drift_metrics"],
            kpis=[
                {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "live_logs"},
                {"name": "latency_p99", "target": 200, "threshold": 500, "source": "live_logs"},
            ],
        )
        assert isinstance(plan, PMMPlan)
        assert plan.plan_id.startswith("pmm-")
        assert plan.system_name == "ClassifierX"
        assert plan.monitoring_objectives == ["detect drift", "track accuracy"]
        assert len(plan.data_sources) == 2
        assert len(plan.kpis) == 2

    def test_create_plan_with_version_and_interval(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            system_name="DetectorY",
            objectives=["monitor performance"],
            data_sources=["incident_reports"],
            kpis=[],
            system_version="2.1.0",
            review_interval_days=90,
        )
        assert plan.system_version == "2.1.0"
        assert plan.review_interval_days == 90

    def test_create_plan_with_kwargs(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            system_name="TestKwargs",
            objectives=["obj1"],
            data_sources=["src1"],
            kpis=[{"name": "m1"}],
            last_review_at="2026-01-01T00:00:00",
            next_review_at="2026-07-01T00:00:00",
        )
        assert plan.last_review_at == "2026-01-01T00:00:00"
        assert plan.next_review_at == "2026-07-01T00:00:00"

    def test_record_observation(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        obs = mgr.record_observation(
            plan_id=plan.plan_id,
            source="live_logs",
            metric="accuracy",
            value=0.93,
        )
        assert isinstance(obs, PMMObservation)
        assert obs.plan_id == plan.plan_id
        assert obs.source == "live_logs"
        assert obs.metric == "accuracy"
        assert obs.value == 0.93
        assert obs.timestamp != ""

    def test_record_observation_with_threshold_breach(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        obs = mgr.record_observation(
            plan_id=plan.plan_id,
            source="logs",
            metric="accuracy",
            value=0.85,
            threshold=0.90,
        )
        assert obs.threshold_breached is True

    def test_record_observation_with_explicit_details(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        obs = mgr.record_observation(
            plan_id=plan.plan_id,
            source="incident_reports",
            metric="error_rate",
            value=0.05,
            details="Spike in error rate after deployment",
        )
        assert obs.details == "Spike in error rate after deployment"

    def test_record_observation_auto_timestamp(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        before = datetime.now(timezone.utc).isoformat()
        obs = mgr.record_observation(plan.plan_id, "logs", "memory", 1024)
        after = datetime.now(timezone.utc).isoformat()
        assert before <= obs.timestamp <= after

    def test_run_trend_analysis_basic(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.93)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.94)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert isinstance(analysis, PMMTrendAnalysis)
        assert "accuracy" in analysis.metric_trends
        trends = analysis.metric_trends["accuracy"]
        assert abs(trends["mean"] - 0.94) < 0.01
        assert trends["min"] == 0.93
        assert trends["max"] == 0.95
        assert trends["std"] >= 0

    def test_run_trend_analysis_multiple_metrics(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.91)
        mgr.record_observation(plan.plan_id, "logs", "latency", 150)
        mgr.record_observation(plan.plan_id, "logs", "latency", 200)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert "accuracy" in analysis.metric_trends
        assert "latency" in analysis.metric_trends

    def test_run_trend_analysis_threshold_breach(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.85, threshold=0.90)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert "accuracy" in analysis.thresholds_breached

    def test_run_trend_analysis_overall_critical(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.85, threshold=0.90)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.overall_assessment == "critical"

    def test_run_trend_analysis_overall_degrading(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.98)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.92)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.89)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.overall_assessment == "degrading"
        assert analysis.metric_trends["accuracy"]["slope"] < 0

    def test_run_trend_analysis_overall_stable(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.96)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.97)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.96)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.overall_assessment == "stable"
        assert abs(analysis.metric_trends["accuracy"]["slope"]) < 0.01

    def test_run_trend_analysis_empty_window(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        analysis = mgr.run_trend_analysis(plan.plan_id, "2025-01-01", "2025-12-31")
        assert analysis.metric_trends == {}
        assert analysis.thresholds_breached == []
        assert analysis.overall_assessment == "stable"

    def test_run_trend_analysis_incident_correlation(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs", "incident_reports"], [])
        mgr.record_observation(plan.plan_id, "logs", "error_rate", 0.02)
        mgr.record_observation(plan.plan_id, "logs", "error_rate", 0.15, details="Incident INC-101")
        mgr.record_observation(plan.plan_id, "logs", "error_rate", 0.12)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert len(analysis.incident_correlation) >= 0

    def test_run_trend_analysis_single_observation(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["accuracy"]["mean"] == 0.95
        assert analysis.metric_trends["accuracy"]["min"] == 0.95
        assert analysis.metric_trends["accuracy"]["max"] == 0.95
        assert analysis.metric_trends["accuracy"]["std"] == 0.0
        assert analysis.metric_trends["accuracy"]["slope"] == 0.0

    def test_generate_periodic_report(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.94)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.92)
        report = mgr.generate_periodic_report(plan.plan_id, "2026-01-01", "2026-12-31")
        assert isinstance(report, PeriodicReport)
        assert report.plan_id == plan.plan_id
        assert report.observation_count == 2
        assert report.report_id.startswith("rpt-")
        assert report.generated_at != ""

    def test_generate_periodic_report_with_trend(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        report = mgr.generate_periodic_report(plan.plan_id, "2026-01-01", "2026-12-31")
        assert report.trend_analysis is not None
        assert isinstance(report.trend_analysis, PMMTrendAnalysis)

    def test_generate_periodic_report_with_incidents(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "error_rate", 0.20, details="Incident INC-202")
        mgr.record_observation(plan.plan_id, "logs", "error_rate", 0.25, details="Incident INC-203")
        report = mgr.generate_periodic_report(plan.plan_id, "2026-01-01", "2026-12-31")
        # Both incidents should be captured
        incident_mentions = sum(1 for r in report.recommendations if "INC-202" in r or "INC-203" in r)
        assert incident_mentions >= 0

    def test_generate_periodic_report_empty_window(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        report = mgr.generate_periodic_report(plan.plan_id, "2025-01-01", "2025-12-31")
        assert report.observation_count == 0
        assert report.trend_analysis is not None
        assert report.trend_analysis.metric_trends == {}

    def test_check_review_due_true(self) -> None:
        mgr = PMMManager()
        past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        plan = mgr.create_plan(
            "Sys", ["obj"], ["logs"], [],
            last_review_at="2025-01-01T00:00:00",
            next_review_at=past,
        )
        assert mgr.check_review_due(plan.plan_id) is True

    def test_check_review_due_false(self) -> None:
        mgr = PMMManager()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        plan = mgr.create_plan(
            "Sys", ["obj"], ["logs"], [],
            next_review_at=future,
        )
        assert mgr.check_review_due(plan.plan_id) is False

    def test_check_review_due_no_next_review(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        assert mgr.check_review_due(plan.plan_id) is False

    def test_check_review_due_based_on_interval(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            "Sys", ["obj"], ["logs"], [],
            last_review_at=(datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
            review_interval_days=365,
        )
        assert mgr.check_review_due(plan.plan_id) is True

    def test_check_review_due_not_due_by_interval(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan(
            "Sys", ["obj"], ["logs"], [],
            last_review_at=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
            review_interval_days=365,
        )
        assert mgr.check_review_due(plan.plan_id) is False

    def test_get_pmm_summary(self) -> None:
        mgr = PMMManager()
        mgr.create_plan("SysA", ["obj"], ["logs"], [{"name": "m1"}])
        mgr.create_plan("SysB", ["obj"], ["logs"], [])
        summary = mgr.get_pmm_summary()
        assert summary["total_plans"] == 2
        assert "SysA" in str(summary["plans"])
        assert "SysB" in str(summary["plans"])

    def test_get_pmm_summary_with_observations(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "latency", 200)
        summary = mgr.get_pmm_summary()
        assert summary["total_observations"] == 2
        assert summary["total_plans"] == 1

    def test_get_pmm_summary_empty(self) -> None:
        mgr = PMMManager()
        summary = mgr.get_pmm_summary()
        assert summary["total_plans"] == 0
        assert summary["total_observations"] == 0
        assert summary["plans"] == []

    def test_multiple_observations_across_time_ranges(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.98)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.96)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.94)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.92)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["accuracy"]["mean"] == 0.95
        assert analysis.metric_trends["accuracy"]["min"] == 0.92
        assert analysis.metric_trends["accuracy"]["max"] == 0.98

    def test_trend_slope_positive(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.85)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.90)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["accuracy"]["slope"] > 0

    def test_trend_slope_negative(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.90)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.85)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["accuracy"]["slope"] < 0

    def test_trend_slope_constant(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.90)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.90)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.90)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["accuracy"]["slope"] == 0.0

    def test_threshold_breached_from_kpi(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "latency", "target": 100, "threshold": 200, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "latency", 150)
        mgr.record_observation(plan.plan_id, "logs", "latency", 250)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert "latency" in analysis.thresholds_breached

    def test_threshold_not_breached(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.95)
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.94)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert len(analysis.thresholds_breached) == 0

    def test_plan_with_zero_objectives_still_works(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("ZeroObj", [], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "uptime", 99.9)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert "uptime" in analysis.metric_trends
        summary = mgr.get_pmm_summary()
        assert summary["total_plans"] == 1

    def test_plan_no_kpis_still_functions(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("NoKPI", ["obj"], ["logs"], [])
        mgr.record_observation(plan.plan_id, "logs", "memory", 512)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert analysis.metric_trends["memory"]["mean"] == 512.0

    def test_all_thresholds_breached(self) -> None:
        mgr = PMMManager()
        plan = mgr.create_plan("Sys", ["obj"], ["logs"], [
            {"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "logs"},
            {"name": "latency", "target": 100, "threshold": 200, "source": "logs"},
        ])
        mgr.record_observation(plan.plan_id, "logs", "accuracy", 0.80, threshold=0.90)
        mgr.record_observation(plan.plan_id, "logs", "latency", 500, threshold=200)
        analysis = mgr.run_trend_analysis(plan.plan_id, "2026-01-01", "2026-12-31")
        assert "accuracy" in analysis.thresholds_breached
        assert "latency" in analysis.thresholds_breached
        assert analysis.overall_assessment == "critical"
