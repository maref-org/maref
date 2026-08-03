"""v0.47 S10 — RuntimeBehaviorProbe 运行时装配 + 事件订阅收窄.

1. ``assemble_runtime_behavior_probe`` wires ``AuditBus + TrustEngineV2 +
   CircuitBreaker`` and returns a started probe — a single production
   assembly point for the sidecar / orchestration layer.

2. The probe's default subscription is narrowed to governance events
   (``state_transition`` / ``audit``) instead of the all-events wildcard,
   reducing false positives from unrelated traffic.
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.agent.behavior_analyzer import (
    RuntimeBehaviorProbe,
    assemble_runtime_behavior_probe,
)
from maref.governance.audit_bus import AuditBus
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.recursive.trust_engine_v2 import TrustEngineV2


def _bus_log(bus: AuditBus, event_type: str, actor: str, action: str, duration_ms: float) -> None:
    bus.log(
        event_type=event_type,
        actor=actor,
        action=action,
        metadata={"duration_ms": duration_ms},
    )


class TestAssembly:
    def test_assemble_returns_started_probe(self) -> None:
        probe = assemble_runtime_behavior_probe()
        assert isinstance(probe, RuntimeBehaviorProbe)
        assert probe.started is True

    def test_assemble_wires_components(self) -> None:
        bus = AuditBus()
        trust = TrustEngineV2()
        cb = CircuitBreaker()
        probe = assemble_runtime_behavior_probe(
            audit_bus=bus, trust_engine=trust, circuit_breaker=cb
        )
        assert probe._bus is bus
        assert probe._trust is trust
        assert probe._cb is cb

    def test_assemble_probe_analyzes_governance_events(self) -> None:
        """A started assembled probe detects anomalies from governance
        events (acceleration → trust penalty + breaker trip)."""
        probe = assemble_runtime_behavior_probe(window_size=6)
        trust = probe._trust
        bus = probe._bus
        cb = probe._cb
        trust.register_agent("agent-1")
        for d in [1000, 1000, 1000, 100, 100, 100]:
            _bus_log(bus, "state_transition", "agent-1", "decide", d)
        assert cb is not None
        assert cb.state == BreakerState.OPEN
        assert probe.anomaly_counts().get("agent-1", 0) >= 1


class TestSubscriptionNarrowing:
    def test_default_subscribes_governance_topics_not_wildcard(self) -> None:
        """The assembly default narrows subscription to governance topics
        instead of the all-events ``"*"`` wildcard."""
        bus = AuditBus()
        probe = assemble_runtime_behavior_probe(audit_bus=bus)
        # Probe subscribed to state_transition / audit, not "*".
        assert "*" not in probe.subscribed_topics
        assert "state_transition" in probe.subscribed_topics
        assert "audit" in probe.subscribed_topics
        # All subscribed topics are wired on the bus.
        for topic in probe.subscribed_topics:
            assert probe._on_event in bus._subscribers.get(topic, [])

    def test_unrelated_event_not_received(self) -> None:
        """Events outside the subscribed governance topics are not delivered."""
        bus = AuditBus()
        probe = assemble_runtime_behavior_probe(audit_bus=bus, window_size=2)
        bus.log(event_type="telemetry", actor="a1", action="ping")
        assert probe.anomaly_counts() == {}
        assert all(len(v) == 0 for v in probe._events.values())

    def test_state_transition_and_audit_received(self) -> None:
        bus = AuditBus()
        probe = assemble_runtime_behavior_probe(audit_bus=bus, window_size=2)
        for d in [1000, 100]:
            _bus_log(bus, "state_transition", "agent-1", "decide", d)
        for d in [1000, 100]:
            _bus_log(bus, "audit", "agent-1", "decide", d)
        assert "agent-1" in probe._events or "agent-1" in probe.anomaly_counts()


class TestSidecarAssembly:
    def test_sidecar_app_wires_behavior_probe(self) -> None:
        """create_app assembles a started behavior probe on app.state."""
        from fastapi.testclient import TestClient

        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.server import create_app

        adapter = MockAgentAdapter(num_agents=1)
        app = create_app(
            ObservationCollector(adapter), CompositeMonitor(),
            allow_unauthenticated=True,
        )
        probe = app.state.behavior_probe
        from maref.agent.behavior_analyzer import RuntimeBehaviorProbe

        assert isinstance(probe, RuntimeBehaviorProbe)
        assert probe.started is True
