"""
威胁情报与监控测试
"""

from datetime import datetime

from maref.monitoring.security_orchestrator import (
    NotificationChannel,
    SecurityAction,
    SecurityOrchestrator,
    create_security_orchestrator,
)
from maref.monitoring.threat_intelligence import (
    IOCType,
    ThreatIndicator,
    ThreatIntelligenceEngine,
    ThreatSeverity,
    ThreatSource,
    VulnerabilityReport,
    create_threat_intelligence,
)


class TestThreatIntelligence:
    """测试威胁情报引擎"""

    def test_create_engine(self) -> None:
        engine = create_threat_intelligence()
        assert isinstance(engine, ThreatIntelligenceEngine)

    def test_add_and_search_indicator(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()

        indicator = ThreatIndicator(
            indicator_id="test-ioc",
            indicator_type=IOCType.IP_ADDRESS,
            value="198.51.100.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.HIGH,
            description="Test malicious IP",
            confidence=0.9,
            first_seen=now,
            last_seen=now,
        )
        engine.add_indicator(indicator)

        found = engine.search_ioc(IOCType.IP_ADDRESS, "198.51.100.1")
        assert found is not None
        assert found.severity == ThreatSeverity.HIGH

    def test_match_against_indicators(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()

        for ip in ["192.0.2.1", "192.0.2.2"]:
            engine.add_indicator(ThreatIndicator(
                indicator_id=f"ioc-{ip}",
                indicator_type=IOCType.IP_ADDRESS,
                value=ip,
                source=ThreatSource.INTERNAL,
                severity=ThreatSeverity.MEDIUM,
                description=f"Malicious IP {ip}",
                confidence=0.8,
                first_seen=now,
                last_seen=now,
            ))

        matches = engine.match_against_indicators("192.0.2.1")
        assert len(matches) == 1

    def test_scan_components(self) -> None:
        engine = create_threat_intelligence()

        vuln = VulnerabilityReport(
            report_id="vuln-test",
            cve_id="CVE-2024-0001",
            title="Test vulnerability in ExampleLib",
            description="A test vulnerability",
            severity=ThreatSeverity.CRITICAL,
            cvss_score=9.8,
            affected_components=["ExampleLib"],
            fixed_versions=["2.0.0"],
            published_at=datetime.now(),
            updated_at=datetime.now(),
        )
        engine.add_vulnerability(vuln)

        result = engine.scan_components([
            {"name": "ExampleLib", "version": "1.0.0"},
            {"name": "SafeLib", "version": "3.0.0"},
        ])

        assert result["vulnerabilities_found"] == 1
        assert result["risk_level"] == "critical"

    def test_create_and_resolve_alert(self) -> None:
        engine = create_threat_intelligence()

        alert = engine.create_alert(
            alert_type="vulnerability",
            severity=ThreatSeverity.HIGH,
            title="Test Alert",
            description="Test description",
            affected_assets=["server-1"],
            recommended_actions=["Patch immediately"],
        )

        assert alert.is_active
        assert len(engine.get_active_alerts()) == 1

        resolved = engine.resolve_alert(alert.alert_id)
        assert resolved
        assert len(engine.get_active_alerts()) == 0

    def test_get_active_alerts_filtered(self) -> None:
        engine = create_threat_intelligence()

        engine.create_alert("vuln", ThreatSeverity.CRITICAL, "Critical", "desc", ["a"], ["fix"])
        engine.create_alert("vuln", ThreatSeverity.LOW, "Low", "desc", ["a"], ["fix"])

        critical_only = engine.get_active_alerts(min_severity=ThreatSeverity.HIGH)
        assert len(critical_only) == 1

    def test_threat_summary(self) -> None:
        engine = create_threat_intelligence()

        summary = engine.get_threat_summary()
        assert "total_indicators" in summary
        assert "active_alerts" in summary

    def test_assess_threat_for_asset(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()

        engine.add_indicator(ThreatIndicator(
            indicator_id="ioc-asset",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.99",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.CRITICAL,
            description="Malicious",
            confidence=1.0,
            first_seen=now,
            last_seen=now,
        ))

        result = engine.assess_threat_for_asset("asset-1", {"ip": "10.0.0.99", "name": "test"})
        assert result["risk_level"] == "critical"
        assert result["matched_iocs"] >= 1


class TestSecurityOrchestrator:
    """测试安全编排器"""

    def test_create_orchestrator(self) -> None:
        so = create_security_orchestrator()
        assert isinstance(so, SecurityOrchestrator)

    def test_register_action(self) -> None:
        so = create_security_orchestrator()

        action = SecurityAction(
            action_id="test-action",
            name="Test Action",
            description="A test action",
            action_type="test",
        )
        so.register_action(action)
        assert so.get_action("test-action") is not None

    def test_create_event_and_auto_respond(self) -> None:
        so = create_security_orchestrator()

        event = so.create_event(
            event_type="threat_detected",
            severity="high",
            title="Suspicious activity detected",
            description="Multiple failed login attempts",
        )

        records = so.auto_respond(event.event_id)
        assert len(records) > 0

    def test_get_open_events(self) -> None:
        so = create_security_orchestrator()

        so.create_event("threat_detected", "critical", "Event 1", "desc")
        so.create_event("threat_detected", "low", "Event 2", "desc")

        all_open = so.get_open_events()
        assert len(all_open) >= 2

    def test_get_playbook(self) -> None:
        so = create_security_orchestrator()

        playbook = so.get_playbook("playbook-threat-response")
        assert playbook is not None
        assert playbook.name == "Threat Detection Response"

    def test_trigger_playbook_manually(self) -> None:
        so = create_security_orchestrator()

        event = so.create_event("test", "high", "Test", "desc")
        record = so.trigger_playbook("playbook-threat-response", event.event_id)

        assert record is not None
        assert record.playbook_id == "playbook-threat-response"

    def test_trigger_nonexistent_playbook(self) -> None:
        so = create_security_orchestrator()

        event = so.create_event("test", "high", "Test", "desc")
        record = so.trigger_playbook("nonexistent", event.event_id)

        assert record is None

    def test_execution_statistics(self) -> None:
        so = create_security_orchestrator()

        stats = so.get_statistics()
        assert "total_playbooks" in stats
        assert "total_actions" in stats

    def test_export_playbooks(self) -> None:
        so = create_security_orchestrator()

        playbooks = so.export_playbooks()
        assert len(playbooks) >= 3  # 三个内置剧本

    def test_notification_registration(self) -> None:
        so = create_security_orchestrator()

        notifications = []

        def handler(title: str, msg: str, severity: str) -> None:
            notifications.append((title, msg, severity))

        so.register_notification_handler(NotificationChannel.LOG, handler)
        result = so.send_notification(NotificationChannel.LOG, "Test", "Message", "info")

        assert result == True
        assert len(notifications) == 1
