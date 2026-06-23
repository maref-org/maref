from __future__ import annotations

from datetime import datetime

from maref.compliance import Jurisdiction
from maref.compliance.compliance_monitor import (
    AlertSeverity,
    ComplianceAlert,
    ComplianceMonitor,
    ComplianceSnapshot,
    MonitorState,
    MonitoringRule,
    create_compliance_monitor,
)
from maref.compliance.registry import ComplianceRegistry


class TestMonitoringRule:
    def test_is_due_initially(self) -> None:
        rule = MonitoringRule("rule-1", "Test Rule", "Test")
        assert rule.is_due()

    def test_mark_checked(self) -> None:
        rule = MonitoringRule("rule-1", "Test Rule", "Test")
        rule.mark_checked()
        assert rule.last_checked is not None

    def test_to_dict_in_snapshot(self) -> None:
        snapshot = ComplianceSnapshot(
            snapshot_id="snap-1",
            timestamp=datetime.now(),
            jurisdiction=Jurisdiction.EU,
            overall_status={"compliance_rate": 75.0},
            requirement_status={},
            changes_since_last=[],
        )
        d = snapshot.to_dict()
        assert d["snapshot_id"] == "snap-1"
        assert d["jurisdiction"] == "eu"
        assert d["requirement_count"] == 0

    def test_to_dict_no_jurisdiction(self) -> None:
        snapshot = ComplianceSnapshot(
            snapshot_id="snap-1",
            timestamp=datetime.now(),
            jurisdiction=None,
            overall_status={},
            requirement_status={},
            changes_since_last=[],
        )
        d = snapshot.to_dict()
        assert d["jurisdiction"] is None


class TestComplianceAlert:
    def test_to_dict(self) -> None:
        alert = ComplianceAlert(
            alert_id="alert-1",
            jurisdiction=Jurisdiction.EU,
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            description="Test description",
            detected_at=datetime.now(),
        )
        d = alert.to_dict()
        assert d["alert_id"] == "alert-1"
        assert d["severity"] == "critical"
        assert d["is_active"] is True

    def test_resolve_alert(self) -> None:
        alert = ComplianceAlert(
            alert_id="alert-1",
            jurisdiction=Jurisdiction.EU,
            severity=AlertSeverity.WARNING,
            title="Test",
            description="Test",
            detected_at=datetime.now(),
        )
        alert.is_active = False
        alert.resolved_at = datetime.now()
        assert not alert.is_active
        assert alert.resolved_at is not None


class TestComplianceMonitor:
    def test_init_creates_default_rules(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        assert monitor.state == MonitorState.IDLE
        assert len(monitor._rules) >= 4

    def test_add_and_remove_rule(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        rule = MonitoringRule("custom-rule", "Custom", "Custom rule")
        rid = monitor.add_rule(rule)
        assert rid == "custom-rule"
        assert monitor.remove_rule("custom-rule")
        assert not monitor.remove_rule("nonexistent")

    def test_take_snapshot_all(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        snapshot = monitor.take_snapshot()
        assert snapshot.snapshot_id.startswith("snap-")
        assert snapshot.jurisdiction is None

    def test_take_snapshot_specific_jurisdiction(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        snapshot = monitor.take_snapshot(Jurisdiction.EU)
        assert snapshot.jurisdiction == Jurisdiction.EU

    def test_take_snapshot_detects_changes(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)

        from maref.compliance.registry import ComplianceRequirement, ComplianceCheckResult, ComplianceStatus
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
        )
        registry.register_requirement(req)
        result = ComplianceCheckResult(
            result_id="res-1",
            requirement_id="req-1",
            status=ComplianceStatus.COMPLIANT,
            checked_at=datetime.now(),
            checked_by="test",
        )
        registry.record_check_result(result)

        monitor.take_snapshot(Jurisdiction.EU)

        result2 = ComplianceCheckResult(
            result_id="res-2",
            requirement_id="req-1",
            status=ComplianceStatus.NON_COMPLIANT,
            checked_at=datetime.now(),
            checked_by="test",
        )
        registry.record_check_result(result2)

        snapshot2 = monitor.take_snapshot(Jurisdiction.EU)
        assert len(snapshot2.changes_since_last) > 0

    def test_get_active_alerts(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        alerts = monitor.get_active_alerts()
        assert isinstance(alerts, list)

    def test_get_active_alerts_filter_by_jurisdiction(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)

        alert = ComplianceAlert(
            alert_id="alert-1",
            jurisdiction=Jurisdiction.EU,
            severity=AlertSeverity.CRITICAL,
            title="Test",
            description="Test",
            detected_at=datetime.now(),
        )
        monitor._alerts["alert-1"] = alert

        eu_alerts = monitor.get_active_alerts(jurisdiction=Jurisdiction.EU)
        assert len(eu_alerts) == 1

        cn_alerts = monitor.get_active_alerts(jurisdiction=Jurisdiction.CHINA)
        assert len(cn_alerts) == 0

    def test_get_monitor_status(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        status = monitor.get_monitor_status()
        assert status["state"] == "idle"
        assert status["rules_count"] >= 4
        assert "active_alerts" in status
        assert "total_snapshots" in status

    def test_resolve_alert(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)

        alert = ComplianceAlert(
            alert_id="alert-1",
            jurisdiction=Jurisdiction.EU,
            severity=AlertSeverity.WARNING,
            title="Test",
            description="Test",
            detected_at=datetime.now(),
        )
        monitor._alerts["alert-1"] = alert

        assert monitor.resolve_alert("alert-1")
        assert not monitor.resolve_alert("nonexistent")
        assert not monitor._alerts["alert-1"].is_active

    def test_register_alert_callback(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        called: list[ComplianceAlert] = []

        def callback(alert: ComplianceAlert) -> None:
            called.append(alert)

        monitor.register_alert_callback(callback)
        assert len(monitor._alert_callbacks) == 1

    def test_run_check_cycle(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)

        from maref.compliance.registry import ComplianceRequirement
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
        )
        registry.register_requirement(req)

        result = monitor.run_check_cycle()
        assert result["cycle_completed"] is True
        assert result["state"] == "idle"

    def test_get_compliance_trend(self) -> None:
        registry = ComplianceRegistry()
        monitor = ComplianceMonitor(registry)
        monitor.take_snapshot(Jurisdiction.EU)
        monitor.take_snapshot(Jurisdiction.EU)
        trend = monitor.get_compliance_trend(Jurisdiction.EU)
        assert len(trend) == 2


class TestCreateComplianceMonitor:
    def test_create_monitor(self) -> None:
        registry = ComplianceRegistry()
        monitor = create_compliance_monitor(registry)
        assert isinstance(monitor, ComplianceMonitor)
