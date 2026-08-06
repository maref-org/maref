from __future__ import annotations

import pytest

from maref.stress.emergence_harness import (
    EmergenceReport,
    EmergenceTestHarness,
    PerturbationResult,
)


class TestPerturbationResult:
    def test_fields(self):
        r = PerturbationResult(
            run_id=0,
            execution_order=["a", "b"],
            final_state={"x": 1},
            success=True,
            duration_ms=10.0,
        )
        assert r.run_id == 0
        assert r.execution_order == ["a", "b"]
        assert r.success is True


class TestEmergenceReport:
    def test_consistency_rate_zero_when_no_runs(self):
        r = EmergenceReport(
            scenario_name="test",
            run_count=0,
            consistent_runs=0,
            inconsistent_runs=0,
            p99_latency_ms=0.0,
        )
        assert r.consistency_rate == 0.0

    def test_consistency_rate_perfect(self):
        r = EmergenceReport(
            scenario_name="test",
            run_count=10,
            consistent_runs=10,
            inconsistent_runs=0,
            p99_latency_ms=5.0,
        )
        assert r.consistency_rate == 1.0

    def test_consistency_rate_partial(self):
        r = EmergenceReport(
            scenario_name="test",
            run_count=10,
            consistent_runs=4,
            inconsistent_runs=6,
            p99_latency_ms=5.0,
        )
        assert r.consistency_rate == 0.4

    def test_to_dict(self):
        r = EmergenceReport(
            scenario_name="scenario-x",
            run_count=5,
            consistent_runs=3,
            inconsistent_runs=2,
            p99_latency_ms=12.3,
        )
        d = r.to_dict()
        assert d["scenario"] == "scenario-x"
        assert d["runs"] == 5
        assert d["consistent"] == 3
        assert d["inconsistent"] == 2
        assert d["consistency_rate"] == 0.6
        assert d["p99_latency_ms"] == 12.3


class TestEmergenceTestHarness:
    def test_init_without_seed(self):
        h = EmergenceTestHarness()
        assert h is not None

    def test_init_with_seed(self):
        h = EmergenceTestHarness(seed=42)
        assert h is not None

    def test_temporal_perturbation_consistent_run_fn(self):
        def run_fn(order: list[str]) -> dict:
            return {"result": sum(ord(c) for c in order)}

        h = EmergenceTestHarness(seed=42)
        report = h.temporal_perturbation("test", ["a", "b", "c"], run_fn, runs=10)
        assert report.run_count == 10
        assert report.scenario_name == "test"
        assert report.consistent_runs == 10
        assert report.inconsistent_runs == 0
        assert report.consistency_rate == 1.0

    def test_temporal_perturbation_inconsistent_run_fn(self):
        def run_fn(order: list[str]) -> dict:
            return {"first": order[0]}

        h = EmergenceTestHarness(seed=42)
        report = h.temporal_perturbation("inconsistent", ["a", "b", "c"], run_fn, runs=20)
        assert report.inconsistent_runs > 0

    def test_temporal_perturbation_custom_comparator(self):
        def run_fn(order: list[str]) -> dict:
            return {"len": len(order)}

        def comparator(a: dict, b: dict) -> bool:
            return a["len"] == b["len"]

        h = EmergenceTestHarness(seed=42)
        report = h.temporal_perturbation("test", ["x", "y", "z"], run_fn,
                                         runs=5, state_comparator=comparator)
        assert report.consistent_runs == 5

    def test_temporal_perturbation_empty_agents(self):
        def run_fn(order: list[str]) -> dict:
            return {"empty": True}

        h = EmergenceTestHarness(seed=42)
        report = h.temporal_perturbation("empty", [], run_fn, runs=3)
        assert report.run_count == 3

    def test_detect_shared_state_conflict_no_conflicts(self):
        agent_outputs = {
            "agent_a": {"timeout": 30, "retries": 3},
            "agent_b": {"timeout": 30, "retries": 3},
        }
        conflicts = EmergenceTestHarness.detect_shared_state_conflict(agent_outputs, ["timeout", "retries"])
        assert conflicts == []

    def test_detect_shared_state_conflict_with_conflicts(self):
        agent_outputs = {
            "agent_a": {"timeout": 30, "retries": 3},
            "agent_b": {"timeout": 60, "retries": 3},
            "agent_c": {"timeout": 30, "retries": 5},
        }
        conflicts = EmergenceTestHarness.detect_shared_state_conflict(agent_outputs, ["timeout", "retries"])
        assert len(conflicts) == 2
        timeout_conflict = [c for c in conflicts if c["key"] == "timeout"][0]
        assert len(timeout_conflict["agents"]) == 2
        assert set(timeout_conflict["values"]) == {30, 60}

    def test_detect_shared_state_conflict_no_relevant_keys(self):
        agent_outputs = {
            "agent_a": {"timeout": 30},
            "agent_b": {"timeout": 30},
        }
        conflicts = EmergenceTestHarness.detect_shared_state_conflict(agent_outputs, ["other_key"])
        assert conflicts == []

    def test_detect_shared_state_conflict_empty_inputs(self):
        conflicts = EmergenceTestHarness.detect_shared_state_conflict({}, ["key"])
        assert conflicts == []

    def test_default_comparator_equal(self):
        assert EmergenceTestHarness._default_comparator({"a": 1}, {"a": 1}) is True

    def test_default_comparator_not_equal(self):
        assert EmergenceTestHarness._default_comparator({"a": 1}, {"a": 2}) is False
