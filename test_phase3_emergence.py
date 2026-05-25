#!/usr/bin/env python3
"""Phase 3.2 emergence test suite."""

from __future__ import annotations

from maref.stress.emergence_harness import EmergenceTestHarness
from maref.stress.chaos_engine import ChaosEngine, FaultType


def test_temporal_perturbation_consistency():
    harness = EmergenceTestHarness(seed=42)

    def run_fn(order):
        # Deterministic aggregation regardless of order
        return {"sum": sum(1 for _ in order), "agents": sorted(order)}

    report = harness.temporal_perturbation(
        scenario_name="deterministic_sum",
        agents=["A", "B", "C"],
        run_fn=run_fn,
        runs=20,
    )
    assert report.consistency_rate == 1.0
    print("  temporal_perturbation_consistency OK")


def test_temporal_perturbation_detects_nondeterminism():
    harness = EmergenceTestHarness(seed=42)

    def run_fn(order):
        # First agent wins → order-dependent
        return {"leader": order[0]}

    report = harness.temporal_perturbation(
        scenario_name="first_wins",
        agents=["A", "B", "C"],
        run_fn=run_fn,
        runs=20,
    )
    # With 3 agents shuffled randomly, consistency rate should be < 1.0
    assert report.inconsistent_runs > 0
    print("  temporal_perturbation_detects_nondeterminism OK")


def test_shared_state_conflict_detection():
    outputs = {
        "agent_A": {"timeout": 30, "retries": 3},
        "agent_B": {"timeout": 60, "retries": 3},
    }
    conflicts = EmergenceTestHarness.detect_shared_state_conflict(
        outputs, shared_keys=["timeout", "retries"]
    )
    assert len(conflicts) == 1
    assert conflicts[0]["key"] == "timeout"
    assert set(conflicts[0]["agents"]) == {"agent_A", "agent_B"}
    print("  shared_state_conflict_detection OK")


def test_chaos_byzantine_fault_type():
    engine = ChaosEngine(simulate=True)
    ev = engine.inject(
        FaultType.BYZANTINE,
        params={"agent_id": "agent_X", "tamper_rate": 0.3},
    )
    assert ev.fault_type == FaultType.BYZANTINE
    assert "agent_X" in ev.detail
    print("  chaos_byzantine_fault_type OK")


def test_chaos_emergent_conflict_fault_type():
    engine = ChaosEngine(simulate=True)
    ev = engine.inject(
        FaultType.EMERGENT_CONFLICT,
        params={"conflict_type": "shared_config"},
    )
    assert ev.fault_type == FaultType.EMERGENT_CONFLICT
    assert "shared_config" in ev.detail
    print("  chaos_emergent_conflict_fault_type OK")


if __name__ == "__main__":
    test_temporal_perturbation_consistency()
    test_temporal_perturbation_detects_nondeterminism()
    test_shared_state_conflict_detection()
    test_chaos_byzantine_fault_type()
    test_chaos_emergent_conflict_fault_type()
    print("All Phase 3 emergence tests passed")
