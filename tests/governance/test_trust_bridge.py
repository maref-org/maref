"""
GovernanceBridge 测试

覆盖审计问题 P11：governance ↔ recursive 桥接。
"""

from __future__ import annotations

import pytest

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.trust_bridge import (
    GovernanceBridge,
    GovernanceQuery,
    RecursiveEvent,
    RecursiveEventType,
)
from maref.governance.types import GovernanceState


class TestGovernanceBridge:
    def test_query_governance_state(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        query = bridge.query_governance_state()
        assert isinstance(query, GovernanceQuery)
        assert query.current_state == GovernanceState.INIT
        assert query.current_entropy == 0
        assert query.is_terminal is False

    def test_is_transition_allowed(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        assert bridge.is_transition_allowed(GovernanceState.OBSERVE) is True
        assert bridge.is_transition_allowed(GovernanceState.HALT) is False

    def test_notify_governance_safety_violation(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        bridge = GovernanceBridge(sm)

        event = RecursiveEvent(
            event_type=RecursiveEventType.SAFETY_VIOLATION,
            source_agent="agent-1",
            payload={"violation": "trust_threshold_exceeded"},
        )
        result = bridge.notify_governance(event)
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE

    def test_notify_governance_circuit_tripped(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.ANALYZE, "analyze")
        bridge = GovernanceBridge(sm)

        event = RecursiveEvent(
            event_type=RecursiveEventType.CIRCUIT_TRIPPED,
            source_agent="agent-2",
            payload={"circuit": "meta_governance"},
        )
        result = bridge.notify_governance(event)
        assert result is True
        assert sm.current_state == GovernanceState.HALT

    def test_notify_governance_disabled(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        bridge.disable()

        event = RecursiveEvent(
            event_type=RecursiveEventType.SAFETY_VIOLATION,
            source_agent="agent-1",
        )
        result = bridge.notify_governance(event)
        assert result is False

    def test_register_recursive_hook(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        called = []

        def hook(transition):
            called.append(transition)

        bridge.register_recursive_hook(hook)
        sm.transition(GovernanceState.OBSERVE, "test")
        assert len(called) == 1
        assert called[0].to_state == GovernanceState.OBSERVE

    def test_remove_recursive_hook(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        called = []

        def hook(transition):
            called.append(transition)

        bridge.register_recursive_hook(hook)
        bridge.remove_recursive_hook(hook)
        sm.transition(GovernanceState.OBSERVE, "test")
        assert len(called) == 0

    def test_get_recent_events(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)

        for i in range(5):
            event = RecursiveEvent(
                event_type=RecursiveEventType.AGENT_REGISTERED,
                source_agent=f"agent-{i}",
            )
            bridge.notify_governance(event)

        events = bridge.get_recent_events(limit=3)
        assert len(events) == 3
        assert events[0].source_agent == "agent-2"

    def test_get_recent_events_by_type(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)

        bridge.notify_governance(
            RecursiveEvent(
                event_type=RecursiveEventType.AGENT_REGISTERED,
                source_agent="agent-1",
            )
        )
        bridge.notify_governance(
            RecursiveEvent(
                event_type=RecursiveEventType.SAFETY_VIOLATION,
                source_agent="agent-2",
            )
        )

        events = bridge.get_recent_events(
            event_type=RecursiveEventType.SAFETY_VIOLATION
        )
        assert len(events) == 1
        assert events[0].source_agent == "agent-2"

    def test_event_count(self) -> None:
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(sm)
        assert bridge.event_count == 0

        bridge.notify_governance(
            RecursiveEvent(
                event_type=RecursiveEventType.AGENT_REGISTERED,
                source_agent="agent-1",
            )
        )
        assert bridge.event_count == 1
