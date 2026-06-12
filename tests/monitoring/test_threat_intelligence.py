from __future__ import annotations

from datetime import datetime

import pytest

from maref.monitoring.threat_intelligence import (
    IOCType,
    ThreatAlert,
    ThreatIndicator,
    ThreatIntelligenceEngine,
    ThreatSeverity,
    ThreatSource,
    VulnerabilityReport,
    create_threat_intelligence,
)


class TestDataclassMethods:
    def test_indicator_to_dict(self) -> None:
        now = datetime.now()
        indicator = ThreatIndicator(
            indicator_id="ioc-001",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.HIGH,
            description="test",
            confidence=0.95,
            first_seen=now,
            last_seen=now,
            tags=["malicious"],
            related_cves=["CVE-2024-0001"],
            mitre_techniques=["T1078"],
        )
        d = indicator.to_dict()
        assert d["indicator_id"] == "ioc-001"
        assert d["type"] == "ip"
        assert d["severity"] == "high"
        assert d["confidence"] == 0.95
        assert d["tags"] == ["malicious"]

    def test_indicator_compute_hash(self) -> None:
        now = datetime.now()
        i1 = ThreatIndicator(
            indicator_id="i1",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.LOW,
            description="test",
            confidence=0.5,
            first_seen=now,
            last_seen=now,
        )
        h = i1.compute_hash()
        assert isinstance(h, str)
        assert len(h) == 64

    def test_vulnerability_report_to_dict(self) -> None:
        now = datetime.now()
        report = VulnerabilityReport(
            report_id="v-001",
            cve_id="CVE-2024-0001",
            title="Test Vuln",
            description="desc",
            severity=ThreatSeverity.CRITICAL,
            cvss_score=9.8,
            affected_components=["lib"],
            fixed_versions=["2.0"],
            published_at=now,
            updated_at=now,
            references=["https://example.com"],
            exploit_available=True,
            patch_available=True,
        )
        d = report.to_dict()
        assert d["cve_id"] == "CVE-2024-0001"
        assert d["severity"] == "critical"
        assert d["exploit_available"] is True

    def test_alert_to_dict(self) -> None:
        now = datetime.now()
        alert = ThreatAlert(
            alert_id="a-001",
            alert_type="vulnerability",
            severity=ThreatSeverity.HIGH,
            title="Test Alert",
            description="desc",
            detected_at=now,
            affected_assets=["server-1"],
            recommended_actions=["patch"],
            assigned_to="user1",
        )
        d = alert.to_dict()
        assert d["alert_id"] == "a-001"
        assert d["severity"] == "high"
        assert d["assigned_to"] == "user1"
        assert d["resolved_at"] is None


class TestThreatIntelligenceEdgeCases:
    def test_export_indicators_all(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()
        engine.add_indicator(ThreatIndicator(
            indicator_id="i1",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.LOW,
            description="",
            confidence=0.5,
            first_seen=now,
            last_seen=now,
        ))
        indicators = engine.export_indicators()
        assert len(indicators) > 0

    def test_export_indicators_filtered(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()
        engine.add_indicator(ThreatIndicator(
            indicator_id="i1",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.CUSTOM_FEED,
            severity=ThreatSeverity.LOW,
            description="",
            confidence=0.5,
            first_seen=now,
            last_seen=now,
        ))
        matched = engine.export_indicators(source=ThreatSource.CUSTOM_FEED)
        assert len(matched) >= 1
        no_match = engine.export_indicators(source=ThreatSource.OSINT_FEED)
        assert len(no_match) == 0

    def test_resolve_alert_not_found(self) -> None:
        engine = create_threat_intelligence()
        assert engine.resolve_alert("nonexistent") is False

    def test_get_active_alerts_no_filter(self) -> None:
        engine = create_threat_intelligence()
        engine.create_alert("vuln", ThreatSeverity.LOW, "Low", "desc", ["a"], ["fix"])
        all_alerts = engine.get_active_alerts()  # min_severity=None
        assert len(all_alerts) == 1

    def test_assess_threat_no_match(self) -> None:
        engine = create_threat_intelligence()
        result = engine.assess_threat_for_asset("asset-1", {"ip": "10.0.0.99"})
        assert result["risk_level"] == "low"
        assert result["recommendation"] == "No threats detected"

    def test_assess_threat_not_string_value(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()
        engine.add_indicator(ThreatIndicator(
            indicator_id="i1",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.CRITICAL,
            description="",
            confidence=1.0,
            first_seen=now,
            last_seen=now,
        ))
        result = engine.assess_threat_for_asset("asset-1", {"ip": 12345})
        assert result["matched_iocs"] == 0

    def test_get_threat_summary_with_alerts(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()
        engine.add_indicator(ThreatIndicator(
            indicator_id="i1",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.HIGH,
            description="",
            confidence=0.8,
            first_seen=now,
            last_seen=now,
        ))
        engine.create_alert("ioc", ThreatSeverity.HIGH, "Alert", "desc", ["a"], ["fix"])
        summary = engine.get_threat_summary()
        assert summary["active_alerts"] >= 1
        assert summary["total_indicators"] >= 1

    def test_add_vulnerability_no_cve(self) -> None:
        engine = create_threat_intelligence()
        report = VulnerabilityReport(
            report_id="v-nocve",
            cve_id=None,
            title="No CVE Vuln",
            description="desc",
            severity=ThreatSeverity.MEDIUM,
            cvss_score=5.5,
            affected_components=["lib"],
            fixed_versions=["2.0"],
            published_at=datetime.now(),
            updated_at=datetime.now(),
        )
        engine.add_vulnerability(report)
        result = engine.scan_components([{"name": "lib", "version": "1.0"}])
        assert result["vulnerabilities_found"] == 1

    def test_scan_components_medium_risk(self) -> None:
        engine = create_threat_intelligence()
        report = VulnerabilityReport(
            report_id="v-medium",
            cve_id=None,
            title="Medium Risk",
            description="desc",
            severity=ThreatSeverity.MEDIUM,
            cvss_score=5.5,
            affected_components=["MidLib"],
            fixed_versions=["2.0"],
            published_at=datetime.now(),
            updated_at=datetime.now(),
        )
        engine.add_vulnerability(report)
        result = engine.scan_components([{"name": "MidLib", "version": "1.0"}])
        assert result["vulnerabilities_found"] == 1

    def test_assess_threat_high_risk(self) -> None:
        engine = create_threat_intelligence()
        now = datetime.now()
        engine.add_indicator(ThreatIndicator(
            indicator_id="i-high",
            indicator_type=IOCType.IP_ADDRESS,
            value="10.0.0.1",
            source=ThreatSource.INTERNAL,
            severity=ThreatSeverity.HIGH,
            description="",
            confidence=0.8,
            first_seen=now,
            last_seen=now,
        ))
        result = engine.assess_threat_for_asset("asset-1", {"ip": "10.0.0.1"})
        assert result["risk_level"] in ("high", "critical")
        assert result["matched_iocs"] >= 1
