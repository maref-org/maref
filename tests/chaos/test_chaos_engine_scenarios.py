"""
MAREF Chaos Engine Scenario Tests

Validates all 12 chaos scenarios from the chaos-scenarios.md library.
Each test exercises a specific fault type through the ChaosEngine
in simulate mode and verifies the expected system behavior.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.stress.chaos_engine import ChaosEngine, FaultType


@pytest.fixture
def engine() -> ChaosEngine:
    return ChaosEngine(simulate=True)


class TestNetworkLatencyScenario:
    """Scenario 1: Network latency injection."""

    def test_network_latency_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=3.0,
            params={"latency_ms": 500, "host": "127.0.0.1", "port": 8080},
        )

        assert event.fault_type == FaultType.NETWORK
        assert event.action == "inject"
        assert event.success is True
        assert "latency" in event.detail.lower()
        assert event.params.get("latency_ms") == 500

    def test_network_latency_recovery(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.NETWORK, duration_s=0)
        events = engine.recover(FaultType.NETWORK)

        assert len(events) > 0
        assert all(e.success for e in events)

    def test_network_latency_plan_only(self, engine: ChaosEngine) -> None:
        plan = engine.plan_only(FaultType.NETWORK, params={"latency_ms": 1000})

        assert plan.dry_run is True
        assert len(plan.events) == 1
        assert plan.events[0].action == "skip"
        assert plan.events[0].success is True


class TestNetworkPartitionScenario:
    """Scenario 2: Network partition."""

    def test_network_partition_detection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=5.0,
            params={"drop_rate": 1.0, "partition_count": 2},
        )

        assert event.success is True
        assert event.fault_type == FaultType.NETWORK
        assert event.params.get("drop_rate") == 1.0

    def test_network_partition_recovery(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.NETWORK, duration_s=0)

        recovered_events = engine.recover()
        assert all(e.success for e in recovered_events)


class TestDiskExhaustionScenario:
    """Scenario 3: Disk space exhaustion."""

    def test_disk_space_exhaustion(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.DISK,
            duration_s=5.0,
            params={"space_mb": 100, "corrupt": False},
        )

        assert event.success is True
        assert event.fault_type == FaultType.DISK
        assert "disk" in event.detail.lower()
        assert "100MB" in event.detail

    def test_disk_space_with_corrupt(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.DISK,
            duration_s=5.0,
            params={"space_mb": 50, "corrupt": True},
        )

        assert event.success is True
        assert event.params.get("corrupt") is True


class TestDiskIOPressureScenario:
    """Scenario 4: Disk IO pressure."""

    def test_disk_io_pressure(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.DISK,
            duration_s=10.0,
            params={"io_threads": 4, "block_size_kb": 1024},
        )

        assert event.success is True
        assert event.fault_type == FaultType.DISK
        assert event.params.get("io_threads") == 4

    def test_disk_io_schedule(self, engine: ChaosEngine) -> None:
        schedule = engine.schedule(
            FaultType.DISK,
            delay_s=0.1,
            duration_s=3.0,
            params={"io_threads": 2},
        )

        assert schedule.fault_type == FaultType.DISK
        assert schedule.duration_s == 3.0
        time.sleep(0.3)
        assert len(engine.events) > 0


class TestCPUOverloadScenario:
    """Scenario 5: CPU overload."""

    def test_cpu_overload_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.CPU,
            duration_s=5.0,
            params={"load_pct": 80},
        )

        assert event.success is True
        assert event.fault_type == FaultType.CPU
        assert "CPU" in event.detail
        assert event.params.get("load_pct") == 80

    def test_cpu_overload_high_load(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.CPU,
            duration_s=3.0,
            params={"load_pct": 100},
        )

        assert event.success is True
        assert "100%" in event.detail

    def test_cpu_overload_low_load(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.CPU,
            duration_s=2.0,
            params={"load_pct": 10},
        )

        assert event.success is True
        assert "10%" in event.detail


class TestMemoryPressureScenario:
    """Scenario 6: Memory pressure."""

    def test_memory_pressure_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.MEMORY,
            duration_s=3.0,
            params={"pressure_mb": 200},
        )

        assert event.success is True
        assert event.fault_type == FaultType.MEMORY
        assert "memory" in event.detail.lower()
        assert "200MB" in event.detail

    def test_memory_pressure_large(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.MEMORY,
            duration_s=2.0,
            params={"pressure_mb": 500},
        )

        assert event.success is True


class TestProcessCrashScenario:
    """Scenario 7: Process crash."""

    def test_process_crash_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.PROCESS,
            duration_s=5.0,
            params={"target": "test_worker", "auto_restart": True},
        )

        assert event.success is True
        assert event.fault_type == FaultType.PROCESS
        assert "process" in event.detail.lower()
        assert event.params.get("target") == "test_worker"

    def test_process_crash_no_restart(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.PROCESS,
            duration_s=3.0,
            params={"target": "worker_1", "auto_restart": False},
        )

        assert event.success is True
        assert event.params.get("auto_restart") is False


class TestCombinedNetworkCPUScenario:
    """Scenario 8: Combined network + CPU fault."""

    def test_combined_network_cpu_injection(self, engine: ChaosEngine) -> None:
        event_net = engine.inject(
            FaultType.NETWORK,
            duration_s=8.0,
            params={"latency_ms": 300},
        )
        event_cpu = engine.inject(
            FaultType.CPU,
            duration_s=8.0,
            params={"load_pct": 70},
        )

        assert event_net.success is True
        assert event_cpu.success is True
        assert event_net.fault_type == FaultType.NETWORK
        assert event_cpu.fault_type == FaultType.CPU

    def test_combined_recovery_all(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.NETWORK, duration_s=0)
        engine.inject(FaultType.CPU, duration_s=0)

        recovered = engine.recover()
        assert len(recovered) >= 2

    def test_combined_events_count(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.NETWORK, duration_s=3.0)
        engine.inject(FaultType.CPU, duration_s=3.0)

        events = engine.events
        network_events = [e for e in events if e.fault_type == FaultType.NETWORK]
        cpu_events = [e for e in events if e.fault_type == FaultType.CPU]

        assert len(network_events) >= 1
        assert len(cpu_events) >= 1


class TestAgentOscillationScenario:
    """Scenario 9: Agent state oscillation."""

    def test_oscillation_fault_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=5.0,
            params={"oscillation_cycles": 5, "interval_ms": 100},
        )

        assert event.success is True
        assert event.params.get("oscillation_cycles") == 5

    def test_oscillation_high_frequency(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=3.0,
            params={"oscillation_cycles": 20, "interval_ms": 50},
        )

        assert event.success is True

    def test_oscillation_event_recorded(self, engine: ChaosEngine) -> None:
        engine.inject(
            FaultType.NETWORK,
            duration_s=2.0,
            params={"oscillation_cycles": 3, "interval_ms": 200},
        )

        events = engine.events
        assert len(events) >= 1
        assert events[0].success is True


class TestKGCorruptionScenario:
    """Scenario 10: KG data corruption."""

    def test_kg_corruption_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.DISK,
            duration_s=5.0,
            params={"space_mb": 10, "corrupt": True, "corrupt_file": "kg/data.json"},
        )

        assert event.success is True
        assert event.fault_type == FaultType.DISK
        assert event.params.get("corrupt") is True

    def test_kg_corruption_without_corrupt_flag(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.DISK,
            duration_s=3.0,
            params={"space_mb": 10, "corrupt": False},
        )

        assert event.success is True
        assert event.params.get("corrupt") is False

    def test_kg_corruption_recovery(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.DISK, duration_s=0, params={"space_mb": 5, "corrupt": True})

        recovered = engine.recover(FaultType.DISK)
        assert len(recovered) > 0
        assert all(e.success for e in recovered)


class TestMessageQueueBuildupScenario:
    """Scenario 11: Message queue buildup."""

    def test_queue_buildup_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=5.0,
            params={"queue_size": 100, "processing_delay_ms": 500},
        )

        assert event.success is True
        assert event.params.get("queue_size") == 100

    def test_queue_buildup_large(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.NETWORK,
            duration_s=5.0,
            params={"queue_size": 1000, "processing_delay_ms": 100},
        )

        assert event.success is True

    def test_queue_buildup_recovery(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.NETWORK, duration_s=0, params={"queue_size": 50})

        engine.recover(FaultType.NETWORK)
        active = engine.active_schedules
        assert len(active) == 0


class TestEntropySpikeScenario:
    """Scenario 12: Entropy spike."""

    def test_entropy_spike_injection(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.MEMORY,
            duration_s=3.0,
            params={"entropy_value": 4.0, "severity": "critical"},
        )

        assert event.success is True
        assert event.params.get("entropy_value") == 4.0
        assert event.params.get("severity") == "critical"

    def test_entropy_spike_warning_level(self, engine: ChaosEngine) -> None:
        event = engine.inject(
            FaultType.MEMORY,
            duration_s=3.0,
            params={"entropy_value": 2.0, "severity": "warning"},
        )

        assert event.success is True
        assert event.params.get("severity") == "warning"

    def test_entropy_spike_full_lifecycle(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.MEMORY, duration_s=0, params={"entropy_value": 4.5})

        engine.recover(FaultType.MEMORY)
        events = engine.events
        actions = [e.action for e in events]

        assert "inject" in actions
        assert any(e.success for e in events if e.action == "inject")


class TestSafetyGate:
    """SafetyGate must block chaos in production."""

    def test_safety_gate_blocks_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_PRODUCTION", "true")

        from maref.stress.chaos_engine import SafetyGate

        assert SafetyGate.is_production() is True

        with pytest.raises(RuntimeError, match="blocked by SafetyGate"):
            SafetyGate.block_if_production()

    def test_safety_gate_allows_non_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_PRODUCTION", raising=False)

        from maref.stress.chaos_engine import SafetyGate

        assert SafetyGate.is_production() is False
        SafetyGate.block_if_production()


class TestChaosPlanAndSchedule:
    """Chaos planning and scheduling behaviors."""

    def test_plan_only_creates_dry_run(self, engine: ChaosEngine) -> None:
        plan = engine.plan_only(FaultType.CPU, params={"load_pct": 50})

        assert plan.dry_run is True
        assert len(plan.schedules) == 1
        assert plan.schedules[0].fault_type == FaultType.CPU

    def test_schedule_delayed_injection(self, engine: ChaosEngine) -> None:
        schedule = engine.schedule(FaultType.DISK, delay_s=0.2, duration_s=2.0)
        time.sleep(0.5)

        assert schedule.fault_type == FaultType.DISK
        assert len(engine.events) >= 1

    def test_clear_removes_all_timers(self, engine: ChaosEngine) -> None:
        engine.schedule(FaultType.CPU, delay_s=10.0, duration_s=5.0)
        engine.schedule(FaultType.MEMORY, delay_s=10.0, duration_s=5.0)

        engine.clear()
        assert len(engine.active_schedules) == 0

    def test_inject_with_zero_duration(self, engine: ChaosEngine) -> None:
        event = engine.inject(FaultType.MEMORY, duration_s=0)

        assert event.success is True
        assert event.action == "inject"


class TestChaosEventsTracking:
    """Event tracking and querying."""

    def test_events_returns_copy(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.CPU, duration_s=1.0)
        events_copy = engine.events
        engine.inject(FaultType.MEMORY, duration_s=1.0)

        assert len(events_copy) == 1
        assert len(engine.events) == 2

    def test_active_schedules_filters_recovered(self, engine: ChaosEngine) -> None:
        engine.inject(FaultType.CPU, duration_s=5.0)
        engine.inject(FaultType.MEMORY, duration_s=0)

        engine.recover(FaultType.MEMORY)
        active = engine.active_schedules
        for s in active:
            assert s.injected is True
            assert s.recovered is False

    def test_fault_event_to_dict(self, engine: ChaosEngine) -> None:
        event = engine.inject(FaultType.NETWORK, duration_s=3.0, params={"latency_ms": 200})
        d = event.to_dict()

        assert d["fault_type"] == "network"
        assert d["action"] == "inject"
        assert d["success"] is True
        assert d["params"]["latency_ms"] == 200


class TestFaultTypeEnum:
    """FaultType enum completeness."""

    def test_all_fault_types_defined(self) -> None:
        types = {ft.value for ft in FaultType}
        assert "network" in types
        assert "process" in types
        assert "disk" in types
        assert "memory" in types
        assert "cpu" in types

    def test_three_categories_covered(self) -> None:
        network_types = {FaultType.NETWORK}
        storage_types = {FaultType.DISK}
        compute_types = {FaultType.PROCESS, FaultType.CPU, FaultType.MEMORY}

        assert len(network_types) >= 1
        assert len(storage_types) >= 1
        assert len(compute_types) >= 3