from __future__ import annotations

from maref.monitoring.safety_dashboard import (
    SafetyDashboard,
    DashboardWidget,
    TrustScoreWidget,
    ThreatDetectionWidget,
    ComplianceStatusWidget,
)


class TestSafetyDashboard:
    """S12: 安全仪表板测试"""

    def test_dashboard_initialization(self):
        dashboard = SafetyDashboard()
        assert dashboard.title == "MAREF Safety Dashboard"
        assert len(dashboard.widgets) == 0

    def test_add_widget(self):
        dashboard = SafetyDashboard()
        widget = TrustScoreWidget()
        widget.widget_id = "w1"
        dashboard.add_widget(widget)
        assert len(dashboard.widgets) == 1
        assert dashboard.widgets[0].widget_id == "w1"

    def test_trust_score_widget(self):
        widget = TrustScoreWidget()

        # 添加几个 agent 的信任分数
        widget.update_trust("agent-1", 90.0)
        widget.update_trust("agent-2", 60.0)
        widget.update_trust("agent-3", 30.0)

        snapshot = widget.snapshot()
        assert snapshot["widget_type"] == "trust_score"
        assert len(snapshot["agents"]) == 3
        assert snapshot["avg_trust"] == 60.0
        assert snapshot["highest"]["agent_id"] == "agent-1"
        assert snapshot["lowest"]["agent_id"] == "agent-3"

    def test_threat_detection_widget(self):
        widget = ThreatDetectionWidget()

        widget.report_threat("threat-1", "high", "Cross-agent poisoning detected", source="S5")
        widget.report_threat("threat-2", "critical", "Byzantine behavior detected", source="S8")
        widget.report_threat("threat-3", "low", "Suspicious message pattern", source="S6")

        snapshot = widget.snapshot()
        assert snapshot["total_threats"] == 3
        assert snapshot["critical_count"] == 1
        assert snapshot["high_count"] == 1

    def test_threat_detection_auto_resolve(self):
        widget = ThreatDetectionWidget()

        widget.report_threat("threat-1", "high", "Test threat")
        widget.resolve_threat("threat-1")

        snapshot = widget.snapshot()
        assert snapshot["total_threats"] == 0

    def test_compliance_status_widget(self):
        widget = ComplianceStatusWidget()

        widget.update_status("five_eyes", "compliant")
        widget.update_status("eu_ai_act", "partial")
        widget.update_status("gdpr", "non_compliant")

        snapshot = widget.snapshot()
        assert snapshot["frameworks"]["five_eyes"] == "compliant"
        assert snapshot["overall"] == "non_compliant"  # 取最低值

    def test_dashboard_full_snapshot(self):
        dashboard = SafetyDashboard()

        trust = TrustScoreWidget()
        trust.update_trust("agent-1", 85.0)
        dashboard.add_widget(trust)

        threat = ThreatDetectionWidget()
        threat.report_threat("t1", "high", "test threat")
        dashboard.add_widget(threat)

        compliance = ComplianceStatusWidget()
        compliance.update_status("five_eyes", "compliant")
        dashboard.add_widget(compliance)

        snapshot = dashboard.snapshot()
        assert "trust_score" in snapshot["widgets"]
        assert "threat_detection" in snapshot["widgets"]
        assert "compliance_status" in snapshot["widgets"]

    def test_threat_timeline(self):
        import time
        widget = ThreatDetectionWidget()

        t1 = time.time()
        widget.report_threat("t1", "high", "threat 1")
        widget.report_threat("t2", "critical", "threat 2")
        t2 = time.time()

        history = widget.get_timeline(start_time=t1, end_time=t2)
        assert len(history) == 2
        assert history[0]["threat_id"] == "t1"

    def test_dashboard_critical_alerts_count(self):
        widget = ThreatDetectionWidget()
        widget.report_threat("t1", "critical", "critical threat 1")
        widget.report_threat("t2", "critical", "critical threat 2")
        widget.report_threat("t3", "low", "low threat")

        snapshot = widget.snapshot()
        assert snapshot["critical_count"] == 2
