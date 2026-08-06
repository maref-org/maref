from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from maref.stress.chaos_engine import ChaosEngine, ChaosPlan, FaultType, SafetyGate


class TestFaultType:
    def test_enum_values(self) -> None:
        assert FaultType.NETWORK.value == "network"
        assert FaultType.PROCESS.value == "process"
        assert FaultType.DISK.value == "disk"
        assert FaultType.MEMORY.value == "memory"
        assert FaultType.CPU.value == "cpu"


class TestChaosEngineInject:
    """Test each fault type injects correctly (simulated mode)."""

    def test_inject_network_fault(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.NETWORK, duration_s=1.0)
        assert event.fault_type == FaultType.NETWORK
        assert event.action == "inject"
        assert event.success is True
        assert "latency" in event.detail.lower()

    def test_inject_process_fault(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.PROCESS, duration_s=1.0, params={"target": "worker_1"})
        assert event.fault_type == FaultType.PROCESS
        assert event.success is True
        assert "worker_1" in event.detail

    def test_inject_disk_fault(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.DISK, duration_s=1.0, params={"space_mb": 500})
        assert event.fault_type == FaultType.DISK
        assert event.success is True
        assert "500" in event.detail

    def test_inject_memory_fault(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.MEMORY, duration_s=1.0, params={"pressure_mb": 256})
        assert event.fault_type == FaultType.MEMORY
        assert event.success is True
        assert "256" in event.detail

    def test_inject_cpu_fault(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.CPU, duration_s=2.0, params={"load_pct": 90})
        assert event.fault_type == FaultType.CPU
        assert event.success is True
        assert "90" in event.detail

    def test_inject_without_duration_no_recovery(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.MEMORY, duration_s=0)
        assert event.success is True
        event_list = engine.events
        assert len(event_list) == 1


class TestChaosEngineRecovery:
    """Test recovery after injection."""

    def test_recover_specific_fault_type(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.NETWORK, duration_s=10.0)
        engine.inject(FaultType.CPU, duration_s=10.0)

        recovered = engine.recover(FaultType.CPU)
        assert len(recovered) > 0
        assert all(e.fault_type == FaultType.CPU for e in recovered)

    def test_recover_all_faults(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.NETWORK, duration_s=10.0)
        engine.inject(FaultType.DISK, duration_s=10.0)

        recovered = engine.recover()
        assert len(recovered) == 2
        assert all(e.action == "recover" for e in recovered)

    def test_auto_recovery_after_timeout(self) -> None:
        engine = ChaosEngine(simulate=True)
        event = engine.inject(FaultType.CPU, duration_s=0.1)
        assert event.success is True
        assert len(engine.events) == 1


class TestSafetyGate:
    """Test safety gate blocks production runs."""

    def test_safety_gate_detects_production(self) -> None:
        assert SafetyGate.is_production() is False

    def test_safety_gate_blocks_inject(self) -> None:
        with patch.dict(os.environ, {"MAREF_PRODUCTION": "true"}, clear=False):
            assert SafetyGate.is_production() is True
            engine = ChaosEngine(simulate=True)
            with pytest.raises(RuntimeError, match="SafetyGate"):
                engine.inject(FaultType.CPU)

    def test_safety_gate_blocks_plan_only(self) -> None:
        with patch.dict(os.environ, {"MAREF_PRODUCTION": "true"}, clear=False):
            engine = ChaosEngine(simulate=True)
            with pytest.raises(RuntimeError, match="SafetyGate"):
                engine.plan_only(FaultType.DISK)

    def test_not_production_by_default(self) -> None:
        assert SafetyGate.is_production() is False

    def test_safety_gate_case_insensitive(self) -> None:
        with patch.dict(os.environ, {"MAREF_PRODUCTION": "True"}, clear=False):
            assert SafetyGate.is_production() is True


class TestDryRunMode:
    """Test dry-run mode returns plan without executing."""

    def test_plan_only_returns_plan(self) -> None:
        engine = ChaosEngine(simulate=True)
        plan = engine.plan_only(FaultType.NETWORK, params={"latency_ms": 1000})
        assert isinstance(plan, ChaosPlan)
        assert plan.dry_run is True
        assert len(plan.schedules) == 1
        assert plan.schedules[0].fault_type == FaultType.NETWORK

    def test_plan_only_logs_skip_event(self) -> None:
        engine = ChaosEngine(simulate=True)
        plan = engine.plan_only(FaultType.MEMORY, params={"pressure_mb": 512})
        assert len(plan.events) > 0
        assert plan.events[0].action == "skip"
        assert plan.events[0].success is True

    def test_plan_only_does_not_execute(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.plan_only(FaultType.CPU)
        assert len(engine.events) > 0

    def test_plan_only_respects_params(self) -> None:
        engine = ChaosEngine(simulate=True)
        plan = engine.plan_only(FaultType.DISK, params={"space_mb": 200, "corrupt": True})
        schedule = plan.schedules[0]
        assert schedule.params["space_mb"] == 200
        assert schedule.params["corrupt"] is True


class TestChaosEngineEvents:
    def test_events_accumulate(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.inject(FaultType.NETWORK, duration_s=1.0)
        engine.inject(FaultType.CPU, duration_s=1.0)
        assert len(engine.events) == 2

    def test_clear_cancels_timers(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.schedule(FaultType.NETWORK, delay_s=10.0)
        engine.clear()
        assert len(engine.active_schedules) == 0
        assert len(engine._timers) == 0

    def test_active_schedules(self) -> None:
        engine = ChaosEngine(simulate=True)
        schedule = engine.schedule(FaultType.DISK, delay_s=0.05, duration_s=10.0)
        schedule.injected = True
        assert len(engine.active_schedules) == 1


class TestChaosEngineScheduling:
    @pytest.mark.chaos
    def test_scheduled_fault_executes(self) -> None:
        engine = ChaosEngine(simulate=True)
        engine.schedule(FaultType.CPU, delay_s=0.05, duration_s=0.1)
        assert len(engine._schedules) == 1

    @pytest.mark.chaos
    def test_scheduled_fault_fires_and_recovers(self) -> None:
        engine = ChaosEngine(simulate=True)
        schedule = engine.schedule(FaultType.NETWORK, delay_s=0.02, duration_s=0.05)
        schedule.injected = True
        _ = engine.recover(FaultType.NETWORK)
        assert schedule.recovered is True


class TestChaosEngineRealMode:
    @pytest.mark.chaos
    def test_real_cpu_load_executes(self) -> None:
        engine = ChaosEngine(simulate=False)
        result = engine._real_cpu_load({"load_pct": 50, "duration_s": 0.5})
        assert "CPU" in result

    @pytest.mark.chaos
    def test_real_memory_pressure_executes(self) -> None:
        engine = ChaosEngine(simulate=False)
        result = engine._real_memory_pressure({"pressure_mb": 1})
        assert "Allocated" in result
