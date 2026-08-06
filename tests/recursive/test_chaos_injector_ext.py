"""Tests for chaos_injector.py — ChaosInjector, events, clearing."""
from __future__ import annotations

import pytest

from maref.recursive.chaos_injector import ChaosEvent, ChaosInjector, ChaosType


class TestChaosInjector:
    def test_initial_state(self):
        ci = ChaosInjector()
        assert ci.events == []

    def test_inject(self):
        ci = ChaosInjector()
        event = ci.inject(ChaosType.CB_OSCILLATION, target="inner_cb", params={"freq": 5})
        assert event.chaos_type == ChaosType.CB_OSCILLATION
        assert event.target == "inner_cb"
        assert event.injected is True
        assert len(ci.events) == 1

    def test_inject_default_params(self):
        ci = ChaosInjector()
        event = ci.inject(ChaosType.HALT_STORM)
        assert event.params == {}

    def test_events_of_type(self):
        ci = ChaosInjector()
        ci.inject(ChaosType.CB_OSCILLATION)
        ci.inject(ChaosType.HALT_STORM)
        ci.inject(ChaosType.CB_OSCILLATION)
        assert len(ci.events_of_type(ChaosType.CB_OSCILLATION)) == 2
        assert len(ci.events_of_type(ChaosType.AGENT_CRASH)) == 0

    def test_clear(self):
        ci = ChaosInjector()
        ci.inject(ChaosType.CB_OSCILLATION)
        ci.clear()
        assert ci.events == []

    def test_events_property_returns_copy(self):
        ci = ChaosInjector()
        ci.inject(ChaosType.CB_OSCILLATION)
        events_copy = ci.events
        events_copy.clear()
        assert len(ci.events) == 1
