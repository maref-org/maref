"""Tests for RuntimeBehaviorProbe (v0.44.0 S2 行为审计闭环反馈)."""

from __future__ import annotations

from typing import Any

import pytest

from maref.agent.behavior_analyzer import (
    RuntimeBehaviorProbe,
    audit_entry_to_agent_event,
)
from maref.governance.audit import AuditEntry
from maref.governance.audit_bus import AuditBus
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.recursive.trust_engine_v2 import TrustEngineV2


def _entry(
    event_type: str,
    actor: str,
    action: str,
    duration_ms: float = 0,
    details: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditEntry:
    md = dict(metadata or {})
    md["duration_ms"] = duration_ms
    return AuditEntry(
        id="id",
        timestamp=1000.0,
        event_type=event_type,
        actor=actor,
        action=action,
        details=details,
        metadata=md,
    )


class TestAuditEventAdapter:
    def test_maps_fields(self) -> None:
        entry = _entry(
            "agent_action.exec",
            "agent-1",
            "network.scan",
            duration_ms=250,
            metadata={
                "tools_used": ["nmap"],
                "confidence": 0.9,
                "tokens": 1200,
            },
        )
        event = audit_entry_to_agent_event(entry)
        assert event.agent_id == "agent-1"
        assert event.action == "network.scan"
        assert event.duration_ms == 250
        assert event.tools_used == ["nmap"]
        assert event.confidence == 0.9
        assert event.tokens_consumed == 1200
        assert event.status == "success"

    def test_status_inferred_from_details(self) -> None:
        assert audit_entry_to_agent_event(
            _entry("agent_action.exec", "a1", "x", details="retry #2")
        ).status == "retry"
        assert audit_entry_to_agent_event(
            _entry("agent_action.exec", "a1", "x", details="call failed")
        ).status == "failure"


class TestProbeLifecycle:
    def test_start_stop_subscription(self) -> None:
        bus = AuditBus()
        probe = RuntimeBehaviorProbe(bus, TrustEngineV2())
        assert probe.started is False
        probe.start()
        assert probe.started is True
        # 重复 start 幂等
        probe.start()
        assert bus._subscribers["*"].count(probe._on_event) == 1
        probe.stop()
        assert probe.started is False
        assert bus._subscribers["*"] == []
        # 重复 stop 幂等
        probe.stop()
        assert bus._subscribers["*"] == []

    def test_non_behavioral_events_ignored(self) -> None:
        bus = AuditBus()
        trust = TrustEngineV2()
        probe = RuntimeBehaviorProbe(bus, trust, window_size=2)
        probe.start()
        bus.log(event_type="governance_decision", actor="a1", action="allow")
        bus.log(event_type="compliance_decision", actor="a1", action="deny")
        assert probe.anomaly_counts() == {}
        assert all(len(v) == 0 for v in probe._events.values())


class TestProbeFeedbackLoop:
    def _probe(
        self,
        window_size: int = 6,
        with_cb: bool = False,
    ) -> tuple[RuntimeBehaviorProbe, AuditBus, TrustEngineV2, Any]:
        bus = AuditBus()
        trust = TrustEngineV2()
        cb = CircuitBreaker() if with_cb else None
        probe = RuntimeBehaviorProbe(bus, trust, circuit_breaker=cb, window_size=window_size)
        probe.start()
        return probe, bus, trust, cb

    def _feed_durations(
        self, bus: AuditBus, durations: list[float], actor: str = "agent-1"
    ) -> None:
        for d in durations:
            bus.log(
                event_type="agent_action.exec",
                actor=actor,
                action="decide",
                metadata={"duration_ms": d},
            )

    def test_acceleration_anomaly_reduces_trust(self) -> None:
        probe, bus, trust, _cb = self._probe(window_size=6)
        trust.register_agent("agent-1")
        # 前 3 个慢（1000ms），后 3 个快（100ms）→ 决策加速 >50% → critical
        self._feed_durations(bus, [1000, 1000, 1000, 100, 100, 100])
        profile = trust._profiles["agent-1"]
        assert profile.behavioral_consistency < 0.7 - 0.28  # 扣了 0.30
        assert probe.anomaly_counts().get("agent-1", 0) == 1

    def test_critical_anomaly_trips_breaker(self) -> None:
        probe, bus, trust, cb = self._probe(window_size=6, with_cb=True)
        trust.register_agent("agent-1")
        self._feed_durations(bus, [1000, 1000, 1000, 100, 100, 100])
        assert cb is not None
        assert cb.state == BreakerState.OPEN
        assert cb.get_stats()["last_trip"] == (
            "behavior_anomaly:acceleration:agent=agent-1"
        )

    def test_no_anomaly_no_trust_change(self) -> None:
        probe, bus, trust, _cb = self._probe(window_size=6)
        trust.register_agent("agent-1")
        # 稳定节奏：无加速
        self._feed_durations(bus, [500, 500, 500, 500, 500, 500])
        profile = trust._profiles["agent-1"]
        assert profile.behavioral_consistency == 0.7
        assert probe.anomaly_counts() == {}

    def test_anomaly_count_accumulates_across_windows(self) -> None:
        probe, bus, trust, _cb = self._probe(window_size=4)
        trust.register_agent("agent-1")
        # 每窗口 4 个事件触发一次检测
        self._feed_durations(bus, [1000, 1000, 100, 100])  # window 1 → anomaly
        self._feed_durations(bus, [1000, 1000, 100, 100])  # window 2 → anomaly
        assert probe.anomaly_counts().get("agent-1", 0) == 2

    def test_non_critical_anomaly_does_not_trip_breaker(self) -> None:
        probe, bus, trust, cb = self._probe(window_size=4, with_cb=True)
        trust.register_agent("agent-1")
        # medium 加速（35%）累计多次也不触发全局熔断，仅扣信任分
        self._feed_durations(bus, [1000, 1000, 650, 650])
        self._feed_durations(bus, [1000, 1000, 650, 650])
        self._feed_durations(bus, [1000, 1000, 650, 650])
        assert cb is not None
        assert cb.state == BreakerState.CLOSED
        assert probe.anomaly_counts().get("agent-1", 0) == 3
        profile = trust._profiles["agent-1"]
        assert profile.behavioral_consistency < 0.7

    def test_stop_halts_processing(self) -> None:
        probe, bus, trust, _cb = self._probe(window_size=4)
        trust.register_agent("agent-1")
        probe.stop()
        self._feed_durations(bus, [1000, 1000, 100, 100])
        assert probe.anomaly_counts() == {}

    def test_baseline_recorded(self) -> None:
        probe, bus, trust, _cb = self._probe(window_size=6)
        self._feed_durations(bus, [1000, 1000, 1000, 100, 100, 100])
        baselines = probe.baselines()
        assert "agent-1" in baselines
        assert baselines["agent-1"]["avg_duration_ms"] == pytest.approx(550.0, abs=1)
