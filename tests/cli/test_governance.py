from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from maref.governance import GovernanceState

from maref_lite.governance import GovernanceDecision, GovernanceOverlay, SelfObservation


class TestGovernanceDecision:
    def test_default_metadata(self) -> None:
        d = GovernanceDecision(action="test", reason="test", from_state="A", to_state="B")
        assert d.metadata == {}

    def test_all_fields(self) -> None:
        d = GovernanceDecision(
            action="transition",
            reason="test",
            from_state="INIT",
            to_state="OBSERVE",
            metadata={"key": "val"},
        )
        assert d.action == "transition"
        assert d.reason == "test"
        assert d.metadata == {"key": "val"}


class TestSelfObservation:
    def test_defaults(self) -> None:
        o = SelfObservation(timestamp=1.0, state="INIT", entropy=0, decision_count=0, anomaly_count=0, critical_count=0)
        assert o.metadata == {}

    def test_all_fields(self) -> None:
        o = SelfObservation(
            timestamp=100.0,
            state="OBSERVE",
            entropy=2,
            decision_count=10,
            anomaly_count=3,
            critical_count=1,
            metadata={"from": "INIT"},
        )
        assert o.state == "OBSERVE"
        assert o.entropy == 2


class TestGovernanceOverlay:
    def test_init_defaults(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm:
            overlay = GovernanceOverlay()
            assert overlay._max_decisions == 1000
            assert overlay._max_self_observations == 500
            assert overlay._running is False

    def test_init_with_collector_adds_callback(self) -> None:
        collector = MagicMock()
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay(collector=collector)
            collector.add_callback.assert_called_once()

    def test_get_status(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.current_state.name = "INIT"
            mock_sm.current_entropy = 0
            mock_sm.get_entropy_trend.return_value = {}
            mock_sm.is_terminal.return_value = False
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            status = overlay.get_status()
            assert status["state"] == "INIT"
            assert status["entropy"] == 0
            assert status["is_terminal"] is False

    def test_get_decisions(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            assert overlay.get_decisions() == []

    def test_transition_state(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.transition.return_value = True
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            result = overlay.transition_state(GovernanceState.OBSERVE, "testing")
            assert result is True
            mock_sm.transition.assert_called_once_with(GovernanceState.OBSERVE, "testing")

    def test_force_stabilize(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.force_stabilize.return_value = True
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            result = overlay.force_stabilize("emergency")
            assert result is True
            mock_sm.force_stabilize.assert_called_once_with("emergency")

    def test_stop(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            overlay._running = True
            overlay.stop()
            assert overlay._running is False

    def test_add_self_observation_callback(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            cb = MagicMock()
            overlay.add_self_observation_callback(cb)
            assert cb in overlay._self_observation_callbacks

    def test_get_self_observations(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            result = overlay.get_self_observations()
            assert result == []

    def test_get_self_observations_with_data(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            for i in range(10):
                overlay._self_observations.append(
                    SelfObservation(
                        timestamp=float(i),
                        state="OBSERVE",
                        entropy=i % 4,
                        decision_count=i,
                        anomaly_count=0,
                        critical_count=0,
                    )
                )
            result = overlay.get_self_observations(n=3)
            assert len(result) == 3

    def test_emit_event(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            import asyncio

            asyncio.run(overlay.emit_event("test", key="value"))
            assert overlay._event_queue.qsize() == 1

    def test_probe_stats(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.current_state.name = "INIT"
            mock_sm.current_entropy = 2
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            stats = overlay.get_probe_stats()
            assert "probe_counts" in stats
            assert "severity_counts" in stats
            assert "total_readings" in stats
            assert "detector_stats" in stats

    def test_get_audit_log(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            with patch("maref_lite.governance.AuditLogger") as MockAudit:
                instance = MockAudit.return_value
                instance.read_all.return_value = []
                overlay = GovernanceOverlay()
                log = overlay.get_audit_log()
                assert log == []

    def test_handle_anomaly_critical(self) -> None:
        from maref.governance import GovernanceState
        from sidecar.monitor import Anomaly

        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.current_entropy = 4
            mock_sm.current_state = GovernanceState.ANALYZE
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            anomaly = MagicMock(spec=Anomaly)
            anomaly.severity = "critical"
            anomaly.anomaly_type = "high_entropy"
            anomaly.description = "Entropy spike detected"

            overlay._handle_anomaly(anomaly)
            mock_sm.force_stabilize.assert_called_once()

    def test_handle_anomaly_low_entropy_no_action(self) -> None:
        from sidecar.monitor import Anomaly

        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.current_entropy = 1
            mock_sm_cls.return_value = mock_sm

            overlay = GovernanceOverlay()
            anomaly = MagicMock(spec=Anomaly)
            anomaly.severity = "critical"

            overlay._handle_anomaly(anomaly)
            mock_sm.force_stabilize.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_drift_no_pipeline(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay(drift_pipeline=None)
            result = await overlay.check_drift(None, None, None, None)
            assert result is None

    @pytest.mark.asyncio
    async def test_check_drift_critical(self) -> None:
        from drift_guard.types import DriftSeverity, ModelSignature

        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.can_transition.return_value = False
            mock_sm_cls.return_value = mock_sm

            pipeline = MagicMock()
            event = MagicMock()
            event.reading.severity = DriftSeverity.CRITICAL
            pipeline.check_drift = AsyncMock(return_value=event)

            overlay = GovernanceOverlay(drift_pipeline=pipeline)
            await overlay.check_drift(None, None, None, None)
            mock_sm.force_stabilize.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_drift_low_severity(self) -> None:
        from drift_guard.types import DriftSeverity, ModelSignature

        with patch("maref_lite.governance.GovernanceStateMachine") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm_cls.return_value = mock_sm

            pipeline = MagicMock()
            event = MagicMock()
            event.reading.severity = DriftSeverity.LOW
            pipeline.check_drift = AsyncMock(return_value=event)

            overlay = GovernanceOverlay(drift_pipeline=pipeline)
            await overlay.check_drift(None, None, None, None)
            mock_sm.force_stabilize.assert_not_called()
            mock_sm.transition.assert_not_called()

    def test_setup_probes(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            overlay = GovernanceOverlay()
            probes = overlay._probe_registry._probes
            assert len(probes) == 5

    def test_record_decision_trims(self) -> None:
        with patch("maref_lite.governance.GovernanceStateMachine"):
            with patch("maref_lite.governance.AuditLogger"):
                overlay = GovernanceOverlay(max_decisions=3)
                for i in range(5):
                    overlay._record_decision(
                        "test", f"reason_{i}",
                        GovernanceState.INIT,
                        GovernanceState.OBSERVE,
                    )
                assert len(overlay._decisions) == 3
