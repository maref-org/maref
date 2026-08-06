"""Unit tests for the MAREF sidecar components."""

import asyncio
import time

import pytest

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import (
    CompositeMonitor,
    DeadlockDetector,
    EntropyMonitor,
    MessageQueueMonitor,
    StateOscillationDetector,
)
from sidecar.protocol import (
    AgentId,
    AgentState,
    EntropyReading,
    Observation,
    ObservationType,
    StateSnapshot,
)


class TestMockAgentAdapter:
    """Tests for the mock agent adapter."""

    @pytest.fixture
    def adapter(self) -> MockAgentAdapter:
        return MockAgentAdapter(num_agents=3)

    @pytest.mark.asyncio
    async def test_list_agents(self, adapter: MockAgentAdapter) -> None:
        agents = await adapter.list_agents()
        assert len(agents) == 3
        assert all(isinstance(a, AgentId) for a in agents)

    @pytest.mark.asyncio
    async def test_get_state(self, adapter: MockAgentAdapter) -> None:
        agents = await adapter.list_agents()
        state = await adapter.get_state(agents[0])
        assert state is not None
        assert state.agent_id == agents[0]
        assert state.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_get_entropy(self, adapter: MockAgentAdapter) -> None:
        agents = await adapter.list_agents()
        entropy = await adapter.get_entropy(agents[0])
        assert entropy is not None
        assert entropy.value == 0.0
        assert entropy.level == "normal"

    def test_set_state(self, adapter: MockAgentAdapter) -> None:
        agents = asyncio.run(adapter.list_agents())
        adapter.set_state(agents[0], AgentState.RUNNING)
        state = asyncio.run(adapter.get_state(agents[0]))
        assert state is not None
        assert state.state == AgentState.RUNNING

    def test_set_entropy(self, adapter: MockAgentAdapter) -> None:
        agents = asyncio.run(adapter.list_agents())
        adapter.set_entropy(agents[0], 3.5)
        entropy = asyncio.run(adapter.get_entropy(agents[0]))
        assert entropy is not None
        assert entropy.value == 3.5
        assert entropy.level == "critical"


class TestObservationCollector:
    """Tests for the observation collector."""

    @pytest.fixture
    def collector(self) -> ObservationCollector:
        adapter = MockAgentAdapter(num_agents=2)
        return ObservationCollector(adapter, poll_interval=0.1)

    @pytest.mark.asyncio
    async def test_collect_once(self, collector: ObservationCollector) -> None:
        observations = await collector.collect_once()
        # 2 agents * 2 obs types = 4 observations
        assert len(observations) == 4
        assert all(isinstance(o, Observation) for o in observations)

    @pytest.mark.asyncio
    async def test_buffer_accumulation(self, collector: ObservationCollector) -> None:
        await collector.collect_once()
        await collector.collect_once()
        assert collector.get_buffer_size() == 8

    def test_get_recent(self, collector: ObservationCollector) -> None:
        asyncio.run(collector.collect_once())
        recent = collector.get_recent(2)
        assert len(recent) == 2


class TestEntropyMonitor:
    """Tests for entropy monitoring."""

    @pytest.fixture
    def monitor(self) -> EntropyMonitor:
        return EntropyMonitor(warning_threshold=1.5, critical_threshold=3.0, max_threshold=4.0)

    def test_normal_entropy(self, monitor: EntropyMonitor) -> None:
        reading = EntropyReading(source="agent-1", value=0.5)
        anomalies = monitor.process(reading)
        assert len(anomalies) == 0

    def test_warning_entropy(self, monitor: EntropyMonitor) -> None:
        reading = EntropyReading(source="agent-1", value=1.6)
        anomalies = monitor.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].severity == "warning"
        assert anomalies[0].anomaly_type == "entropy_warning"

    def test_critical_entropy(self, monitor: EntropyMonitor) -> None:
        reading = EntropyReading(source="agent-1", value=3.1)
        anomalies = monitor.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].severity == "critical"
        assert anomalies[0].anomaly_type == "entropy_critical"

    def test_max_breach(self, monitor: EntropyMonitor) -> None:
        # boundary: exactly at threshold (4.0) should NOT trigger max_breach
        reading = EntropyReading(source="agent-1", value=4.0)
        anomalies = monitor.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_critical"

    def test_max_breach_strict(self, monitor: EntropyMonitor) -> None:
        # strict greater-than: 4.01 > 4.0 triggers max_breach
        reading = EntropyReading(source="agent-1", value=4.01)
        anomalies = monitor.process(reading)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "entropy_max_breach"

    def test_entropy_spike(self, monitor: EntropyMonitor) -> None:
        # Build history with low entropy
        for _ in range(4):
            monitor.process(EntropyReading(source="agent-1", value=0.5))
        # Spike
        anomalies = monitor.process(EntropyReading(source="agent-1", value=1.5))
        # 1.5 is warning, plus spike detection
        assert any(a.anomaly_type == "entropy_spike" for a in anomalies)


class TestStateOscillationDetector:
    """Tests for state oscillation detection."""

    @pytest.fixture
    def detector(self) -> StateOscillationDetector:
        return StateOscillationDetector(window_size=5, threshold=4)

    def test_no_oscillation(self, detector: StateOscillationDetector) -> None:
        agent = AgentId(name="agent-1")
        for _ in range(5):
            snapshot = StateSnapshot(agent_id=agent, state=AgentState.RUNNING)
            anomalies = detector.process(snapshot)
        assert len(anomalies) == 0

    def test_oscillation_detected(self, detector: StateOscillationDetector) -> None:
        agent = AgentId(name="agent-1")
        states = [
            AgentState.RUNNING,
            AgentState.WAITING,
            AgentState.ERROR,
            AgentState.IDLE,
            AgentState.RUNNING,
        ]
        anomalies: list = []
        for state in states:
            snapshot = StateSnapshot(agent_id=agent, state=state)
            anomalies = detector.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "state_oscillation"


class TestDeadlockDetector:
    """Tests for deadlock detection."""

    @pytest.fixture
    def detector(self) -> DeadlockDetector:
        return DeadlockDetector(stuck_threshold_seconds=0.1)

    def test_no_deadlock(self, detector: DeadlockDetector) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, state=AgentState.RUNNING, task_progress=0.0)
        anomalies = detector.process(snapshot)
        assert len(anomalies) == 0

    def test_deadlock_detected(self, detector: DeadlockDetector) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, state=AgentState.RUNNING, task_progress=0.5)
        detector.process(snapshot)
        time.sleep(0.15)
        snapshot2 = StateSnapshot(agent_id=agent, state=AgentState.WAITING, task_progress=0.5)
        anomalies = detector.process(snapshot2)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "potential_deadlock"
        assert anomalies[0].severity == "critical"


class TestMessageQueueMonitor:
    """Tests for message queue monitoring."""

    @pytest.fixture
    def monitor(self) -> MessageQueueMonitor:
        return MessageQueueMonitor(warning_threshold=5, critical_threshold=10)

    def test_normal_queue(self, monitor: MessageQueueMonitor) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, pending_messages=3)
        anomalies = monitor.process(snapshot)
        assert len(anomalies) == 0

    def test_warning_queue(self, monitor: MessageQueueMonitor) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, pending_messages=6)
        anomalies = monitor.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].severity == "warning"

    def test_critical_queue(self, monitor: MessageQueueMonitor) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, pending_messages=12)
        anomalies = monitor.process(snapshot)
        assert len(anomalies) == 1
        assert anomalies[0].severity == "critical"


class TestCompositeMonitor:
    """Tests for the composite monitor."""

    @pytest.fixture
    def monitor(self) -> CompositeMonitor:
        return CompositeMonitor()

    def test_entropy_observation(self, monitor: CompositeMonitor) -> None:
        reading = EntropyReading(source="agent-1", value=4.0)
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        anomalies = monitor.process(obs)
        assert len(anomalies) == 1
        assert monitor.get_anomaly_count() == 1
        assert monitor.get_critical_count() == 1

    def test_state_observation(self, monitor: CompositeMonitor) -> None:
        agent = AgentId(name="agent-1")
        snapshot = StateSnapshot(agent_id=agent, state=AgentState.RUNNING, pending_messages=60)
        obs = Observation(obs_type=ObservationType.STATE_SNAPSHOT, payload=snapshot)
        anomalies = monitor.process(obs)
        assert len(anomalies) == 1  # queue critical
        assert anomalies[0].anomaly_type == "message_queue_critical"

    def test_get_recent_anomalies(self, monitor: CompositeMonitor) -> None:
        reading = EntropyReading(source="agent-1", value=4.0)
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        monitor.process(obs)
        recent = monitor.get_recent_anomalies(10)
        assert len(recent) == 1
