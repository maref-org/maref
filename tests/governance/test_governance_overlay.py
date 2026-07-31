"""Tests for GovernanceOverlay event loop lifecycle (governance.py).

GovernanceOverlay.run() 事件循环测试：启动、事件处理、停止、异常恢复。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.governance import GovernanceState, GovernanceStateMachine
from maref_lite.governance import GovernanceOverlay


@pytest.fixture
def temp_audit_path():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def overlay(temp_audit_path):
    sm = GovernanceStateMachine()
    ol = GovernanceOverlay(
        state_machine=sm,
        audit_log_path=str(temp_audit_path),
        oscillation_cooldown=1.0,
    )
    return ol


class TestGovernanceOverlayLifecycle:
    @pytest.mark.asyncio
    async def test_run_and_stop(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)
        assert overlay._running
        overlay.stop()
        await asyncio.sleep(0.1)
        assert not task.done() or task.cancelled()

    @pytest.mark.asyncio
    async def test_emit_and_process_event(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)
        await overlay.emit_event("oscillation_detected", rate=15.0)
        await asyncio.sleep(0.1)
        overlay.stop()
        await asyncio.sleep(0.05)
        task.cancel()

    @pytest.mark.asyncio
    async def test_event_queue_processes_oscillation(self, overlay):
        with patch.object(overlay._oscillation_loop, "detect_and_fix") as mock:
            overlay._running = True
            task = asyncio.create_task(overlay.run())
            await asyncio.sleep(0.05)
            await overlay.emit_event("oscillation_detected", rate=12.0)
            await asyncio.sleep(0.2)
            overlay.stop()
            task.cancel()
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_transition_emits_self_observation(self, overlay):
        overlay._enable_self_observation = True
        initial_count = len(overlay._self_observations)
        overlay._state_machine.transition(GovernanceState.OBSERVE, reason="test")
        assert len(overlay._self_observations) == initial_count + 1
        obs = overlay._self_observations[-1]
        assert obs.state == "OBSERVE"

    @pytest.mark.asyncio
    async def test_multiple_events_in_queue(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)
        for i in range(5):
            await overlay.emit_event("test_event", index=i)
        await asyncio.sleep(0.2)
        overlay.stop()
        task.cancel()
        assert overlay._event_queue.qsize() <= 5

    @pytest.mark.asyncio
    async def test_drift_check_high_severity(self, overlay):
        from drift_guard.types import DriftSeverity

        sm = overlay._state_machine
        chain = [GovernanceState.OBSERVE, GovernanceState.ANALYZE, GovernanceState.EVALUATE, GovernanceState.DECIDE]
        for state in chain:
            assert sm.transition(state, reason="setup"), f"Cannot transition to {state}"
        assert sm.current_state == GovernanceState.DECIDE
        mock_event = MagicMock()
        mock_event.reading.severity = DriftSeverity.HIGH
        mock_pipeline = MagicMock()
        mock_pipeline.check_drift = AsyncMock(return_value=mock_event)
        overlay._drift = mock_pipeline
        await overlay.check_drift(None, None, None, None)
        assert sm.current_state == GovernanceState.STABILIZE

    def test_decision_recording(self, overlay, temp_audit_path):
        assert len(overlay.get_decisions()) == 0
        overlay._record_decision(
            action="test_action",
            reason="test_reason",
            from_state=GovernanceState.INIT,
            to_state=GovernanceState.OBSERVE,
        )
        assert len(overlay.get_decisions()) == 1
        d = overlay.get_decisions()[0]
        assert d.action == "test_action"
        assert d.reason == "test_reason"

    def test_decision_appears_in_audit_log(self, overlay, temp_audit_path):
        overlay._record_decision("test", "unit test", GovernanceState.INIT, GovernanceState.OBSERVE)
        entries = overlay._audit.read_all()
        assert any("test" in e.action for e in entries)

    def test_force_stabilize_passthrough(self, overlay):
        result = overlay.force_stabilize(reason="test")
        assert result is True
        assert overlay._state_machine.current_state == GovernanceState.STABILIZE

    def test_transition_state_passthrough(self, overlay):
        overlay.transition_state(GovernanceState.OBSERVE)
        assert overlay._state_machine.current_state == GovernanceState.OBSERVE

    def test_get_status_returns_dict(self, overlay):
        status = overlay.get_status()
        assert "state" in status
        assert "entropy" in status
        assert "decision_count" in status
        assert status["state"] in [s.name for s in GovernanceState]

    def test_get_probe_stats(self, overlay):
        stats = overlay.get_probe_stats()
        assert "probe_counts" in stats
        assert "detector_stats" in stats
        assert "oscillation_stats" in stats


class TestGovernanceOverlayEdgeCases:
    @pytest.mark.asyncio
    async def test_anomaly_critical_triggers_stabilize(self, overlay):
        sm = overlay._state_machine
        chain = [GovernanceState.OBSERVE, GovernanceState.ANALYZE, GovernanceState.EVALUATE, GovernanceState.DECIDE]
        for state in chain:
            assert sm.transition(state, reason="setup"), f"Cannot transition to {state}"
        assert sm.current_entropy >= 3
        anomaly = MagicMock()
        anomaly.severity = "critical"
        anomaly.anomaly_type = "test_anomaly"
        anomaly.description = "critical test anomaly"
        overlay._handle_anomaly(anomaly)
        assert sm.current_state == GovernanceState.STABILIZE

    @pytest.mark.asyncio
    async def test_anomaly_medium_does_not_force_stabilize(self, overlay):
        sm = overlay._state_machine
        initial = sm.current_state
        anomaly = MagicMock()
        anomaly.severity = "medium"
        overlay._handle_anomaly(anomaly)
        assert sm.current_state == initial

    @pytest.mark.asyncio
    async def test_probe_reading_with_high_entropy(self, overlay):
        sm = overlay._state_machine
        sm.force_stabilize()
        sm.transition(GovernanceState.REPORT)
        overlay._read_probes()
        assert sm.current_state is not None

    def test_observation_store_batch_insert(self, overlay):
        from maref.observation.probes import ProbeReading, ProbeSeverity

        readings = [
            ProbeReading(probe_name="test", severity=ProbeSeverity.NORMAL, value=1.0, threshold=0.5),
            ProbeReading(probe_name="test", severity=ProbeSeverity.NORMAL, value=2.0, threshold=0.5),
        ]
        overlay._store.insert_batch(readings)
        counts = overlay._store.get_counts()
        assert counts.get("total", 0) >= 2

    def _make_transition(self, from_s=GovernanceState.OBSERVE, to_s=GovernanceState.ANALYZE, reason="test"):
        transition = MagicMock(spec=["from_state", "to_state", "reason"])
        transition.from_state = MagicMock(spec=["name"])
        transition.from_state.name = from_s.name
        transition.to_state = MagicMock(spec=["name"])
        transition.to_state.name = to_s.name
        transition.reason = reason
        return transition

    def test_self_observations_ring_buffer(self, overlay):
        transition = self._make_transition()
        for _ in range(600):
            overlay._on_state_transition(transition)
        assert len(overlay._self_observations) <= overlay._max_self_observations

    def test_callback_invocation(self, overlay):
        calls = []
        overlay.add_self_observation_callback(lambda obs: calls.append(obs))
        overlay._on_state_transition(self._make_transition())
        assert len(calls) == 1

    def test_multiple_callbacks(self, overlay):
        c1, c2 = [], []
        overlay.add_self_observation_callback(lambda obs: c1.append(obs))
        overlay.add_self_observation_callback(lambda obs: c2.append(obs))
        overlay._on_state_transition(self._make_transition())
        assert len(c1) == 1
        assert len(c2) == 1

    def test_callback_exception_isolation(self, overlay):
        """One failing callback should not affect others."""
        calls = []

        def failing(obs):
            raise ValueError("callback failed")

        def working(obs):
            calls.append(obs)

        overlay.add_self_observation_callback(failing)
        overlay.add_self_observation_callback(working)
        overlay._on_state_transition(self._make_transition())
        assert len(calls) == 1


class TestGovernanceOverlayConfig:
    def test_config_defaults(self):
        config = GovernanceOverlay()
        assert config._max_decisions == 1000
        assert config._max_self_observations == 500
        assert config._enable_self_observation is True

    def test_config_custom_values(self, temp_audit_path):
        config = GovernanceOverlay(
            max_decisions=100,
            max_self_observations=50,
            enable_self_observation=False,
            audit_log_path=str(temp_audit_path),
        )
        assert config._max_decisions == 100
        assert config._max_self_observations == 50
        assert config._enable_self_observation is False

    def test_config_audit_logger_initialized(self, temp_audit_path):
        config = GovernanceOverlay(audit_log_path=str(temp_audit_path))
        assert config._audit is not None
        entry_count = len(list(config._audit.read_all()))
        assert entry_count == 0

    def test_config_with_collector(self, temp_audit_path):
        collector = MagicMock()
        GovernanceOverlay(collector=collector, audit_log_path=str(temp_audit_path))
        collector.add_callback.assert_called_once()
