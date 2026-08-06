"""Tests for PERCV governance hooks — event-driven state transitions."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.governance.percv_hooks import (
    PERCVEventType,
    PERCVGovernanceHook,
    handle_percv_event,
)
from maref.governance.types import GovernanceState


class TestPERCVEventType:
    def test_event_types_defined(self):
        assert PERCVEventType.RESEARCH_START.value == "research_start"
        assert PERCVEventType.RESEARCH_COMPLETE.value == "research_complete"
        assert PERCVEventType.RESEARCH_FAIL.value == "research_fail"
        assert PERCVEventType.BUDGET_WARNING.value == "budget_warning"
        assert PERCVEventType.BUDGET_CRITICAL.value == "budget_critical"
        assert PERCVEventType.CARD_SYNC.value == "card_sync"
        assert PERCVEventType.VERIFICATION_FAIL.value == "verification_fail"


class TestPERCVGovernanceHook:
    def test_hook_created_with_state_machine(self):
        sm = MagicMock()
        hook = PERCVGovernanceHook(state_machine=sm)
        assert hook.state_machine is sm
        assert hook.event_count == 0

    def test_handle_research_start(self):
        sm = MagicMock()
        sm.can_transition.return_value = True
        hook = PERCVGovernanceHook(state_machine=sm)

        result = hook.handle_event(PERCVEventType.RESEARCH_START, {"topic": "test"})
        assert result["handled"] is True
        assert result["event_type"] == "research_start"
        sm.transition.assert_called_with(GovernanceState.ANALYZE, "research_start:test")
        assert hook.event_count == 1

    def test_handle_research_fail(self):
        sm = MagicMock()
        hook = PERCVGovernanceHook(state_machine=sm)

        result = hook.handle_event(PERCVEventType.RESEARCH_FAIL, {"error": "timeout"})
        assert result["handled"] is True
        sm.force_halt.assert_called_with("research_fail:timeout")

    def test_handle_budget_critical_with_circuit_breaker(self):
        sm = MagicMock()
        cb = MagicMock()
        hook = PERCVGovernanceHook(state_machine=sm, circuit_breaker=cb)

        result = hook.handle_event(PERCVEventType.BUDGET_CRITICAL, {"pct_used": 96.0})
        assert result["handled"] is True
        cb.trip.assert_called_once()

    def test_handler_registration_and_dispatch(self):
        sm = MagicMock()
        hook = PERCVGovernanceHook(state_machine=sm)

        handler = MagicMock(return_value={"handled": True})
        hook.register_handler(PERCVEventType.CARD_SYNC, handler)

        result = hook.handle_event(PERCVEventType.CARD_SYNC, {"count": 5})
        handler.assert_called_once()
        assert result["handled"] is True

    def test_unregistered_event(self):
        sm = MagicMock()
        hook = PERCVGovernanceHook(state_machine=sm)

        result = hook.handle_event(PERCVEventType.CARD_SYNC, {"count": 5})
        assert result["handled"] is True

    def test_handle_event_standalone_function(self):
        sm = MagicMock()
        result = handle_percv_event(sm, PERCVEventType.RESEARCH_START, {"topic": "test"})
        assert result["handled"] is True
