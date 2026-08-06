"""Tests for ObsBridge (sidecar integration)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.oscillation import OscillationFixLoop
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.obs import MarefObsClient, TelemetryLevel
from sidecar.obs_bridge import ObsBridge


class TestObsBridge:
    def setup_method(self) -> None:
        MarefObsClient.reset_default()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="maref_bridge_test_"))
        self._client = MarefObsClient(
            level=TelemetryLevel.STANDARD,
            base_dir=self._tmpdir,
        )
        self._bridge = ObsBridge(client=self._client)

    def test_wire_state_machine_logs_transitions(self) -> None:
        sm = GovernanceStateMachine()
        self._bridge.wire_state_machine(sm)
        sm.transition(GovernanceState.OBSERVE, reason="test")
        events = self._client.get_all_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "state_transition"

    def test_wire_state_machine_multiple_transitions(self) -> None:
        sm = GovernanceStateMachine()
        self._bridge.wire_state_machine(sm)
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        assert self._client.count_events()["state_transition"] == 2

    def test_wire_circuit_breaker(self) -> None:
        cb = CircuitBreaker(max_depth=1, max_consecutive_failures=2)
        self._bridge.wire_circuit_breaker(cb)
        cb.check_depth(3)
        events = self._client.get_all_events()
        assert len(events) >= 1
        trip_events = [e for e in events if e["event_type"] == "breaker_trip"]
        assert len(trip_events) >= 1

    def test_wire_oscillation_loop(self) -> None:
        calls: list[bool] = []

        def fake_stabilize(reason: str = "") -> None:
            calls.append(True)

        loop = OscillationFixLoop(stabilize_fn=fake_stabilize, cooldown_seconds=0.01, max_rate=1.0)
        self._bridge.wire_oscillation_loop(loop)

        import asyncio

        result = asyncio.run(loop.detect_and_fix(rate=5.0, entropy=3, current_state="ACT"))

        events = self._client.get_all_events()
        detected = [e for e in events if e["event_type"] == "oscillation_detected"]
        assert len(detected) >= 1

    def test_wire_multiple_components(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(max_depth=1)

        self._bridge.wire_state_machine(sm)
        self._bridge.wire_circuit_breaker(cb)

        sm.transition(GovernanceState.OBSERVE)
        cb.check_depth(3)

        events = self._client.get_all_events()
        types = {e["event_type"] for e in events}
        assert "state_transition" in types
        assert "breaker_trip" in types
