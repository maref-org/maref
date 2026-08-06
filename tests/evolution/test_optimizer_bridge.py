from __future__ import annotations

from drift_guard.policy_sandbox import PolicyChangeType, PolicySandbox
from maref.evolution.optimizer_bridge import OptimizerEvolutionBridge
from maref.recursive.self_diagnostician import DiagnosisReport, RiskLevel
from maref.recursive.self_observer import SystemSnapshot


def _make_snapshot(**overrides: object) -> SystemSnapshot:
    defaults: dict[str, object] = {
        "timestamp": 1234567890.0,
        "module_graph": {},
        "test_stats": {"total": 100, "passed": 95, "failed": 5},
        "git_stats": {"commits": 10},
        "state_machine_status": {"state": "CLOSED"},
        "probe_readings": [],
        "source_file_count": 42,
        "total_lines": 5000,
    }
    merged = {**defaults, **overrides}
    return SystemSnapshot(**merged)


def _make_report(risk_matrix: dict[str, RiskLevel], **overrides: object) -> DiagnosisReport:
    defaults: dict[str, object] = {
        "snapshot_ref": "test-snapshot",
        "overall_risk": RiskLevel.NORMAL,
        "risk_matrix": risk_matrix,
        "diagnostic_context": {
            "entropy_value": 2.5,
            "entropy_test_failure_ratio": 0.05,
            "latency_value": 450.0,
            "latency_p95_ms": 400.0,
            "latency_drift_pct": 15.0,
            "source_file_count": 42,
            "kg_orphan_ratio": 0.1,
            "anomaly_modules": 1.0,
            "desktop_pool_available": 1.0,
            "desktop_active_sessions": 2.0,
            "gui_build_lint_ok": 1.0,
            "gui_build_ts_errors": 5.0,
        },
        "recommendations": [],
    }
    merged = {**defaults, **overrides}
    return DiagnosisReport(**merged)


class TestDiagnoseToHypotheses:
    def test_empty_risk_matrix_returns_no_hypotheses(self) -> None:
        report = _make_report({})
        snapshot = _make_snapshot()
        bridge = OptimizerEvolutionBridge()

        hypotheses = bridge.diagnose_to_hypotheses(report, snapshot)

        assert hypotheses == []

    def test_all_critical_generates_all_hypotheses(self) -> None:
        risk = {
            "entropy": RiskLevel.CRITICAL,
            "latency": RiskLevel.CRITICAL,
            "anomaly": RiskLevel.CRITICAL,
            "knowledge_graph": RiskLevel.CRITICAL,
            "desktop": RiskLevel.CRITICAL,
            "playwright": RiskLevel.CRITICAL,
            "gui_build": RiskLevel.CRITICAL,
        }
        report = _make_report(risk)
        snapshot = _make_snapshot()
        bridge = OptimizerEvolutionBridge()

        hypotheses = bridge.diagnose_to_hypotheses(report, snapshot)

        ids = {h.hypothesis_id.split("_")[0] for h in hypotheses}
        assert "entropy" in ids
        assert "latency" in ids
        assert "complexity" in ids
        assert "kg" in ids
        assert "desktop" in ids
        assert "gui" in ids
        assert len(hypotheses) == 6

    def test_all_warning_generates_five_hypotheses(self) -> None:
        risk = {
            "entropy": RiskLevel.WARNING,
            "latency": RiskLevel.WARNING,
            "anomaly": RiskLevel.WARNING,
            "knowledge_graph": RiskLevel.WARNING,
            "gui_build": RiskLevel.WARNING,
        }
        report = _make_report(risk)
        snapshot = _make_snapshot()
        bridge = OptimizerEvolutionBridge()

        hypotheses = bridge.diagnose_to_hypotheses(report, snapshot)

        ids = {h.hypothesis_id.split("_")[0] for h in hypotheses}
        assert "entropy" in ids
        assert "latency" in ids
        assert "complexity" in ids
        assert "kg" in ids
        assert "gui" in ids
        assert "desktop" not in ids
        assert len(hypotheses) == 5

    def test_desktop_only_triggers_on_critical(self) -> None:
        risk_warn = {"desktop": RiskLevel.WARNING, "playwright": RiskLevel.WARNING}
        report = _make_report(risk_warn)
        bridge = OptimizerEvolutionBridge()
        h1 = bridge.diagnose_to_hypotheses(report, _make_snapshot())

        risk_crit = {"desktop": RiskLevel.CRITICAL, "playwright": RiskLevel.WARNING}
        report2 = _make_report(risk_crit)
        h2 = bridge.diagnose_to_hypotheses(report2, _make_snapshot())

        risk_crit2 = {"desktop": RiskLevel.WARNING, "playwright": RiskLevel.CRITICAL}
        report3 = _make_report(risk_crit2)
        h3 = bridge.diagnose_to_hypotheses(report3, _make_snapshot())

        assert len(h1) == 0
        assert len(h2) == 1
        assert h2[0].target_module == "desktop"
        assert len(h3) == 1
        assert h3[0].target_module == "desktop"

    def test_partial_risk_matrix(self) -> None:
        risk = {"entropy": RiskLevel.CRITICAL}
        report = _make_report(risk)
        snapshot = _make_snapshot()
        bridge = OptimizerEvolutionBridge()

        hypotheses = bridge.diagnose_to_hypotheses(report, snapshot)

        assert len(hypotheses) == 1
        assert hypotheses[0].target_module == "tests"
        assert "entropy" in hypotheses[0].hypothesis_id
        assert "reduce test failures" in hypotheses[0].description


class TestAdoptToPolicyChange:
    def setup_method(self) -> None:
        self.bridge = OptimizerEvolutionBridge()
        self.sandbox = PolicySandbox()

    def test_tests_target_uses_threshold_adjustment(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"entropy": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.THRESHOLD_ADJUSTMENT

    def test_execution_target_uses_threshold_adjustment(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"latency": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.THRESHOLD_ADJUSTMENT

    def test_architecture_target_uses_state_machine_rule(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"anomaly": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.STATE_MACHINE_RULE

    def test_knowledge_graph_target_uses_monitor_config(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"knowledge_graph": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.MONITOR_CONFIG

    def test_desktop_target_uses_action_policy(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"desktop": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.ACTION_POLICY

    def test_gui_target_uses_action_policy(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"gui_build": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is not None
        assert change.change_type == PolicyChangeType.ACTION_POLICY

    def test_unknown_target_returns_none(self) -> None:
        h = self.bridge.diagnose_to_hypotheses(
            _make_report({"entropy": RiskLevel.CRITICAL}),
            _make_snapshot(),
        )[0]
        h.target_module = "unknown"
        change = self.bridge.adopt_to_policy_change(h, self.sandbox)
        assert change is None
