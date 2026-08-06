"""Tests for C32: Life State Registry."""

from __future__ import annotations

import pytest

from maref.life_state.metadata import (
    LifeStateCapability,
    LifeStateMetadata,
    LifeStateType,
)
from maref.life_state.registry import (
    DuplicateRegistrationError,
    LifeStateRegistry,
    NotRegisteredError,
    RegistryEvent,
)


class TestLifeStateRegistry:
    def test_register_and_get(self):
        reg = LifeStateRegistry()
        meta = LifeStateMetadata(state_id="s1", state_type=LifeStateType.AGENT)
        reg.register(meta)
        assert reg.has("s1")
        assert reg.get("s1") is meta
        assert reg.count() == 1

    def test_duplicate_registration_raises(self):
        reg = LifeStateRegistry()
        meta = LifeStateMetadata(state_id="s1")
        reg.register(meta)
        with pytest.raises(DuplicateRegistrationError):
            reg.register(meta)

    def test_unregister(self):
        reg = LifeStateRegistry()
        meta = LifeStateMetadata(state_id="s1")
        reg.register(meta)
        removed = reg.unregister("s1")
        assert removed.state_id == "s1"
        assert not reg.has("s1")
        assert reg.count() == 0

    def test_unregister_not_registered_raises(self):
        reg = LifeStateRegistry()
        with pytest.raises(NotRegisteredError):
            reg.unregister("missing")

    def test_list_all(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="s1"))
        reg.register(LifeStateMetadata(state_id="s2"))
        assert len(reg.list_all()) == 2

    def test_find_by_type(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="a1", state_type=LifeStateType.AGENT))
        reg.register(LifeStateMetadata(state_id="s1", state_type=LifeStateType.SERVICE))
        agents = reg.find_by_type(LifeStateType.AGENT)
        assert len(agents) == 1
        assert agents[0].state_id == "a1"

    def test_find_by_capability(self):
        reg = LifeStateRegistry()
        m1 = LifeStateMetadata(state_id="s1")
        m1.add_capability(LifeStateCapability.COMPUTE)
        m2 = LifeStateMetadata(state_id="s2")
        reg.register(m1)
        reg.register(m2)
        result = reg.find_by_capability(LifeStateCapability.COMPUTE)
        assert len(result) == 1
        assert result[0].state_id == "s1"

    def test_find_by_label(self):
        reg = LifeStateRegistry()
        m = LifeStateMetadata(state_id="s1", labels={"env": "prod"})
        reg.register(m)
        result = reg.find_by_label("env", "prod")
        assert len(result) == 1
        assert result[0].state_id == "s1"

    def test_find_healthy_and_unhealthy(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="h1", health_score=90.0))
        reg.register(LifeStateMetadata(state_id="h2", health_score=40.0))
        healthy = reg.find_healthy(threshold=80.0)
        unhealthy = reg.find_unhealthy(threshold=50.0)
        assert len(healthy) == 1
        assert healthy[0].state_id == "h1"
        assert len(unhealthy) == 1
        assert unhealthy[0].state_id == "h2"

    def test_update_metadata(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="s1", version="0.1.0"))
        reg.update_metadata("s1", version="0.2.0")
        assert reg.get("s1").version == "0.2.0"

    def test_update_not_registered_raises(self):
        reg = LifeStateRegistry()
        with pytest.raises(NotRegisteredError):
            reg.update_metadata("missing", version="0.2.0")

    def test_subscribe_and_event_emission(self):
        reg = LifeStateRegistry()
        events: list[RegistryEvent] = []
        reg.subscribe(lambda e: events.append(e))
        reg.register(LifeStateMetadata(state_id="s1"))
        assert len(events) == 1
        assert events[0].event_type == "registered"
        assert events[0].state_id == "s1"

    def test_unsubscribe(self):
        reg = LifeStateRegistry()
        events: list[RegistryEvent] = []
        handler = lambda e: events.append(e)
        reg.subscribe(handler)
        reg.unsubscribe(handler)
        reg.register(LifeStateMetadata(state_id="s1"))
        assert len(events) == 0

    def test_event_log(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="s1"))
        reg.unregister("s1")
        log = reg.get_event_log()
        assert len(log) == 2
        assert log[0].event_type == "registered"
        assert log[1].event_type == "unregistered"

    def test_clear(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="s1"))
        reg.clear()
        assert reg.count() == 0
        assert len(reg.get_event_log()) == 0

    def test_to_dict(self):
        reg = LifeStateRegistry()
        reg.register(LifeStateMetadata(state_id="s1"))
        d = reg.to_dict()
        assert d["count"] == 1
        assert d["event_count"] == 1
        assert len(d["entities"]) == 1

    def test_subscriber_exception_isolated(self):
        reg = LifeStateRegistry()
        reg.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        reg.subscribe(lambda e: events.append(e))
        events: list[RegistryEvent] = []
        reg.register(LifeStateMetadata(state_id="s1"))
        assert len(events) == 1
