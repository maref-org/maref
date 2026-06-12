from __future__ import annotations

import pytest

from maref.recursive.self_diagnostician import (
    DiagnosisReport,
    RiskLevel,
    SelfDiagnostician,
)
from maref.recursive.self_observer import SystemSnapshot


class TestSelfDiagnostician:
    @pytest.fixture
    def diagnostician(self) -> SelfDiagnostician:
        return SelfDiagnostician()

    @pytest.fixture
    def normal_snapshot(self) -> SystemSnapshot:
        return SystemSnapshot(
            timestamp=1000.0,
            module_graph={"a": ["b"], "b": ["c"], "c": []},
            test_stats={"total": 658, "passed": 658, "failed": 0},
            git_stats={"tags": ["v0.3.0-r1", "v0.2.0"]},
            source_file_count=10,
            total_lines=1000,
        )

    def test_diagnose_returns_report(self, diagnostician: SelfDiagnostician, normal_snapshot: SystemSnapshot) -> None:
        report = diagnostician.diagnose(normal_snapshot)
        assert isinstance(report, DiagnosisReport)
        assert report.overall_risk == RiskLevel.NORMAL

    def test_diagnose_runs_all_five_probes(self, diagnostician: SelfDiagnostician, normal_snapshot: SystemSnapshot) -> None:
        report = diagnostician.diagnose(normal_snapshot)
        expected_probes = {"entropy", "anomaly", "latency", "kg", "oscillation"}
        assert set(report.probe_results.keys()) == expected_probes, \
            f"Expected {expected_probes}, got {set(report.probe_results.keys())}"

    def test_normal_state_all_risk_normal(self, diagnostician: SelfDiagnostician, normal_snapshot: SystemSnapshot) -> None:
        report = diagnostician.diagnose(normal_snapshot)
        for probe_name, level in report.risk_matrix.items():
            assert level == RiskLevel.NORMAL, f"Probe {probe_name} expected NORMAL, got {level}"

    def test_diagnose_recommendations_normal(self, diagnostician: SelfDiagnostician, normal_snapshot: SystemSnapshot) -> None:
        report = diagnostician.diagnose(normal_snapshot)
        assert len(report.recommendations) >= 1
        assert any("正常" in r or "无异常" in r for r in report.recommendations)

    def test_high_entropy_triggers_warning(self, diagnostician: SelfDiagnostician) -> None:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 80, "failed": 20},
            module_graph={"a": []},
            git_stats={"tags": []},
            source_file_count=5,
            total_lines=100,
        )
        report = diagnostician.diagnose(snapshot)
        assert report.overall_risk != RiskLevel.NORMAL

    def test_circuit_breaker_closed_initially(self, diagnostician: SelfDiagnostician) -> None:
        assert diagnostician.cb_state == "CLOSED"
        assert not diagnostician.is_blocked()

    def test_circuit_breaker_opens_on_critical(self, diagnostician: SelfDiagnostician) -> None:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 0, "failed": 100},
            module_graph={},
            git_stats={"tags": []},
            source_file_count=0,
            total_lines=0,
        )
        report = diagnostician.diagnose(snapshot)
        diagnostician.check_and_trip(report)
        assert diagnostician.cb_state == "OPEN"
        assert diagnostician.is_blocked()

    def test_circuit_breaker_blocked_blocks_snapshot(self, diagnostician: SelfDiagnostician) -> None:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 0, "failed": 100},
            module_graph={"a": []},
            git_stats={"tags": []},
            source_file_count=0,
            total_lines=0,
        )
        report = diagnostician.diagnose(snapshot)
        diagnostician.check_and_trip(report)
        result = diagnostician.check_and_trip(report)
        assert result is False

    def test_half_open_allows_probe(self, diagnostician: SelfDiagnostician) -> None:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 0, "failed": 100},
            module_graph={"a": []},
            git_stats={"tags": []},
            source_file_count=0,
            total_lines=0,
        )
        report = diagnostician.diagnose(snapshot)
        diagnostician.check_and_trip(report)
        diagnostician.reset_to_half_open()
        assert diagnostician.cb_state == "HALF_OPEN"
        assert not diagnostician.is_blocked()

    def test_close_resets_trip_count(self, diagnostician: SelfDiagnostician) -> None:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 0, "failed": 100},
            module_graph={"a": []},
            git_stats={"tags": []},
            source_file_count=0,
            total_lines=0,
        )
        report = diagnostician.diagnose(snapshot)
        diagnostician.check_and_trip(report)
        diagnostician.close()
        assert diagnostician.cb_state == "CLOSED"
        assert not diagnostician.is_blocked()

    def test_risk_level_enum_values(self) -> None:
        assert RiskLevel.NORMAL.value == "normal"
        assert RiskLevel.WARNING.value == "warning"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_diagnosis_report_defaults(self) -> None:
        report = DiagnosisReport(snapshot_ref="test")
        assert report.probe_results == {}
        assert report.overall_risk == RiskLevel.NORMAL
        assert report.cb_status == "CLOSED"
        assert report.recommendations == []


class TestSemanticDiagnosisIntegration:
    def setup_method(self) -> None:
        self.d = SelfDiagnostician()

    def test_accept_semantic_finding_adds_to_report(self) -> None:
        finding = {"type": "code_smell", "module": "self_observer", "severity": "warning", "message": "Duplicate AST traversal logic detected"}
        self.d.accept_semantic_diagnosis(finding)
        snapshot = SystemSnapshot()
        report = self.d.diagnose(snapshot)
        assert "semantic" in report.probe_results
        assert len(report.probe_results["semantic"]) >= 1

    def test_accept_semantic_critical_detected(self) -> None:
        finding = {"type": "security", "module": "auth", "severity": "critical", "message": "Hardcoded secret key"}
        self.d.accept_semantic_diagnosis(finding)
        snapshot = SystemSnapshot()
        report = self.d.diagnose(snapshot)
        assert report.overall_risk == RiskLevel.CRITICAL

    def test_clear_semantic_findings(self) -> None:
        self.d.accept_semantic_diagnosis({"type": "test", "severity": "warning"})
        self.d.clear_semantic_findings()
        snapshot = SystemSnapshot()
        report = self.d.diagnose(snapshot)
        assert "semantic" not in report.probe_results

    def test_multiple_semantic_findings(self) -> None:
        self.d.accept_semantic_diagnosis({"type": "a", "severity": "warning"})
        self.d.accept_semantic_diagnosis({"type": "b", "severity": "normal"})
        snapshot = SystemSnapshot()
        report = self.d.diagnose(snapshot)
        assert len(report.probe_results.get("semantic", [])) == 2
