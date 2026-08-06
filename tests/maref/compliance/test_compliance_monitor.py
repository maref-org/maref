from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from maref.compliance import ComplianceRegistry, Jurisdiction
from maref.compliance.compliance_monitor import (
    AlertSeverity,
    ComplianceAlert,
    ComplianceMonitor,
    ComplianceSnapshot,
    MonitorState,
    MonitoringRule,
)


class TestMonitorState:
    def test_values(self) -> None:
        assert MonitorState.IDLE.value == "idle"
        assert MonitorState.RUNNING.value == "running"
        assert MonitorState.PAUSED.value == "paused"
        assert MonitorState.ERROR.value == "error"


class TestAlertSeverity:
    def test_values(self) -> None:
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.INFO.value == "info"


class TestComplianceSnapshot:
    def test_defaults(self) -> None:
        snapshot = ComplianceSnapshot(
            snapshot_id="s1",
            timestamp=datetime(2026, 1, 1),
            jurisdiction=Jurisdiction.CHINA,
            overall_status={"score": 85.0},
            requirement_status={},
            changes_since_last=[],
        )
        assert snapshot.snapshot_id == "s1"
        assert snapshot.jurisdiction == Jurisdiction.CHINA

    def test_to_dict(self) -> None:
        snapshot = ComplianceSnapshot(
            snapshot_id="s1",
            timestamp=datetime(2026, 1, 1),
            jurisdiction=Jurisdiction.CHINA,
            overall_status={"score": 85.0},
            requirement_status={},
            changes_since_last=[],
        )
        d = snapshot.to_dict()
        assert d["snapshot_id"] == "s1"
        assert d["jurisdiction"] == "china"
        assert d["requirement_count"] == 0


class TestComplianceAlert:
    def test_defaults(self) -> None:
        alert = ComplianceAlert(
            alert_id="a1",
            jurisdiction=Jurisdiction.CHINA,
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            description="A test alert",
            detected_at=datetime(2026, 1, 1),
        )
        assert alert.is_active is True
        assert alert.resolved_at is None

    def test_to_dict(self) -> None:
        alert = ComplianceAlert(
            alert_id="a1",
            jurisdiction=Jurisdiction.CHINA,
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            description="Something broke",
            detected_at=datetime(2026, 1, 1),
            affected_requirements=["req1"],
            recommended_remediation=["fix it"],
        )
        d = alert.to_dict()
        assert d["alert_id"] == "a1"
        assert d["severity"] == "critical"
        assert len(d["affected_requirements"]) == 1


class TestMonitoringRule:
    def test_defaults(self) -> None:
        rule = MonitoringRule(
            rule_id="r1",
            name="Test Rule",
            description="A test rule",
        )
        assert rule.check_interval_hours == 24
        assert rule.threshold == 80.0
        assert rule.auto_remediate is False
        assert rule.is_active is True
        assert rule.last_checked is None

    def test_is_due_never_checked(self) -> None:
        rule = MonitoringRule(rule_id="r1", name="R1", description="test")
        assert rule.is_due() is True

    def test_is_due_recently_checked(self) -> None:
        rule = MonitoringRule(rule_id="r1", name="R1", description="test")
        rule.mark_checked()
        assert rule.last_checked is not None
        # just checked, so not due
        assert rule.is_due() is False

    def test_mark_checked(self) -> None:
        rule = MonitoringRule(rule_id="r1", name="R1", description="test")
        rule.mark_checked()
        assert rule.last_checked is not None


class TestComplianceMonitor:
    def test_init(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        assert monitor.state == MonitorState.IDLE
        assert len(monitor._rules) > 0

    def test_register_alert_callback(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        callback = MagicMock()
        monitor.register_alert_callback(callback)
        assert len(monitor._alert_callbacks) == 1

    def test_add_rule(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        rule = MonitoringRule(rule_id="custom", name="Custom", description="test")
        monitor.add_rule(rule)
        assert "custom" in monitor._rules

    def test_remove_rule(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        rule = MonitoringRule(rule_id="r1", name="R1", description="test")
        monitor.add_rule(rule)
        assert monitor.remove_rule("r1") is True
        assert monitor.remove_rule("nonexistent") is False

    def test_take_snapshot(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        registry.get_jurisdiction_compliance_status.return_value = {
            "compliance_rate": 90.0,
        }
        registry.check_results = {}
        monitor = ComplianceMonitor(registry=registry)
        snapshot = monitor.take_snapshot(jurisdiction=Jurisdiction.CHINA)
        assert snapshot.jurisdiction == Jurisdiction.CHINA
        assert "compliance_rate" in snapshot.overall_status

    def test_check_all_rules(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        registry.get_jurisdiction_compliance_status.return_value = {
            "compliance_rate": 50.0,
        }
        registry.jurisdiction_rules = {}
        monitor = ComplianceMonitor(registry=registry)
        alerts = monitor.check_all_rules()
        assert isinstance(alerts, list)

    def test_resolve_alert(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        assert monitor.resolve_alert("nonexistent") is False

    def test_get_active_alerts(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        alerts = monitor.get_active_alerts()
        assert isinstance(alerts, list)

    def test_get_compliance_trend(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        registry.get_jurisdiction_compliance_status.return_value = {
            "compliance_rate": 90.0,
        }
        registry.check_results = {}
        monitor = ComplianceMonitor(registry=registry)
        trend = monitor.get_compliance_trend(jurisdiction=Jurisdiction.CHINA)
        assert isinstance(trend, list)

    def test_run_check_cycle(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        registry.get_jurisdiction_compliance_status.return_value = {
            "compliance_rate": 90.0,
        }
        registry.jurisdiction_rules = {}
        registry.check_results = {}
        monitor = ComplianceMonitor(registry=registry)
        result = monitor.run_check_cycle()
        assert result["cycle_completed"] is True

    def test_get_monitor_status(self) -> None:
        registry = MagicMock(spec=ComplianceRegistry)
        monitor = ComplianceMonitor(registry=registry)
        status = monitor.get_monitor_status()
        assert status["state"] == "idle"
        assert status["rules_count"] > 0
