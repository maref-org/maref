"""一致性 DSL 模块单元测试.

覆盖 consistency_dsl.py 的 ConsistencyLevel、ConsistencyCost、CostEstimator、DynamicDegrader。
"""
from __future__ import annotations

import pytest

from maref.consensus.consistency_dsl import (
    ConsistencyCost,
    ConsistencyLevel,
    CostEstimator,
    DynamicDegrader,
)


class TestConsistencyLevel:
    def test_enum_values(self) -> None:
        assert ConsistencyLevel.STRICT.value == "strict"
        assert ConsistencyLevel.CAUSAL.value == "causal"
        assert ConsistencyLevel.EVENTUAL.value == "eventual"


class TestConsistencyCost:
    def test_to_dict(self) -> None:
        cc = ConsistencyCost(
            level=ConsistencyLevel.STRICT,
            latency_ms=200.0,
            communication_multiplier=2.0,
            description="test",
        )
        d = cc.to_dict()
        assert d["level"] == "strict"
        assert d["latency_ms"] == 200.0
        assert d["communication_multiplier"] == 2.0
        assert d["description"] == "test"


class TestCostEstimator:
    def test_estimate_strict(self) -> None:
        cc = CostEstimator.estimate(ConsistencyLevel.STRICT)
        assert cc.level == ConsistencyLevel.STRICT
        assert cc.latency_ms > CostEstimator.BASELINE_LATENCY_MS

    def test_estimate_eventual(self) -> None:
        cc = CostEstimator.estimate(ConsistencyLevel.EVENTUAL)
        assert cc.latency_ms == CostEstimator.BASELINE_LATENCY_MS

    def test_compare(self) -> None:
        result = CostEstimator.compare(ConsistencyLevel.STRICT, ConsistencyLevel.EVENTUAL)
        assert result["from"] == "strict"
        assert result["to"] == "eventual"
        assert result["latency_delta_ms"] < 0
        assert result["comm_ratio"] < 1.0


class TestDynamicDegrader:
    def test_critical_path_unchanged(self) -> None:
        dd = DynamicDegrader()
        effective = dd.resolve("step1", ConsistencyLevel.STRICT, 0.9, is_critical=True)
        assert effective == ConsistencyLevel.STRICT

    def test_below_threshold_no_degrade(self) -> None:
        dd = DynamicDegrader()
        effective = dd.resolve("step1", ConsistencyLevel.STRICT, 0.5, is_critical=False)
        assert effective == ConsistencyLevel.STRICT

    def test_degrade_strict_to_causal(self) -> None:
        dd = DynamicDegrader()
        effective = dd.resolve("step1", ConsistencyLevel.STRICT, 0.9, is_critical=False)
        assert effective == ConsistencyLevel.CAUSAL

    def test_degrade_causal_to_eventual(self) -> None:
        dd = DynamicDegrader()
        effective = dd.resolve("step1", ConsistencyLevel.CAUSAL, 0.9, is_critical=False)
        assert effective == ConsistencyLevel.EVENTUAL

    def test_eventual_stays_eventual(self) -> None:
        dd = DynamicDegrader()
        effective = dd.resolve("step1", ConsistencyLevel.EVENTUAL, 0.9, is_critical=False)
        assert effective == ConsistencyLevel.EVENTUAL

    def test_explain_structure(self) -> None:
        dd = DynamicDegrader()
        exp = dd.explain("step1", ConsistencyLevel.STRICT, 0.9, is_critical=False)
        assert exp["step_id"] == "step1"
        assert exp["requested"] == "strict"
        assert exp["effective"] == "causal"
        assert exp["reason"] == "degraded due to high load"

    def test_explain_no_degrade(self) -> None:
        dd = DynamicDegrader()
        exp = dd.explain("step1", ConsistencyLevel.STRICT, 0.5, is_critical=False)
        assert exp["reason"] == "load below threshold"
        assert exp["effective"] == "strict"
