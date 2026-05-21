"""Tests for C38: Life State Lifecycle Management."""

from __future__ import annotations

import pytest

from maref.life_state.health import HealthStatus
from maref.life_state.lifecycle import LifeCycleManager, LifecyclePhase
from maref.life_state.metadata import LifeStateMetadata
from maref.life_state.state_machine import LifeState


class TestLifeCycleManager:
    def test_register_entity(self):
        mgr = LifeCycleManager()
        meta = LifeStateMetadata(state_id="s1")
        mgr.register_entity(meta)
        assert mgr.get_state("s1") == LifeState.BIRTH
        assert mgr._registry.has("s1")

    def test_activate(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        assert mgr.get_state("s1") == LifeState.ACTIVE

    def test_degrade(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        mgr.degrade("s1", reason="high_load")
        assert mgr.get_state("s1") == LifeState.DEGRADED

    def test_recover(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        mgr.degrade("s1")
        mgr.recover("s1")
        assert mgr.get_state("s1") == LifeState.ACTIVE

    def test_terminate(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        mgr.terminate("s1", reason="shutdown")
        assert mgr.get_state("s1") == LifeState.TERMINATED
        assert not mgr._registry.has("s1")

    def test_lifecycle_hooks(self):
        mgr = LifeCycleManager()
        hooks_called: list[str] = []
        mgr.add_hook(LifecyclePhase.BIRTH, lambda sid: hooks_called.append(f"birth:{sid}"))
        mgr.add_hook(LifecyclePhase.ACTIVATE, lambda sid: hooks_called.append(f"activate:{sid}"))
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        assert "birth:s1" in hooks_called
        assert "activate:s1" in hooks_called

    def test_hook_exception_isolated(self):
        mgr = LifeCycleManager()
        mgr.add_hook(LifecyclePhase.BIRTH, lambda sid: (_ for _ in ()).throw(RuntimeError("boom")))
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        assert mgr.get_state("s1") == LifeState.BIRTH

    def test_health_check_updates_metadata(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.health_check("s1", "latency_ms", 50.0)
        meta = mgr._registry.get("s1")
        assert meta.health_score == 100.0

    def test_health_critical_triggers_degrade(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        mgr.health_check("s1", "latency_ms", 500.0)
        assert mgr.get_state("s1") == LifeState.DEGRADED

    def test_health_warning_no_degrade(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        mgr.health_check("s1", "latency_ms", 50.0)
        mgr.health_check("s1", "latency_ms", 50.0)
        mgr.health_check("s1", "latency_ms", 150.0)
        assert mgr.get_state("s1") == LifeState.ACTIVE

    def test_get_machine(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        machine = mgr.get_machine("s1")
        assert machine is not None
        assert machine.current == LifeState.BIRTH

    def test_get_state_unknown(self):
        mgr = LifeCycleManager()
        assert mgr.get_state("unknown") is None

    def test_terminate_already_terminal(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.terminate("s1")
        mgr.terminate("s1")
        assert mgr.get_state("s1") == LifeState.TERMINATED

    def test_audit_log(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        mgr.activate("s1")
        log = mgr.get_audit_log()
        assert len(log) == 2
        assert log[0]["event"] == "registered"
        assert log[1]["event"] == "activated"

    def test_to_dict(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="s1"))
        d = mgr.to_dict()
        assert d["entity_count"] == 1
        assert d["state_machine_count"] == 1
        assert d["audit_count"] == 1
