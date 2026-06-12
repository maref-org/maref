"""Tests for SharedStateMonitor — pollution detection."""

import time

import pytest

from maref.security.state_monitor import (
    PollutionReport,
    PollutionSeverity,
    SharedStateMonitor,
    StateMutationEvent,
)


class TestStateMutationEvent:
    def test_default_timestamp(self):
        event = StateMutationEvent(
            agent_id="agent-1", scope="global", key="x", old_value=1, new_value=2
        )
        assert event.timestamp > 0


class TestPollutionReport:
    def test_to_dict(self):
        report = PollutionReport(
            agent_id="agent-1",
            severity=PollutionSeverity.HIGH,
            reason="reason",
            affected_keys=["x"],
            mutations=[],
        )
        d = report.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["severity"] == "high"
        assert d["mutation_count"] == 0


class TestSharedStateMonitor:
    def test_initial_state(self):
        monitor = SharedStateMonitor()
        assert monitor.mutation_threshold == 0.5
        assert monitor.burst_threshold == 3
        assert not monitor._quarantined_agents

    def test_record_mutation_normal(self):
        monitor = SharedStateMonitor()
        report = monitor.record_mutation("agent-1", "global", "x", 10, 12)
        assert report is None

    def test_record_mutation_high_delta(self):
        monitor = SharedStateMonitor(mutation_threshold=0.5)
        report = monitor.record_mutation("agent-1", "global", "x", 10, 100)
        assert report is not None
        assert report.severity == PollutionSeverity.HIGH
        assert "Single-variable mutation rate" in report.reason

    def test_record_mutation_burst(self):
        monitor = SharedStateMonitor(mutation_threshold=0.5, burst_threshold=2, burst_window_seconds=60)
        # Use small deltas so mutation_threshold doesn't trigger
        monitor.record_mutation("agent-1", "global", "x", 100, 105)
        monitor.record_mutation("agent-1", "global", "y", 100, 105)
        report = monitor.record_mutation("agent-1", "global", "z", 100, 105)
        assert report is not None
        assert report.severity == PollutionSeverity.MEDIUM
        assert "Burst mutation" in report.reason

    def test_quarantined_agent_gets_critical_report(self):
        monitor = SharedStateMonitor()
        monitor.quarantine("agent-1")
        report = monitor.record_mutation("agent-1", "global", "x", 1, 2)
        assert report is not None
        assert report.severity == PollutionSeverity.CRITICAL
        assert "quarantined" in report.reason

    def test_quarantine_and_unquarantine(self):
        monitor = SharedStateMonitor()
        monitor.quarantine("agent-1")
        assert monitor.is_quarantined("agent-1")
        monitor.unquarantine("agent-1")
        assert not monitor.is_quarantined("agent-1")

    def test_unquarantine_unknown_agent(self):
        monitor = SharedStateMonitor()
        monitor.unquarantine("unknown")
        assert not monitor.is_quarantined("unknown")

    def test_get_history_all(self):
        monitor = SharedStateMonitor()
        monitor.record_mutation("agent-1", "global", "x", 1, 2)
        monitor.record_mutation("agent-2", "global", "y", 1, 2)
        history = monitor.get_history()
        assert len(history) == 2

    def test_get_history_by_agent(self):
        monitor = SharedStateMonitor()
        monitor.record_mutation("agent-1", "global", "x", 1, 2)
        monitor.record_mutation("agent-2", "global", "y", 1, 2)
        history = monitor.get_history(agent_id="agent-1")
        assert len(history) == 1
        assert history[0].agent_id == "agent-1"

    def test_compute_delta_ratio_numeric(self):
        monitor = SharedStateMonitor()
        assert monitor._compute_delta_ratio(10, 15) == 0.5
        assert monitor._compute_delta_ratio(10, 10) == 0.0

    def test_compute_delta_ratio_zero_old(self):
        monitor = SharedStateMonitor()
        assert monitor._compute_delta_ratio(0, 5) == 1.0
        assert monitor._compute_delta_ratio(0, 0) == 0.0

    def test_compute_delta_ratio_non_numeric(self):
        monitor = SharedStateMonitor()
        assert monitor._compute_delta_ratio("a", "b") == 1.0
        assert monitor._compute_delta_ratio("a", "a") == 0.0

    def test_compute_delta_ratio_exception(self):
        monitor = SharedStateMonitor()
        class BadType:
            def __sub__(self, other):
                raise TypeError("cannot subtract")

        assert monitor._compute_delta_ratio(BadType(), BadType()) == 1.0

    def test_record_mutation_appends_to_history(self):
        monitor = SharedStateMonitor()
        monitor.record_mutation("agent-1", "global", "x", 1, 2)
        monitor.record_mutation("agent-1", "global", "x", 2, 3)
        assert len(monitor._history) == 2

    def test_burst_mutation_different_agents_no_false_positive(self):
        monitor = SharedStateMonitor(mutation_threshold=0.5, burst_threshold=2, burst_window_seconds=60)
        monitor.record_mutation("agent-1", "global", "x", 100, 102)
        monitor.record_mutation("agent-2", "global", "y", 100, 102)
        report = monitor.record_mutation("agent-1", "global", "z", 100, 102)
        # agent-1 has 2 mutations (x, z), and burst_threshold=2, so 2 > 2 is False
        # Actually burst_threshold=2 means len(recent) > 2, so need 3 mutations
        # With 2 mutations (x, z), len(recent)=2, not > 2, so no burst
        # But delta is 2/100=0.02 < 0.5, so no delta trigger either
        assert report is None
