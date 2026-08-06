#!/usr/bin/env python3
"""Phase 3.3 ConsistencyLevel DSL tests."""

from __future__ import annotations

from maref.consensus.consistency_dsl import (
    ConsistencyLevel,
    CostEstimator,
    DynamicDegrader,
)


def test_cost_estimator_values():
    strict = CostEstimator.estimate(ConsistencyLevel.STRICT)
    assert strict.latency_ms > 0
    assert strict.communication_multiplier >= 1.0
    print("  cost_estimator_values OK")


def test_compare_levels():
    cmp = CostEstimator.compare(ConsistencyLevel.STRICT, ConsistencyLevel.EVENTUAL)
    assert cmp["latency_delta_ms"] < 0  # eventual is faster
    assert cmp["comm_ratio"] < 1.0  # eventual uses less comm
    print("  compare_levels OK")


def test_dynamic_degrader_no_degradation():
    dd = DynamicDegrader(high_load_threshold=0.8)
    level = dd.resolve("s1", ConsistencyLevel.STRICT, current_load=0.5)
    assert level == ConsistencyLevel.STRICT
    print("  dynamic_degrader_no_degradation OK")


def test_dynamic_degrader_degrades_once():
    dd = DynamicDegrader(high_load_threshold=0.8)
    level = dd.resolve("s1", ConsistencyLevel.STRICT, current_load=0.9)
    assert level == ConsistencyLevel.CAUSAL
    print("  dynamic_degrader_degrades_once OK")


def test_dynamic_degrader_degrades_twice():
    dd = DynamicDegrader(high_load_threshold=0.8)
    level = dd.resolve("s1", ConsistencyLevel.CAUSAL, current_load=0.95)
    assert level == ConsistencyLevel.EVENTUAL
    print("  dynamic_degrader_degrades_twice OK")


def test_critical_path_immune():
    dd = DynamicDegrader(high_load_threshold=0.8)
    level = dd.resolve("s1", ConsistencyLevel.STRICT, current_load=0.95, is_critical=True)
    assert level == ConsistencyLevel.STRICT
    print("  critical_path_immune OK")


def test_explain_output():
    dd = DynamicDegrader(high_load_threshold=0.8)
    info = dd.explain("s1", ConsistencyLevel.STRICT, current_load=0.95)
    assert info["effective"] == "causal"
    assert "degraded due to high load" in info["reason"]
    print("  explain_output OK")


if __name__ == "__main__":
    test_cost_estimator_values()
    test_compare_levels()
    test_dynamic_degrader_no_degradation()
    test_dynamic_degrader_degrades_once()
    test_dynamic_degrader_degrades_twice()
    test_critical_path_immune()
    test_explain_output()
    print("All Phase 3 Consistency DSL tests passed")
