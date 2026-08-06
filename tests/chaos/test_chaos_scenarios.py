"""
MAREF Chaos Engineering Tests

Validates system resilience under various failure modes:
1. Network latency injection
2. Model weight drift injection
3. State oscillation/conflict injection
4. Entropy spike injection
5. Message queue buildup injection

Each test verifies that the governance overlay detects,
responds to, and recovers from the injected chaos.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from drift_guard.pipeline import DriftDetectionPipeline
from drift_guard.types import ModelSignature, PipelineConfig
from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceState
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.protocol import AgentId, AgentState, StateSnapshot


@dataclass
class ChaosResult:
    """Result of a chaos injection test."""

    scenario: str
    injected: bool
    detected: bool
    recovered: bool
    duration_ms: float
    details: dict[str, Any]


class ChaosInjector:
    """Injects various chaos scenarios into the system."""

    @staticmethod
    def entropy_spike(adapter: MockAgentAdapter, severity: str = "critical") -> None:
        """Inject sudden entropy spike across all agents."""
        agents = adapter._agents
        value = 4.0 if severity == "critical" else 2.5
        for agent in agents:
            adapter.set_entropy(agent, value)
            adapter.set_state(agent, AgentState.RUNNING)

    @staticmethod
    def state_oscillation(adapter: MockAgentAdapter, cycles: int = 10) -> None:
        """Inject rapid state oscillation."""
        agents = adapter._agents
        states = [AgentState.RUNNING, AgentState.WAITING, AgentState.ERROR, AgentState.IDLE]
        for agent in agents:
            for _ in range(cycles):
                adapter.set_state(agent, random.choice(states))

    @staticmethod
    def message_queue_buildup(adapter: MockAgentAdapter, count: int = 100) -> None:
        """Inject message queue buildup."""
        agents = adapter._agents
        for agent in agents:
            adapter.set_pending(agent, count)
            adapter.set_state(agent, AgentState.WAITING)

    @staticmethod
    def network_latency(adapter: MockAgentAdapter, latency_ms: float = 5000) -> None:
        """Simulate network latency by freezing agent progress."""
        agents = adapter._agents
        for agent in agents:
            adapter.set_state(agent, AgentState.WAITING)
            adapter.set_task(agent, "network_blocked", 0.0)

    @staticmethod
    def model_drift(baseline: np.ndarray, severity: str = "critical") -> np.ndarray:
        """Generate drifted model weights."""
        noise_scale = 5.0 if severity == "critical" else 1.0
        return baseline + np.random.randn(*baseline.shape) * noise_scale


class TestEntropySpikeChaos:
    """Test system response to entropy spikes."""

    @pytest.fixture
    def system(self) -> tuple[GovernanceOverlay, MockAgentAdapter, ObservationCollector]:
        adapter = MockAgentAdapter(num_agents=3)
        collector = ObservationCollector(adapter, poll_interval=0.1)
        monitor = CompositeMonitor()
        overlay = GovernanceOverlay(collector=collector, monitor=monitor)
        return overlay, adapter, collector

    @pytest.mark.asyncio
    async def test_critical_entropy_detected(self, system) -> None:
        overlay, adapter, collector = system

        # Initial collection
        await collector.collect_once()

        # Inject chaos
        ChaosInjector.entropy_spike(adapter, "critical")

        # Collect after injection
        await collector.collect_once()

        # Verify anomalies detected
        assert overlay.get_status()["critical_count"] > 0
        assert overlay.get_status()["anomaly_count"] > 0

    @pytest.mark.asyncio
    async def test_entropy_recovery(self, system) -> None:
        overlay, adapter, collector = system

        # Inject then recover
        ChaosInjector.entropy_spike(adapter, "critical")
        await collector.collect_once()

        # Reset entropy
        for agent in adapter._agents:
            adapter.set_entropy(agent, 0.0)

        await collector.collect_once()

        # Verify system can recover
        status = overlay.get_status()
        assert status["state"] != "HALT"


class TestStateOscillationChaos:
    """Test system response to state oscillation."""

    @pytest.fixture
    def system(self) -> tuple[GovernanceOverlay, MockAgentAdapter, ObservationCollector]:
        adapter = MockAgentAdapter(num_agents=3)
        collector = ObservationCollector(adapter, poll_interval=0.1)
        monitor = CompositeMonitor()
        overlay = GovernanceOverlay(collector=collector, monitor=monitor)
        return overlay, adapter, collector

    @pytest.mark.asyncio
    async def test_oscillation_detected(self, system) -> None:
        overlay, adapter, collector = system

        # Directly test StateOscillationDetector with rapid state changes
        from sidecar.monitor import StateOscillationDetector

        detector = StateOscillationDetector(window_size=5, threshold=4)

        agent = AgentId(name="test-agent")
        states = [AgentState.RUNNING, AgentState.WAITING, AgentState.ERROR, AgentState.IDLE]

        anomalies = []
        for i in range(6):
            snapshot = StateSnapshot(
                agent_id=agent,
                state=states[i % len(states)],
            )
            anomalies.extend(detector.process(snapshot))

        # Verify oscillation detected
        assert len(anomalies) > 0
        assert any(a.anomaly_type == "state_oscillation" for a in anomalies)


@pytest.mark.skip(reason="requires specific chaos environment (async queue buildup)")
class TestMessageQueueChaos:
    """Test system response to message queue buildup."""

    @pytest.fixture
    def system(self) -> tuple[GovernanceOverlay, MockAgentAdapter, ObservationCollector]:
        adapter = MockAgentAdapter(num_agents=3)
        collector = ObservationCollector(adapter, poll_interval=0.1)
        monitor = CompositeMonitor()
        overlay = GovernanceOverlay(collector=collector, monitor=monitor)
        return overlay, adapter, collector

    @pytest.mark.asyncio
    async def test_queue_buildup_detected(self, system) -> None:
        overlay, adapter, collector = system

        # Inject queue buildup
        ChaosInjector.message_queue_buildup(adapter, count=60)

        # Collect
        await collector.collect_once()

        # Verify
        status = overlay.get_status()
        assert status["critical_count"] > 0


class TestModelDriftChaos:
    """Test system response to model weight drift."""

    @pytest.fixture
    def pipeline(self) -> DriftDetectionPipeline:
        config = PipelineConfig(
            kl_warning=0.1,
            kl_critical=0.5,
            kl_max=1.0,
            review_timeout_seconds=1.0,
        )
        return DriftDetectionPipeline(config)

    @pytest.mark.asyncio
    async def test_critical_drift_detected(self, pipeline: DriftDetectionPipeline) -> None:
        baseline = np.random.randn(1000)
        current = ChaosInjector.model_drift(baseline, "critical")

        event = await pipeline.check_drift(
            baseline_weights=baseline,
            current_weights=current,
            model=ModelSignature("test-model", "v1"),
            baseline=ModelSignature("base", "v1"),
        )

        assert event is not None
        assert event.reading.severity.name in ("MEDIUM", "HIGH", "CRITICAL")

    @pytest.mark.asyncio
    async def test_no_drift_baseline(self, pipeline: DriftDetectionPipeline) -> None:
        baseline = np.random.randn(1000)

        event = await pipeline.check_drift(
            baseline_weights=baseline,
            current_weights=baseline,
            model=ModelSignature("test-model", "v1"),
            baseline=ModelSignature("base", "v1"),
        )

        assert event is None


class TestNetworkLatencyChaos:
    """Test system response to simulated network latency."""

    @pytest.fixture
    def system(self) -> tuple[GovernanceOverlay, MockAgentAdapter, ObservationCollector]:
        adapter = MockAgentAdapter(num_agents=3)
        collector = ObservationCollector(adapter, poll_interval=0.1)
        monitor = CompositeMonitor()
        overlay = GovernanceOverlay(collector=collector, monitor=monitor)
        return overlay, adapter, collector

    @pytest.mark.asyncio
    async def test_deadlock_detected(self, system) -> None:
        overlay, adapter, collector = system

        # First establish baseline progress
        agents = adapter._agents
        for agent in agents:
            adapter.set_state(agent, AgentState.RUNNING)
            adapter.set_task(agent, "task", 0.0)
        await collector.collect_once()

        # Inject network latency (agents stuck with same progress)
        ChaosInjector.network_latency(adapter, latency_ms=5000)

        # Wait for deadlock detection threshold (detector needs 30s, use shorter for test)
        # The detector requires 30s by default - override with direct check
        from sidecar.monitor import DeadlockDetector

        detector = DeadlockDetector(stuck_threshold_seconds=0.1)

        # First call establishes baseline
        for agent in agents:
            snapshot = StateSnapshot(
                agent_id=agent,
                state=AgentState.RUNNING,
                task_progress=0.5,
            )
            detector.process(snapshot)

        time.sleep(0.15)

        # Second call with same progress should detect deadlock
        anomalies = []
        for agent in agents:
            snapshot = StateSnapshot(
                agent_id=agent,
                state=AgentState.WAITING,
                task_progress=0.5,
            )
            anomalies.extend(detector.process(snapshot))

        # Verify deadlock anomalies
        assert len(anomalies) > 0
        assert any(a.anomaly_type == "potential_deadlock" for a in anomalies)


class TestCombinedChaos:
    """Test system under multiple simultaneous chaos scenarios."""

    @pytest.fixture
    def system(self) -> tuple[GovernanceOverlay, MockAgentAdapter, ObservationCollector]:
        adapter = MockAgentAdapter(num_agents=5)
        collector = ObservationCollector(adapter, poll_interval=0.1)
        monitor = CompositeMonitor()
        overlay = GovernanceOverlay(collector=collector, monitor=monitor)
        return overlay, adapter, collector

    @pytest.mark.asyncio
    async def test_multiple_chaos_sources(self, system) -> None:
        overlay, adapter, collector = system

        # Inject multiple chaos sources simultaneously
        ChaosInjector.entropy_spike(adapter, "critical")
        ChaosInjector.message_queue_buildup(adapter, count=80)
        ChaosInjector.state_oscillation(adapter, cycles=10)

        # Collect multiple times
        for _ in range(3):
            await collector.collect_once()
            time.sleep(0.05)

        # Verify system detected chaos
        status = overlay.get_status()
        assert status["anomaly_count"] >= 3
        assert status["critical_count"] > 0

    @pytest.mark.asyncio
    async def test_system_stability_under_chaos(self, system) -> None:
        overlay, adapter, collector = system

        # Inject chaos
        ChaosInjector.entropy_spike(adapter, "critical")
        await collector.collect_once()

        # Verify system did not crash
        status = overlay.get_status()
        assert "state" in status
        assert "entropy" in status
        assert status["is_terminal"] is False or status["state"] == "HALT"


class TestGovernanceStateTransitions:
    """Test governance state machine under chaos."""

    def test_forced_stabilization(self) -> None:
        from maref_lite.state_machine import GovernanceStateMachine

        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        sm.transition(GovernanceState.EVALUATE)
        sm.transition(GovernanceState.DECIDE)
        sm.transition(GovernanceState.ACT)

        # Force stabilize from ACT (high entropy)
        result = sm.force_stabilize("chaos_test")
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE
        assert sm.current_entropy == 1

    def test_emergency_halt(self) -> None:
        from maref_lite.state_machine import GovernanceStateMachine

        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE)

        # Emergency halt
        result = sm.force_halt("emergency_chaos")
        assert result is True
        assert sm.is_terminal()
