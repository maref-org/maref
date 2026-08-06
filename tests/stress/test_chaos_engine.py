from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

from maref.stress.chaos_engine import (
    ChaosEngine,
    ChaosPlan,
    FaultEvent,
    FaultSchedule,
    FaultType,
    SafetyGate,
)


class TestFaultType:
    def test_enum_values(self):
        assert FaultType.NETWORK.value == "network"
        assert FaultType.PROCESS.value == "process"
        assert FaultType.DISK.value == "disk"
        assert FaultType.MEMORY.value == "memory"
        assert FaultType.CPU.value == "cpu"
        assert FaultType.BYZANTINE.value == "byzantine"
        assert FaultType.EMERGENT_CONFLICT.value == "emergent_conflict"


class TestFaultSchedule:
    def test_defaults(self):
        s = FaultSchedule(fault_type=FaultType.CPU, inject_at=1.0)
        assert s.duration_s == 10.0
        assert s.params == {}
        assert s.injected is False
        assert s.recovered is False
        assert s.error == ""

    def test_with_params(self):
        s = FaultSchedule(FaultType.NETWORK, 1.0, params={"latency_ms": 200})
        assert s.params["latency_ms"] == 200


class TestFaultEvent:
    def test_to_dict(self):
        e = FaultEvent(
            fault_type=FaultType.CPU,
            action="inject",
            timestamp=100.0,
            success=True,
            detail="ok",
            params={"load_pct": 80},
        )
        d = e.to_dict()
        assert d["fault_type"] == "cpu"
        assert d["action"] == "inject"
        assert d["timestamp"] == 100.0
        assert d["success"] is True
        assert d["detail"] == "ok"
        assert d["params"] == {"load_pct": 80}

    def test_to_dict_default_params_empty(self):
        e = FaultEvent(FaultType.CPU, "inject", 1.0, True)
        d = e.to_dict()
        assert d["params"] == {}


class TestChaosPlan:
    def test_to_dict_empty(self):
        p = ChaosPlan()
        d = p.to_dict()
        assert d["schedule_count"] == 0
        assert d["event_count"] == 0
        assert d["dry_run"] is False
        assert d["events"] == []

    def test_to_dict_with_schedule_and_events(self):
        e = FaultEvent(FaultType.CPU, "skip", 1.0, True)
        p = ChaosPlan(dry_run=True, events=[e])
        d = p.to_dict()
        assert d["dry_run"] is True
        assert len(d["events"]) == 1
        assert d["event_count"] == 1


class TestSafetyGate:
    def test_is_production_false_when_unset(self):
        assert SafetyGate.is_production() is False

    def test_is_production_false_for_empty(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: ""}):
            assert SafetyGate.is_production() is False

    def test_is_production_false_for_random(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: "false"}):
            assert SafetyGate.is_production() is False

    def test_is_production_true_for_1(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: "1"}):
            assert SafetyGate.is_production() is True

    def test_is_production_true_for_true(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: "true"}):
            assert SafetyGate.is_production() is True

    def test_is_production_true_for_yes(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: "yes"}):
            assert SafetyGate.is_production() is True

    def test_block_if_production_raises(self):
        with patch.dict(os.environ, {SafetyGate.PRODUCTION_ENV_VAR: "1"}):
            with pytest.raises(RuntimeError, match="ChaosEngine blocked"):
                SafetyGate.block_if_production()

    def test_block_if_production_not_set_no_error(self):
        SafetyGate.block_if_production()


class TestChaosEngine:
    def test_init(self):
        engine = ChaosEngine(simulate=True)
        assert engine.events == []
        assert engine.active_schedules == []

    def test_inject_network(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.NETWORK, duration_s=0.001, params={"latency_ms": 100})
        assert event.fault_type == FaultType.NETWORK
        assert event.action == "inject"
        assert event.success is True
        assert "+100ms" in event.detail
        assert len(engine.events) == 1

    def test_inject_cpu(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.CPU, duration_s=0.001, params={"load_pct": 90})
        assert event.success is True
        assert "CPU" in event.detail

    def test_inject_memory(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.MEMORY, duration_s=0.001, params={"pressure_mb": 500})
        assert event.success is True

    def test_inject_disk(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.DISK, duration_s=0.001, params={"space_mb": 50, "corrupt": True})
        assert event.success is True
        assert "corrupt" in event.detail

    def test_inject_process(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.PROCESS, duration_s=0.001, params={"target": "worker-1"})
        assert event.success is True
        assert "worker-1" in event.detail

    def test_inject_byzantine(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.BYZANTINE, duration_s=0.001, params={"agent_id": "a1"})
        assert event.success is True
        assert "byzantine" in event.detail.lower()

    def test_inject_emergent_conflict(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.EMERGENT_CONFLICT, duration_s=0.001,
                              params={"conflict_type": "shared_state"})
        assert event.success is True

    def test_inject_no_params(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.CPU, duration_s=0.001)
        assert event.success is True

    def test_inject_zero_duration_no_timer(self):
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.CPU, duration_s=0.0)
        assert event.success is True
        assert len(engine._timers) == 0

    def test_schedule_fault(self):
        engine = ChaosEngine(simulate=True)
        sched = engine.schedule(FaultType.CPU, delay_s=0.001, duration_s=0.001)
        assert sched.fault_type == FaultType.CPU
        assert sched.injected is False
        time.sleep(0.05)
        assert len(engine.events) >= 1

    def test_schedule_fault_with_params(self):
        engine = ChaosEngine(simulate=True)
        sched = engine.schedule(FaultType.NETWORK, delay_s=0.001, params={"latency_ms": 300})
        assert sched.params["latency_ms"] == 300

    def test_plan_only(self):
        engine = ChaosEngine(simulate=True)
        plan = engine.plan_only(FaultType.CPU, params={"load_pct": 50})
        assert isinstance(plan, ChaosPlan)
        assert plan.dry_run is True
        assert len(plan.events) == 1
        assert plan.events[0].action == "skip"
        assert plan.events[0].success is True

    def test_plan_only_no_params(self):
        engine = ChaosEngine(simulate=True)
        plan = engine.plan_only(FaultType.MEMORY)
        assert plan.dry_run is True

    def test_recover_specific_fault_type(self):
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.CPU, duration_s=2.0)
        engine.inject(FaultType.MEMORY, duration_s=2.0)
        events = engine.recover(FaultType.CPU)
        assert len(events) >= 1
        assert all(e.fault_type == FaultType.CPU for e in events)

    def test_recover_all(self):
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.CPU, duration_s=2.0)
        engine.inject(FaultType.MEMORY, duration_s=2.0)
        events = engine.recover()
        assert len(events) >= 1

    def test_active_schedules(self):
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.CPU, duration_s=0.0)
        engine.inject(FaultType.MEMORY, duration_s=2.0)
        active = engine.active_schedules
        cpu_actives = [s for s in active if s.fault_type == FaultType.CPU]
        mem_actives = [s for s in active if s.fault_type == FaultType.MEMORY]
        assert len(cpu_actives) == 1
        assert len(mem_actives) == 1

    def test_clear_cancels_timers(self):
        engine = ChaosEngine(simulate=True)
        engine.schedule(FaultType.CPU, delay_s=10.0, duration_s=10.0)
        engine.clear()
        assert len(engine._timers) == 0
        assert engine.active_schedules == []

    def test_events_property_returns_copy(self):
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.CPU, duration_s=0.001)
        evts = engine.events
        evts.clear()
        assert len(engine.events) == 1

    def test_inject_raises_in_production(self):
        engine = ChaosEngine(simulate=True)
        with patch.dict(os.environ, {"MAREF_PRODUCTION": "1"}):
            with pytest.raises(RuntimeError, match="ChaosEngine blocked"):
                engine.inject(FaultType.CPU)

    def test_plan_only_raises_in_production(self):
        engine = ChaosEngine(simulate=True)
        with patch.dict(os.environ, {"MAREF_PRODUCTION": "1"}):
            with pytest.raises(RuntimeError, match="ChaosEngine blocked"):
                engine.plan_only(FaultType.CPU)

    def test_recover_fault_sets_recovered(self):
        engine = ChaosEngine(simulate=True)
        s = FaultSchedule(FaultType.MEMORY, inject_at=time.time(), duration_s=0.001, params={})
        s.injected = True
        engine._schedules.append(s)
        event = engine._recover_fault(s)
        assert s.recovered is True
        assert event.action == "recover"
        assert event.success is True

    def test_execute_scheduled(self):
        engine = ChaosEngine(simulate=True)
        s = FaultSchedule(FaultType.CPU, inject_at=time.time(), duration_s=0.001, params={})
        engine._execute_scheduled(s)
        assert s.injected is True

    def test_recover_scheduled(self):
        engine = ChaosEngine(simulate=True)
        s = FaultSchedule(FaultType.CPU, inject_at=time.time(), duration_s=0.001, params={})
        s.injected = True
        engine._recover_scheduled(s)
        assert s.recovered is True
        assert len(engine.events) == 1
        assert engine.events[0].action == "recover"

    def test_recover_auto_after_timeout(self):
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.CPU, duration_s=0.001)
        time.sleep(0.1)
        ev = [e for e in engine.events if e.action == "recover"]
        assert len(ev) >= 1
        assert ev[0].detail == "Auto-recovery after timeout"
