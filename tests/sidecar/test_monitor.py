from __future__ import annotations

import time
from dataclasses import asdict

import pytest

from sidecar.monitor import (
    Anomaly,
    AnomalyEvent,
    CompositeMonitor,
    DeadlockDetector,
    EntropyMonitor,
    MessageQueueMonitor,
    StateOscillationDetector,
)
from sidecar.protocol import AgentId, AgentState, EntropyReading, Observation, ObservationType, StateSnapshot


class TestAnomaly:
    def test_defaults(self) -> None:
        a = Anomaly()
        assert a.anomaly_type == ""
        assert a.severity == "info"
        assert a.message == ""
        assert a.description == ""
        assert a.source == ""
        assert isinstance(a.timestamp, float)

    def test_custom_values(self) -> None:
        now = time.time()
        a = Anomaly(
            anomaly_type="test_type",
            severity="critical",
            message="msg",
            description="desc",
            source="src",
            timestamp=now,
        )
        assert a.anomaly_type == "test_type"
        assert a.severity == "critical"
        assert a.message == "msg"
        assert a.description == "desc"
        assert a.source == "src"
        assert a.timestamp == now


class TestEntropyMonitor:
    def test_init_defaults(self) -> None:
        m = EntropyMonitor()
        assert m._warning_threshold == 1.5
        assert m._critical_threshold == 3.0
        assert m._max_threshold == 4.0

    def test_custom_thresholds(self) -> None:
        m = EntropyMonitor(warning_threshold=2.0, critical_threshold=4.0, max_threshold=5.0)
        assert m._warning_threshold == 2.0
        assert m._critical_threshold == 4.0
        assert m._max_threshold == 5.0

    def test_no_anomaly_below_warning(self) -> None:
        m = EntropyMonitor()
        reading = EntropyReading(value=1.0, source="test")
        anomalies = m.process(reading)
        assert anomalies == []

    def test_warning_anomaly(self) -> None:
        m = EntropyMonitor()
        reading = EntropyReading(value=2.0, source="test")
        anomalies = m.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_warning"
        assert anomalies[0].severity == "warning"

    def test_critical_anomaly(self) -> None:
        m = EntropyMonitor()
        reading = EntropyReading(value=3.5, source="test")
        anomalies = m.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_critical"
        assert anomalies[0].severity == "critical"

    def test_max_breach_anomaly(self) -> None:
        m = EntropyMonitor()
        reading = EntropyReading(value=5.0, source="test")
        anomalies = m.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_max_breach"
        assert anomalies[0].severity == "critical"

    def test_max_breach_takes_precedence(self) -> None:
        m = EntropyMonitor()
        reading = EntropyReading(value=5.0, source="test")
        anomalies = m.process(reading)
        types = {a.anomaly_type for a in anomalies}
        # Should have max_breach but not critical or warning
        assert "entropy_max_breach" in types
        assert "entropy_critical" not in types

    def test_spike_detected(self) -> None:
        m = EntropyMonitor()
        # Add 4 readings below threshold to build history
        for _ in range(4):
            m.process(EntropyReading(value=1.0, source="test"))
        # Fifth reading is a spike
        reading = EntropyReading(value=3.0, source="test")
        anomalies = m.process(reading)
        types = {a.anomaly_type for a in anomalies}
        assert "entropy_spike" in types

    def test_spike_not_detected_with_insufficient_history(self) -> None:
        m = EntropyMonitor()
        # Only 3 readings in history - need 5 for spike detection
        for _ in range(3):
            m.process(EntropyReading(value=1.0, source="test"))
        reading = EntropyReading(value=3.0, source="test")
        anomalies = m.process(reading)
        types = {a.anomaly_type for a in anomalies}
        assert "entropy_spike" not in types

    def test_spike_not_detected_below_threshold(self) -> None:
        m = EntropyMonitor()
        for _ in range(4):
            m.process(EntropyReading(value=1.0, source="test"))
        # Spike exists but below warning threshold
        reading = EntropyReading(value=1.5, source="test")
        anomalies = m.process(reading)
        types = {a.anomaly_type for a in anomalies}
        assert "entropy_spike" not in types

    def test_detect_spike_returns_false_for_empty_history(self) -> None:
        m = EntropyMonitor()
        with patch.object(m, "_history", []) as mock_history:
            # Add reading normally to trigger history append
            result = m._detect_spike(EntropyReading(value=1.0, source="test"))
            assert result is False

    def test_history_appended(self) -> None:
        m = EntropyMonitor()
        assert len(m._history) == 0
        m.process(EntropyReading(value=1.0, source="test"))
        assert len(m._history) == 1
        m.process(EntropyReading(value=2.0, source="test"))
        assert len(m._history) == 2


from unittest.mock import patch


class TestMessageQueueMonitor:
    def test_init_defaults(self) -> None:
        m = MessageQueueMonitor()
        assert m._warning_threshold == 5
        assert m._critical_threshold == 10

    def test_no_anomaly_below_warning(self) -> None:
        m = MessageQueueMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=3)
        anomalies = m.process(snapshot)
        assert anomalies == []

    def test_warning_anomaly(self) -> None:
        m = MessageQueueMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=7)
        anomalies = m.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "message_queue_warning"
        assert anomalies[0].severity == "warning"

    def test_critical_anomaly(self) -> None:
        m = MessageQueueMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=15)
        anomalies = m.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "message_queue_critical"
        assert anomalies[0].severity == "critical"

    def test_critical_takes_precedence_over_warning(self) -> None:
        m = MessageQueueMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=10)
        anomalies = m.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "message_queue_critical"

    def test_at_warning_threshold(self) -> None:
        m = MessageQueueMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=5)
        anomalies = m.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "message_queue_warning"


class TestStateOscillationDetector:
    def test_init_defaults(self) -> None:
        d = StateOscillationDetector()
        assert d._window_size == 5
        assert d._threshold == 4

    def test_not_enough_history(self) -> None:
        d = StateOscillationDetector(window_size=3, threshold=2)
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), state=AgentState.RUNNING)
        anomalies = d.process(snapshot)
        assert anomalies == []

    def test_oscillation_detected(self) -> None:
        d = StateOscillationDetector(window_size=5, threshold=4)
        agent = AgentId(name="a")
        # Submit 5 states with at least 4 distinct
        states = [AgentState.RUNNING, AgentState.WAITING, AgentState.RUNNING, AgentState.WAITING, AgentState.ERROR]
        for s in states:
            d.process(StateSnapshot(agent_id=agent, state=s))
        anomalies = d.process(StateSnapshot(agent_id=agent, state=AgentState.IDLE))
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "state_oscillation"
        assert anomalies[0].severity == "warning"

    def test_no_oscillation_few_unique(self) -> None:
        d = StateOscillationDetector(window_size=5, threshold=4)
        agent = AgentId(name="a")
        # Only 2 distinct states out of 5
        for _ in range(5):
            d.process(StateSnapshot(agent_id=agent, state=AgentState.RUNNING))
        anomalies = d.process(StateSnapshot(agent_id=agent, state=AgentState.RUNNING))
        assert anomalies == []

    def test_different_agents_independent(self) -> None:
        d = StateOscillationDetector(window_size=3, threshold=2)
        a1 = AgentId(name="a1")
        a2 = AgentId(name="a2")
        d.process(StateSnapshot(agent_id=a1, state=AgentState.RUNNING))
        d.process(StateSnapshot(agent_id=a2, state=AgentState.IDLE))
        # a1 has 1 entry, not enough
        result_a1 = d.process(StateSnapshot(agent_id=a1, state=AgentState.WAITING))
        assert result_a1 == []
        # a2 still has just 1
        result_a2 = d.process(StateSnapshot(agent_id=a2, state=AgentState.IDLE))
        assert result_a2 == []


class TestDeadlockDetector:
    def test_init_defaults(self) -> None:
        d = DeadlockDetector()
        assert d._stuck_threshold == 5.0

    def test_first_call_no_anomaly(self) -> None:
        d = DeadlockDetector()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), task_progress=0.5)
        anomalies = d.process(snapshot)
        assert anomalies == []

    def test_stuck_detected(self) -> None:
        d = DeadlockDetector(stuck_threshold_seconds=0.0)  # Immediate detection
        agent = AgentId(name="a")
        snapshot = StateSnapshot(agent_id=agent, task_progress=0.5)
        d.process(snapshot)
        # Same progress, should detect stuck
        anomalies = d.process(StateSnapshot(agent_id=agent, task_progress=0.5))
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "potential_deadlock"
        assert anomalies[0].severity == "critical"

    def test_progress_changed_no_anomaly(self) -> None:
        d = DeadlockDetector()
        agent = AgentId(name="a")
        d.process(StateSnapshot(agent_id=agent, task_progress=0.5))
        anomalies = d.process(StateSnapshot(agent_id=agent, task_progress=0.8))
        assert anomalies == []

    def test_different_agents_tracked_independently(self) -> None:
        d = DeadlockDetector(stuck_threshold_seconds=0.0)
        a1 = AgentId(name="a1")
        a2 = AgentId(name="a2")
        d.process(StateSnapshot(agent_id=a1, task_progress=0.5))
        d.process(StateSnapshot(agent_id=a2, task_progress=0.5))
        # a1 stuck, a2 also stuck (independently)
        anomalies_a1 = d.process(StateSnapshot(agent_id=a1, task_progress=0.5))
        assert len(anomalies_a1) == 1
        anomalies_a2 = d.process(StateSnapshot(agent_id=a2, task_progress=0.5))
        assert len(anomalies_a2) == 1

    def test_agent_recovered_after_change(self) -> None:
        d = DeadlockDetector(stuck_threshold_seconds=0.0)
        agent = AgentId(name="a")
        d.process(StateSnapshot(agent_id=agent, task_progress=0.5))
        d.process(StateSnapshot(agent_id=agent, task_progress=0.5))  # Stuck
        anomalies = d.process(StateSnapshot(agent_id=agent, task_progress=0.9))  # Progress
        assert anomalies == []  # Not stuck anymore


class TestCompositeMonitor:
    def test_init(self) -> None:
        m = CompositeMonitor()
        assert m._monitors == []
        assert m._anomalies == []
        assert isinstance(m._entropy_monitor, EntropyMonitor)
        assert isinstance(m._queue_monitor, MessageQueueMonitor)

    def test_add_monitor(self) -> None:
        m = CompositeMonitor()
        detector = StateOscillationDetector()
        m.add_monitor(detector)
        assert len(m._monitors) == 1
        assert m._monitors[0] is detector

    def test_check_all_default(self) -> None:
        m = CompositeMonitor()
        assert m.check_all() == []

    def test_process_entropy_observation(self) -> None:
        m = CompositeMonitor()
        reading = EntropyReading(value=3.5, source="test")
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        anomalies = m.process(obs)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_critical"

    def test_process_state_snapshot_observation(self) -> None:
        m = CompositeMonitor()
        snapshot = StateSnapshot(agent_id=AgentId(name="a"), pending_messages=15)
        obs = Observation(obs_type=ObservationType.STATE_SNAPSHOT, payload=snapshot)
        anomalies = m.process(obs)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "message_queue_critical"

    def test_process_other_observation_type(self) -> None:
        m = CompositeMonitor()
        obs = Observation(obs_type=ObservationType.MESSAGE_FLOW, payload={"msg": "hello"})
        anomalies = m.process(obs)
        assert anomalies == []

    def test_process_entropy_wrong_payload_type(self) -> None:
        m = CompositeMonitor()
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload="not an EntropyReading")
        anomalies = m.process(obs)
        assert anomalies == []

    def test_get_anomaly_count(self) -> None:
        m = CompositeMonitor()
        assert m.get_anomaly_count() == 0
        reading = EntropyReading(value=3.5, source="test")
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        m.process(obs)
        assert m.get_anomaly_count() == 1

    def test_get_critical_count(self) -> None:
        m = CompositeMonitor()
        reading = EntropyReading(value=3.5, source="test")
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        m.process(obs)
        assert m.get_critical_count() == 1

    def test_get_recent_anomalies(self) -> None:
        m = CompositeMonitor()
        for value in [3.5, 2.0, 4.5]:
            reading = EntropyReading(value=value, source="test")
            obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
            m.process(obs)
        recent = m.get_recent_anomalies(2)
        assert len(recent) == 2
        # Should return last 2, both are max_breach and warning/critical
        assert len(recent) == 2

    def test_anomaly_history_accumulates(self) -> None:
        m = CompositeMonitor()
        for i in range(3):
            reading = EntropyReading(value=2.0 + i, source="test")
            obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
            m.process(obs)
        assert m.get_anomaly_count() >= 3


class TestAnomalyEvent:
    def test_construction(self) -> None:
        event = AnomalyEvent(source="src", severity="critical", message="Something bad")
        assert event.source == "src"
        assert event.severity == "critical"
        assert event.message == "Something bad"

    def test_defaults_not_applicable(self) -> None:
        # AnomalyEvent has no defaults, all required args
        event = AnomalyEvent(source="a", severity="b", message="c")
        assert event.source == "a"
