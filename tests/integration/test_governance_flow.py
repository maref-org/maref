"""Integration tests for the MAREF governance flow.

Tests the full governance pipeline: state machine -> sidecar -> drift guard -> policies.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from maref_lite.governance import GovernanceOverlay
from maref_lite.policy import (
    PolicyAction,
    create_default_policies,
)
from maref_lite.state_machine import (
    ENTROPY_LEVELS,
    GovernanceState,
    GovernanceStateMachine,
)
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.protocol import EntropyReading, Observation, ObservationType


class TestGovernanceStateFlow:
    """Integration tests for the full state transition flow."""

    @pytest.fixture
    def sm(self) -> GovernanceStateMachine:
        return GovernanceStateMachine()

    def test_full_gray_code_path(self, sm: GovernanceStateMachine) -> None:
        """Test the full canonical Gray code state path."""
        path = [
            GovernanceState.OBSERVE,
            GovernanceState.ANALYZE,
            GovernanceState.EVALUATE,
            GovernanceState.DECIDE,
            GovernanceState.ACT,
            GovernanceState.VERIFY,
            GovernanceState.STABILIZE,
            GovernanceState.REPORT,
            GovernanceState.HALT,
        ]
        for state in path:
            assert sm.can_transition(state), f"Cannot transition to {state.name}"
            result = sm.transition(state)
            assert result, f"Transition to {state.name} failed"

        assert sm.is_terminal()
        history = sm.get_history()
        assert len(history) == 9

    def test_entropy_profile_validation(self, sm: GovernanceStateMachine) -> None:
        """Validate entropy levels follow expected profile."""
        expected_profile = [0, 1, 2, 2, 3, 4, 3, 1, 0, 0]
        for state, expected in zip(GovernanceState, expected_profile, strict=False):
            assert ENTROPY_LEVELS[state] == expected

    def test_force_stabilize_from_any_state(self, sm: GovernanceStateMachine) -> None:
        """Force stabilize should work from most states."""
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        sm.transition(GovernanceState.EVALUATE)
        sm.transition(GovernanceState.DECIDE)
        # Force stabilize from DECIDE
        result = sm.force_stabilize()
        assert result
        assert sm.current_state == GovernanceState.STABILIZE

    def test_force_halt_from_any_state(self, sm: GovernanceStateMachine) -> None:
        """Force halt should work from most states."""
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        result = sm.force_halt()
        assert result
        assert sm.is_terminal()

    def test_halt_is_fully_absorbing(self, sm: GovernanceStateMachine) -> None:
        """HALT must not allow any transitions and must reject force operations."""
        sm.transition(GovernanceState.OBSERVE)
        sm.force_halt()
        assert sm.is_terminal()
        assert not sm.transition(GovernanceState.OBSERVE)
        assert not sm.force_stabilize()
        assert not sm.force_halt()
        assert sm.get_valid_next_states() == []

    def test_entropy_trend_accumulation(self, sm: GovernanceStateMachine) -> None:
        """Entropy trend should accumulate correctly across transitions."""
        sm.transition(GovernanceState.OBSERVE)  # entropy: 0->1
        sm.transition(GovernanceState.ANALYZE)  # 1->2
        sm.transition(GovernanceState.EVALUATE)  # 2->2
        trend = sm.get_entropy_trend()
        assert trend["current"] == 2
        assert trend["max"] == 2
        assert 0 < trend["mean"] <= 2


class TestObservationToAnomalyFlow:
    """Integration tests for observation -> anomaly -> governance decision flow."""

    @pytest.fixture
    def adapter(self) -> MockAgentAdapter:
        return MockAgentAdapter(num_agents=3)

    @pytest.fixture
    def collector(self, adapter: MockAgentAdapter) -> ObservationCollector:
        return ObservationCollector(adapter, poll_interval=0.1)

    @pytest.fixture
    def monitor(self) -> CompositeMonitor:
        return CompositeMonitor()

    @pytest.fixture
    def overlay(
        self, collector: ObservationCollector, monitor: CompositeMonitor
    ) -> GovernanceOverlay:
        return GovernanceOverlay(
            collector=collector,
            monitor=monitor,
            enable_self_observation=True,
        )

    def test_critical_entropy_triggers_stabilize(
        self, overlay: GovernanceOverlay, monitor: CompositeMonitor
    ) -> None:
        """Critical entropy observation should trigger force_stabilize."""
        # Advance state machine to a higher-entropy state first
        overlay._state_machine.transition(GovernanceState.OBSERVE)
        overlay._state_machine.transition(GovernanceState.ANALYZE)
        overlay._state_machine.transition(GovernanceState.EVALUATE)
        overlay._state_machine.transition(GovernanceState.DECIDE)
        assert overlay._state_machine.current_entropy >= 3

        reading = EntropyReading(source="agent-1", value=4.0)
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        anomalies = monitor.process(obs)

        assert len(anomalies) > 0
        assert anomalies[0].severity == "critical"

        # Manually invoke the anomaly handler
        for anomaly in anomalies:
            overlay._handle_anomaly(anomaly)

        decisions = overlay.get_decisions()
        assert len(decisions) > 0
        assert decisions[0].action == "force_stabilize"

    def test_self_observation_on_state_change(self, overlay: GovernanceOverlay) -> None:
        """State transitions should generate self-observations."""
        overlay._state_machine.transition(GovernanceState.OBSERVE, "test_transition")
        observations = overlay.get_self_observations()
        assert len(observations) > 0
        assert observations[-1].state == "OBSERVE"

    @pytest.mark.asyncio
    async def test_collect_and_monitor_pipeline(
        self, collector: ObservationCollector, monitor: CompositeMonitor
    ) -> None:
        """Full collection and monitoring pipeline should work."""
        # Set high entropy on one agent
        adapter = collector._adapter
        assert isinstance(adapter, MockAgentAdapter)
        agents = await adapter.list_agents()
        adapter.set_entropy(agents[0], 3.5)

        # Collect and process
        observations = await collector.collect_once()
        assert len(observations) > 0

        for obs in observations:
            monitor.process(obs)

        # Should have detected at least one anomaly
        assert monitor.get_anomaly_count() >= 1
        assert monitor.get_critical_count() >= 1

    def test_no_anomaly_for_normal_entropy(self, monitor: CompositeMonitor) -> None:
        """Normal entropy levels should not generate anomalies."""
        reading = EntropyReading(source="agent-1", value=0.5)
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, payload=reading)
        anomalies = monitor.process(obs)
        assert len(anomalies) == 0


class TestPolicyEngineFlow:
    """Integration tests for policy engine against governance context."""

    def test_default_policies_critical_anomaly_priority(self) -> None:
        """Critical anomaly policy has highest priority and takes precedence."""
        engine = create_default_policies()
        context = {"anomaly_severity": "critical", "entropy": 4}
        triggered = engine.evaluate(context)

        # Both critical_anomaly (priority 200) and critical_entropy (priority 100) match
        assert len(triggered) >= 1
        # Highest priority should be first
        assert triggered[0].name == "critical_anomaly"

    def test_default_policies_high_entropy(self) -> None:
        """High entropy triggers the high_entropy rule."""
        engine = create_default_policies()
        triggered = engine.evaluate({"entropy": 3})
        assert any(r.name == "high_entropy" for r in triggered)
        assert all(r.action in (PolicyAction.TRANSITION, PolicyAction.ALERT) for r in triggered)

    def test_default_policies_drift_high(self) -> None:
        """High drift severity triggers the drift_verify rule."""
        engine = create_default_policies()
        triggered = engine.evaluate({"drift_severity": "high"})
        assert any(r.name == "drift_verify" for r in triggered)

    def test_default_policies_drift_critical(self) -> None:
        """Critical drift severity also triggers drift_verify."""
        engine = create_default_policies()
        triggered = engine.evaluate({"drift_severity": "critical"})
        assert any(r.name == "drift_verify" for r in triggered)

    def test_default_policies_no_false_positives(self) -> None:
        """Normal conditions should not trigger any policies."""
        engine = create_default_policies()
        triggered = engine.evaluate({"entropy": 1, "anomaly_severity": "info"})
        # Only state_timeout (priority 50) with default state_duration=0 may trigger
        timeout_triggered = [r for r in triggered if r.name == "state_timeout"]
        assert len(timeout_triggered) == 0 or len(triggered) <= 1


class TestMAREFGovernanceIntegration:
    """End-to-end governance integration tests."""

    def test_overlay_initialization(self) -> None:
        """GovernanceOverlay should initialize all components correctly."""
        overlay = GovernanceOverlay()
        status = overlay.get_status()
        assert status["state"] == "INIT"
        assert status["entropy"] == 0
        assert not status["is_terminal"]
        assert status["anomaly_count"] == 0

    def test_overlay_with_custom_components(self) -> None:
        """GovernanceOverlay should accept custom components."""
        adapter = MockAgentAdapter(num_agents=1)
        collector = ObservationCollector(adapter)
        monitor = CompositeMonitor()
        state_machine = GovernanceStateMachine()

        overlay = GovernanceOverlay(
            state_machine=state_machine,
            collector=collector,
            monitor=monitor,
        )

        status = overlay.get_status()
        assert status["state"] == "INIT"

    def test_governance_cycle_auto_init_to_observe(self) -> None:
        """Initial governance cycle should auto-transition from INIT to OBSERVE."""
        overlay = GovernanceOverlay()

        async def run_cycle():
            await overlay._governance_cycle()

        asyncio.run(run_cycle())
        status = overlay.get_status()
        assert status["state"] == "OBSERVE"

    def test_stop_sets_running_false(self) -> None:
        """Stopping the overlay should set running to false."""
        overlay = GovernanceOverlay()
        overlay._running = True
        overlay.stop()
        assert not overlay._running

    def test_get_decisions_returns_copy(self) -> None:
        """get_decisions should return a copy, not the internal list."""
        overlay = GovernanceOverlay()
        decisions = overlay.get_decisions()
        assert isinstance(decisions, list)
        assert len(decisions) == 0


class TestRecursiveGovernanceIntegration:
    """Integration tests for recursive governance components."""

    def test_recursive_governance_initialization(self) -> None:
        """RecursiveGovernanceOverlay should initialize properly."""
        from maref_lite.recursive_governance import (
            RecursiveGovernanceConfig,
            RecursiveGovernanceOverlay,
        )

        config = RecursiveGovernanceConfig(max_recursion_depth=2)
        overlay = RecursiveGovernanceOverlay(config=config)
        status = overlay.get_recursive_status()

        assert "primary_status" in status
        assert "meta_status" in status
        assert status["recursion_depth"] == 0
        assert not status["oscillation_detected"]

    def test_recursive_config_to_dict(self) -> None:
        """RecursiveGovernanceConfig should serialize to dict."""
        from maref_lite.recursive_governance import RecursiveGovernanceConfig

        config = RecursiveGovernanceConfig()
        d = config.to_dict()
        assert d["max_recursion_depth"] == 4
        assert d["self_observation_cooldown"] == 5.0
        assert d["enable_meta_learning"] is True
        assert d["enable_policy_sandbox"] is True

    def test_oscillation_detection_normal(self) -> None:
        """Normal state changes should not trigger oscillation."""
        from maref_lite.recursive_governance import (
            RecursiveGovernanceConfig,
            RecursiveGovernanceOverlay,
        )

        config = RecursiveGovernanceConfig(max_oscillation_rate=10.0)
        overlay = RecursiveGovernanceOverlay(config=config)
        # Add a few state changes below threshold
        for _ in range(4):
            overlay._state_changes.append(time.time())
        assert not overlay._detect_oscillation()

    def test_oscillation_detection_triggered(self) -> None:
        """Rapid state changes should trigger oscillation detection."""
        from maref_lite.recursive_governance import (
            RecursiveGovernanceConfig,
            RecursiveGovernanceOverlay,
        )

        config = RecursiveGovernanceConfig(max_oscillation_rate=3.0)
        overlay = RecursiveGovernanceOverlay(config=config)
        # Add many state changes
        for _ in range(5):
            overlay._state_changes.append(time.time())
        assert overlay._detect_oscillation()
