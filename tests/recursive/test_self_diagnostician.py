from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import patch

from maref.observation.probes import ProbeReading, ProbeSeverity
from maref.recursive.self_diagnostician import (
    DiagnosisReport,
    RiskLevel,
    SelfDiagnostician,
)
from maref.recursive.self_observer import SystemSnapshot


class TestRiskLevel:
    def test_values(self) -> None:
        assert RiskLevel.NORMAL.value == "normal"
        assert RiskLevel.WARNING.value == "warning"
        assert RiskLevel.CRITICAL.value == "critical"


class TestDiagnosisReport:
    def test_default_construction(self) -> None:
        r = DiagnosisReport(snapshot_ref="s1")
        assert r.snapshot_ref == "s1"
        assert r.probe_results == {}
        assert r.risk_matrix == {}
        assert r.cb_status == "CLOSED"
        assert r.recommendations == []
        assert r.overall_risk == RiskLevel.NORMAL
        assert r.diagnostic_context == {}


class TestSelfDiagnostician:
    def test_default_construction(self) -> None:
        d = SelfDiagnostician()
        assert d.cb_state == "CLOSED"
        assert d._blocked is False
        assert d._trip_count == 0

    @staticmethod
    def _normal_reading(name: str, value: float = 1.0, threshold: float = 0.0, **kw: Any) -> ProbeReading:
        return ProbeReading(
            probe_name=name,
            severity=ProbeSeverity.NORMAL,
            value=value,
            threshold=threshold,
            context=kw,
        )

    def test_diagnose_normal_snapshot(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={"mod_a": ["mod_b"]},
            test_stats={"total": 10, "failed": 0, "duration_ms": 100},
            git_stats={"tags": ["v1.0", "v1.1"]},
            source_file_count=5,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.snapshot_ref == f"snapshot_{snapshot.timestamp}"
        assert report.overall_risk == RiskLevel.NORMAL
        assert report.cb_status == "CLOSED"
        assert "系统正常" in report.recommendations[0]

    def _mock_env_probes(self, d: SelfDiagnostician) -> tuple:
        return (
            patch.object(d._playwright_probe, "measure", return_value=self._normal_reading("playwright", installed=True, chromium_available=True)),
            patch.object(d._desktop_probe, "measure", return_value=self._normal_reading("desktop", pool_available=True, active_sessions=1)),
            patch.object(d._gui_build_probe, "measure", return_value=self._normal_reading("gui_build", lint_passes=True, build_success=True, ts_errors=0)),
        )

    def test_diagnose_entropy_critical(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={},
            test_stats={"total": 10, "failed": 8, "duration_ms": 100},
            git_stats={"tags": []},
            source_file_count=5,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.risk_matrix.get("entropy") == RiskLevel.CRITICAL
        assert report.overall_risk == RiskLevel.CRITICAL
        assert any("CRITICAL" in r for r in report.recommendations)

    def test_diagnose_entropy_warning(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={},
            test_stats={"total": 100, "failed": 20, "duration_ms": 100},
            git_stats={"tags": []},
            source_file_count=5,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.risk_matrix.get("entropy") in (RiskLevel.WARNING, RiskLevel.CRITICAL)

    def test_diagnose_total_tests_zero_falls_back_to_one(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            module_graph={},
            test_stats={"total": 0, "failed": 0, "duration_ms": 0},
            git_stats={"tags": []},
            source_file_count=0,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.overall_risk == RiskLevel.NORMAL

    def test_diagnose_latency_from_duration(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            module_graph={},
            test_stats={"total": 10, "failed": 0, "duration_ms": 120000},
            git_stats={"tags": []},
            source_file_count=1,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.diagnostic_context["latency_test_duration_ms"] >= 120000

    def test_diagnose_latency_from_source_file_count(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            module_graph={},
            test_stats={"total": 10, "failed": 0, "duration_ms": 0},
            git_stats={"tags": []},
            source_file_count=100,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.diagnostic_context["latency_test_duration_ms"] >= 50.0

    def test_diagnose_kg_relation_density(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            module_graph={"mod_a": ["mod_b", "mod_c"], "mod_b": ["mod_c"]},
            test_stats={"total": 10, "failed": 0, "duration_ms": 100},
            git_stats={"tags": []},
            source_file_count=2,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.diagnostic_context["kg_nodes"] == 2
        assert report.diagnostic_context["kg_relation_density"] == 1.5

    def test_diagnose_oscillation_from_tags(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            module_graph={},
            test_stats={"total": 10, "failed": 0, "duration_ms": 100},
            git_stats={"tags": ["v1", "v2", "v3", "v4", "v5"] * 10},
            source_file_count=5,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            report = d.diagnose(snapshot)
        assert report.diagnostic_context["oscillation_tag_count"] == 50
        assert report.diagnostic_context["oscillation_value"] == 5.0

    def test_build_risk_matrix_empty(self) -> None:
        d = SelfDiagnostician()
        matrix = d._build_risk_matrix({})
        assert matrix == {}

    def test_build_risk_matrix_critical_wins(self) -> None:
        d = SelfDiagnostician()
        results = {
            "entropy": [
                ProbeReading(
                    probe_name="entropy",
                    severity=ProbeSeverity.WARNING,
                    value=2.0,
                    threshold=1.5,
                ),
                ProbeReading(
                    probe_name="entropy",
                    severity=ProbeSeverity.CRITICAL,
                    value=5.0,
                    threshold=3.0,
                ),
            ]
        }
        matrix = d._build_risk_matrix(results)
        assert matrix["entropy"] == RiskLevel.CRITICAL

    def test_build_risk_matrix_warning(self) -> None:
        d = SelfDiagnostician()
        results = {
            "latency": [
                ProbeReading(
                    probe_name="latency",
                    severity=ProbeSeverity.WARNING,
                    value=2.0,
                    threshold=1.5,
                )
            ]
        }
        matrix = d._build_risk_matrix(results)
        assert matrix["latency"] == RiskLevel.WARNING

    def test_build_risk_matrix_normal(self) -> None:
        d = SelfDiagnostician()
        results = {
            "entropy": [
                ProbeReading(
                    probe_name="entropy",
                    severity=ProbeSeverity.NORMAL,
                    value=0.5,
                    threshold=3.0,
                )
            ]
        }
        matrix = d._build_risk_matrix(results)
        assert matrix["entropy"] == RiskLevel.NORMAL

    def test_build_risk_matrix_empty_readings(self) -> None:
        d = SelfDiagnostician()
        results = {"entropy": []}
        matrix = d._build_risk_matrix(results)
        assert matrix["entropy"] == RiskLevel.NORMAL

    def test_overall_risk(self) -> None:
        assert SelfDiagnostician._overall_risk({}) == RiskLevel.NORMAL
        assert SelfDiagnostician._overall_risk({"a": RiskLevel.NORMAL, "b": RiskLevel.WARNING}) == RiskLevel.WARNING
        assert SelfDiagnostician._overall_risk({"a": RiskLevel.CRITICAL}) == RiskLevel.CRITICAL
        assert SelfDiagnostician._overall_risk({"a": RiskLevel.WARNING, "b": RiskLevel.CRITICAL}) == RiskLevel.CRITICAL

    def test_generate_recommendations_normal(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {})
        assert recs == ["系统正常，无异常"]

    def test_generate_recommendations_entropy_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"entropy": RiskLevel.CRITICAL},
            {"entropy_test_failure_ratio": 0.5},
        )
        assert any("CRITICAL" in r for r in recs)
        assert any("50.0%" in r for r in recs)

    def test_generate_recommendations_latency_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"latency": RiskLevel.CRITICAL},
            {"latency_test_duration_ms": 60000},
        )
        assert any("60000ms" in r for r in recs)

    def test_generate_recommendations_anomaly_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"anomaly": RiskLevel.CRITICAL},
            {"source_file_count": 5000},
        )
        assert any("5000" in r for r in recs)

    def test_generate_recommendations_kg_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"knowledge_graph": RiskLevel.CRITICAL},
            {"kg_orphan_ratio": 0.8},
        )
        assert any("CRITICAL" in r for r in recs)

    def test_generate_recommendations_oscillation_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"oscillation": RiskLevel.CRITICAL},
            {"oscillation_value": 8.0},
        )
        assert any("CRITICAL" in r for r in recs)

    def test_generate_recommendations_unknown_probe_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"custom_probe": RiskLevel.CRITICAL})
        assert any("custom_probe" in r for r in recs)

    def test_generate_recommendations_warning_entropy(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"entropy": RiskLevel.WARNING})
        assert any("WARNING" in r for r in recs)

    def test_generate_recommendations_warning_latency(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"latency": RiskLevel.WARNING})
        assert any("优化" in r for r in recs)

    def test_generate_recommendations_warning_kg(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"kg": RiskLevel.WARNING})
        assert any("碎片化" in r for r in recs)

    def test_generate_recommendations_warning_anomaly(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"anomaly": RiskLevel.WARNING})
        assert any("增长较快" in r for r in recs)

    def test_generate_recommendations_warning_oscillation(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"oscillation": RiskLevel.WARNING})
        assert any("偏高" in r for r in recs)

    def test_generate_recommendations_unknown_probe_warning(self) -> None:
        recs = SelfDiagnostician._generate_recommendations({}, {"custom": RiskLevel.WARNING})
        assert any("监控" in r for r in recs)

    def test_diagnose_includes_playwright_probe_normal(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={},
            test_stats={"total": 1, "failed": 0, "duration_ms": 0},
            git_stats={"tags": []},
            source_file_count=0,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            stack.enter_context(patch.object(
                d._playwright_probe,
                "measure",
                return_value=ProbeReading(
                    probe_name="playwright",
                    severity=ProbeSeverity.NORMAL,
                    value=1.0,
                    threshold=0.0,
                    context={"installed": True, "chromium_available": True},
                ),
            ))
            report = d.diagnose(snapshot)
        assert "playwright" in report.probe_results
        assert report.risk_matrix["playwright"] == RiskLevel.NORMAL

    def test_diagnose_includes_desktop_probe_normal(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={},
            test_stats={"total": 1, "failed": 0, "duration_ms": 0},
            git_stats={"tags": []},
            source_file_count=0,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            stack.enter_context(patch.object(
                d._desktop_probe,
                "measure",
                return_value=ProbeReading(
                    probe_name="desktop",
                    severity=ProbeSeverity.NORMAL,
                    value=1.0,
                    threshold=0.3,
                    context={"pool_available": True, "active_sessions": 2},
                ),
            ))
            report = d.diagnose(snapshot)
        assert "desktop" in report.probe_results
        assert report.risk_matrix["desktop"] == RiskLevel.NORMAL

    def test_diagnose_includes_gui_build_probe_normal(self) -> None:
        d = SelfDiagnostician()
        snapshot = SystemSnapshot(
            timestamp=1000.0,
            module_graph={},
            test_stats={"total": 1, "failed": 0, "duration_ms": 0},
            git_stats={"tags": []},
            source_file_count=0,
        )
        with contextlib.ExitStack() as stack:
            for p in self._mock_env_probes(d):
                stack.enter_context(p)
            stack.enter_context(patch.object(
                d._gui_build_probe,
                "measure",
                return_value=ProbeReading(
                    probe_name="gui_build",
                    severity=ProbeSeverity.NORMAL,
                    value=0.8,
                    threshold=0.3,
                    context={"lint_passes": True, "build_success": True, "ts_errors": 0},
                ),
            ))
            report = d.diagnose(snapshot)
        assert "gui_build" in report.probe_results
        assert report.risk_matrix["gui_build"] == RiskLevel.NORMAL

    def test_generate_recommendations_playwright_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"playwright": RiskLevel.CRITICAL},
        )
        assert any("Playwright 未安装" in r for r in recs)

    def test_generate_recommendations_desktop_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"desktop": RiskLevel.CRITICAL},
        )
        assert any("桌面代理不可用" in r for r in recs)

    def test_generate_recommendations_gui_build_critical(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"gui_build": RiskLevel.CRITICAL},
        )
        assert any("GUI 构建完全失败" in r for r in recs)

    def test_generate_recommendations_gui_build_warning(self) -> None:
        recs = SelfDiagnostician._generate_recommendations(
            {},
            {"gui_build": RiskLevel.WARNING},
        )
        assert any("TypeScript" in r for r in recs)

    def test_attach_circuit_breaker(self) -> None:
        d = SelfDiagnostician()
        d._cb_state = "OPEN"
        d._blocked = True
        d.attach_circuit_breaker()
        assert d._cb_state == "CLOSED"
        assert d._blocked is False

    def test_check_and_trip_cb_open(self) -> None:
        d = SelfDiagnostician()
        d._cb_state = "OPEN"
        d._blocked = True
        report = DiagnosisReport(snapshot_ref="s1")
        assert d.check_and_trip(report) is False
        assert d._blocked is True

    def test_check_and_trip_cb_closed_critical_returns_true(self) -> None:
        d = SelfDiagnostician()
        report = DiagnosisReport(snapshot_ref="s1", risk_matrix={"entropy": RiskLevel.CRITICAL})
        assert d.check_and_trip(report) is True
        assert d._cb_state == "CLOSED"
        assert d._blocked is False
        assert d._trip_count == 1

    def test_check_and_trip_trips_after_3_critical(self) -> None:
        d = SelfDiagnostician()
        d._trip_count = 3
        report = DiagnosisReport(snapshot_ref="s1", risk_matrix={"entropy": RiskLevel.CRITICAL})
        assert d.check_and_trip(report) is False
        assert d._cb_state == "OPEN"
        assert d._blocked is True

    def test_check_and_trip_cb_closed_no_critical(self) -> None:
        d = SelfDiagnostician()
        report = DiagnosisReport(snapshot_ref="s1", risk_matrix={"entropy": RiskLevel.WARNING})
        assert d.check_and_trip(report) is True
        assert d._cb_state == "CLOSED"
        assert d._blocked is False

    def test_reset_to_half_open(self) -> None:
        d = SelfDiagnostician()
        d._cb_state = "OPEN"
        d._blocked = True
        d.reset_to_half_open()
        assert d._cb_state == "HALF_OPEN"
        assert d._blocked is False

    def test_reset_to_half_open_not_open(self) -> None:
        d = SelfDiagnostician()
        d._cb_state = "CLOSED"
        d.reset_to_half_open()
        assert d._cb_state == "CLOSED"

    def test_close(self) -> None:
        d = SelfDiagnostician()
        d._cb_state = "OPEN"
        d._blocked = True
        d._trip_count = 5
        d.close()
        assert d._cb_state == "CLOSED"
        assert d._blocked is False
        assert d._trip_count == 0

    def test_is_blocked(self) -> None:
        d = SelfDiagnostician()
        assert d.is_blocked() is False
        d._blocked = True
        assert d.is_blocked() is True
