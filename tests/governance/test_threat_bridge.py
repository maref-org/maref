"""
ThreatGovernanceBridge 测试

覆盖审计问题 P13：威胁情报到治理层桥接。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.threat_bridge import (
    ThreatGovernanceBridge,
    ThreatGovernanceMapping,
)
from maref.governance.types import GovernanceState
from maref.monitoring.threat_intelligence import (
    ThreatAlert,
    ThreatSeverity,
)


class TestThreatGovernanceBridge:
    def test_critical_alert_triggers_halt(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        bridge = ThreatGovernanceBridge(sm)

        alert = ThreatAlert(
            alert_id="alert-1",
            alert_type="vulnerability",
            severity=ThreatSeverity.CRITICAL,
            title="Critical Vulnerability",
            description="RCE found",
            detected_at=datetime.now(),
            affected_assets=["api-server"],
            recommended_actions=["patch immediately"],
        )
        result = bridge.on_threat_alert(alert)
        assert result["triggered"] is True
        assert result["action"] == "force_halt"
        assert sm.current_state == GovernanceState.HALT

    def test_high_alert_triggers_stabilize(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        bridge = ThreatGovernanceBridge(sm)

        alert = ThreatAlert(
            alert_id="alert-2",
            alert_type="anomaly",
            severity=ThreatSeverity.HIGH,
            title="High Anomaly",
            description="Unusual traffic",
            detected_at=datetime.now(),
            affected_assets=["gateway"],
            recommended_actions=["investigate"],
        )
        result = bridge.on_threat_alert(alert)
        assert result["triggered"] is True
        assert result["action"] == "force_stabilize"
        assert sm.current_state == GovernanceState.STABILIZE

    def test_medium_alert_logs_only(self) -> None:
        sm = GovernanceStateMachine()
        bridge = ThreatGovernanceBridge(sm)

        alert = ThreatAlert(
            alert_id="alert-3",
            alert_type="ioc_match",
            severity=ThreatSeverity.MEDIUM,
            title="Medium IOC Match",
            description="Suspicious IP",
            detected_at=datetime.now(),
            affected_assets=["firewall"],
            recommended_actions=["monitor"],
        )
        result = bridge.on_threat_alert(alert)
        assert result["triggered"] is False
        assert result["action"] == "log_only"

    def test_low_alert_auto_resolves(self) -> None:
        sm = GovernanceStateMachine()
        bridge = ThreatGovernanceBridge(sm)

        alert = ThreatAlert(
            alert_id="alert-4",
            alert_type="info",
            severity=ThreatSeverity.LOW,
            title="Low Priority",
            description="Informational",
            detected_at=datetime.now(),
            affected_assets=["log-server"],
            recommended_actions=["review"],
        )
        result = bridge.on_threat_alert(alert)
        assert result["triggered"] is False
        assert alert.is_active is False
        assert alert.resolved_at is not None

    def test_custom_mapping(self) -> None:
        sm = GovernanceStateMachine()
        mapping = ThreatGovernanceMapping(
            critical_action="force_stabilize",  # 覆盖默认
            high_action="force_halt",
        )
        bridge = ThreatGovernanceBridge(sm, mapping=mapping)

        alert = ThreatAlert(
            alert_id="alert-5",
            alert_type="vulnerability",
            severity=ThreatSeverity.CRITICAL,
            title="Test",
            description="Test",
            detected_at=datetime.now(),
            affected_assets=["test"],
            recommended_actions=["test"],
        )
        result = bridge.on_threat_alert(alert)
        assert result["action"] == "force_stabilize"

    def test_get_alert_statistics(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        bridge = ThreatGovernanceBridge(sm)

        # CRITICAL triggers halt, which makes subsequent HIGH unable to trigger
        for severity in [
            ThreatSeverity.CRITICAL,
            ThreatSeverity.HIGH,
            ThreatSeverity.MEDIUM,
        ]:
            alert = ThreatAlert(
                alert_id=f"alert-{severity.value}",
                alert_type="test",
                severity=severity,
                title="Test",
                description="Test",
                detected_at=datetime.now(),
                affected_assets=["test"],
                recommended_actions=["test"],
            )
            bridge.on_threat_alert(alert)

        stats = bridge.get_alert_statistics()
        assert stats["total"] == 3
        assert stats["by_severity"]["critical"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["medium"] == 1
        # Only CRITICAL triggered action because HALT is terminal
        assert stats["actions_taken"] == 1

    def test_register_handler(self) -> None:
        sm = GovernanceStateMachine()
        bridge = ThreatGovernanceBridge(sm)
        called = []

        def handler(alert, action):
            called.append((alert.alert_id, action))

        bridge.register_handler(handler)

        alert = ThreatAlert(
            alert_id="alert-handler",
            alert_type="test",
            severity=ThreatSeverity.LOW,
            title="Test",
            description="Test",
            detected_at=datetime.now(),
            affected_assets=["test"],
            recommended_actions=["test"],
        )
        bridge.on_threat_alert(alert)
        assert len(called) == 1
        assert called[0][0] == "alert-handler"
