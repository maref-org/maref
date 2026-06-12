"""Tests for BehaviorMonitor — emergent behavior detection."""



from maref.security.behavior_monitor import BehaviorAnomaly, BehaviorBaseline, BehaviorMonitor


class TestBehaviorBaseline:
    def test_to_dict(self):
        baseline = BehaviorBaseline(
            agent_id="agent-1",
            avg_ops_per_minute=5.5,
            avg_chain_depth=2.0,
            tool_usage_distribution={"read": 0.5, "write": 0.5},
            sample_count=10,
        )
        d = baseline.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["avg_ops_per_minute"] == 5.5
        assert d["sample_count"] == 10


class TestBehaviorAnomaly:
    def test_to_dict(self):
        anomaly = BehaviorAnomaly(
            agent_id="agent-1",
            severity="high",
            deviation_sigma=4.5,
            metric_name="ops_per_minute",
            expected_value=5.0,
            actual_value=20.0,
        )
        d = anomaly.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["severity"] == "high"
        assert d["metric"] == "ops_per_minute"


class TestBehaviorMonitor:
    def test_initial_state(self):
        monitor = BehaviorMonitor()
        assert monitor.sigma_threshold == 3.0

    def test_custom_sigma_threshold(self):
        monitor = BehaviorMonitor(sigma_threshold=2.5)
        assert monitor.sigma_threshold == 2.5

    def test_get_baseline_none_when_no_data(self):
        monitor = BehaviorMonitor()
        assert monitor.get_baseline("unknown") is None

    def test_record_activity(self):
        monitor = BehaviorMonitor()
        monitor.record_activity("agent-1", ops_count=5, chain_depth=2, tools_used=["read", "write"])
        assert len(monitor._samples["agent-1"]) == 1

    def test_record_activity_triggers_baseline_update(self):
        monitor = BehaviorMonitor()
        for _ in range(15):
            monitor.record_activity("agent-1", ops_count=5, chain_depth=2, tools_used=["read"])
        baseline = monitor.get_baseline("agent-1")
        assert baseline is not None
        assert baseline.sample_count == 10
        assert baseline.avg_ops_per_minute == 5.0

    def test_record_activity_baseline_not_updated_below_5_samples(self):
        monitor = BehaviorMonitor()
        for _ in range(4):
            monitor.record_activity("agent-1", ops_count=5, chain_depth=2)
        assert monitor.get_baseline("agent-1") is None

    def test_detect_anomalies_returns_empty_when_no_baseline(self):
        monitor = BehaviorMonitor()
        anomalies = monitor.detect_anomalies("agent-1")
        assert anomalies == []

    def test_detect_anomalies_with_anomalous_ops(self):
        monitor = BehaviorMonitor()
        # Normal pattern with some variation so std > 0
        for i in range(14):
            monitor.record_activity("agent-1", ops_count=5 + (i % 3), chain_depth=1)
        # Anomalous: large spike
        monitor.record_activity("agent-1", ops_count=100, chain_depth=1)
        monitor.record_activity("agent-1", ops_count=100, chain_depth=1)

        anomalies = monitor.detect_anomalies("agent-1")
        assert len(anomalies) >= 1
        assert any(a.metric_name == "ops_per_minute" for a in anomalies)

    def test_detect_anomalies_with_anomalous_depth(self):
        monitor = BehaviorMonitor()
        for i in range(14):
            monitor.record_activity("agent-1", ops_count=5, chain_depth=1 + (i % 2))
        # Anomalous depth (far from baseline mean ~1.5, std ~0.5)
        monitor.record_activity("agent-1", ops_count=5, chain_depth=50)
        monitor.record_activity("agent-1", ops_count=5, chain_depth=50)

        anomalies = monitor.detect_anomalies("agent-1")
        assert len(anomalies) >= 1
        assert any(a.metric_name == "chain_depth" for a in anomalies)

    def test_detect_emergent_behavior(self):
        monitor = BehaviorMonitor()
        for i in range(14):
            monitor.record_activity("agent-1", ops_count=5 + (i % 3), chain_depth=1 + (i % 2))
            monitor.record_activity("agent-2", ops_count=5 + (i % 3), chain_depth=1 + (i % 2))

        # Anomalous for both agents
        for _ in range(5):
            monitor.record_activity("agent-1", ops_count=100, chain_depth=20)
            monitor.record_activity("agent-2", ops_count=100, chain_depth=20)

        emergent = monitor.detect_emergent_behavior(["agent-1", "agent-2"])
        # Should detect emergent because both have high anomalies
        assert len(emergent) >= 1
        assert any("emergent_" in a.metric_name for a in emergent)

    def test_detect_emergent_no_escalation_if_single_agent(self):
        monitor = BehaviorMonitor()
        for _ in range(14):
            monitor.record_activity("agent-1", ops_count=5, chain_depth=1)
            monitor.record_activity("agent-2", ops_count=5, chain_depth=1)

        for _ in range(5):
            monitor.record_activity("agent-1", ops_count=100, chain_depth=20)
            monitor.record_activity("agent-2", ops_count=5, chain_depth=1)

        emergent = monitor.detect_emergent_behavior(["agent-1", "agent-2"])
        assert len(emergent) == 0

    def test_severity_from_sigma_critical(self):
        monitor = BehaviorMonitor()
        assert monitor._severity_from_sigma(6.0) == "critical"
        assert monitor._severity_from_sigma(5.1) == "critical"

    def test_severity_from_sigma_high(self):
        monitor = BehaviorMonitor()
        assert monitor._severity_from_sigma(4.5) == "high"

    def test_severity_from_sigma_medium(self):
        monitor = BehaviorMonitor()
        assert monitor._severity_from_sigma(3.5) == "medium"

    def test_severity_from_sigma_low(self):
        monitor = BehaviorMonitor()
        assert monitor._severity_from_sigma(3.0) == "low"
        assert monitor._severity_from_sigma(0.0) == "low"

    def test_max_samples_limit(self):
        monitor = BehaviorMonitor()
        monitor._max_samples = 5
        for _ in range(20):
            monitor.record_activity("agent-1", ops_count=5)
        assert len(monitor._samples["agent-1"]) == 5

    def test_record_activity_no_tools(self):
        monitor = BehaviorMonitor()
        monitor.record_activity("agent-1", ops_count=3, chain_depth=1)
        assert monitor._samples["agent-1"][0]["tools_used"] == []

    def test_baseline_tool_distribution(self):
        monitor = BehaviorMonitor()
        for _ in range(12):
            monitor.record_activity("agent-1", ops_count=5, chain_depth=1, tools_used=["read", "write"])
        baseline = monitor.get_baseline("agent-1")
        assert baseline is not None
        assert "read" in baseline.tool_usage_distribution
        assert baseline.tool_usage_distribution["read"] == 0.5

    def test_detect_emergent_behavior_empty_agent_list(self):
        monitor = BehaviorMonitor()
        emergent = monitor.detect_emergent_behavior([])
        assert emergent == []
