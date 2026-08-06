"""Tests for ValueMetric (v0.51 W2-S1 / B1).

Covers business value metric model with baseline/current/delta and per-task
attachment for ROI tracking.
"""

from __future__ import annotations

import pytest

from maref.value.metrics import ValueMetric, ValueMetricType


def test_metric_with_delta_positive() -> None:
    metric = ValueMetric(
        metric_type=ValueMetricType.HOURS_SAVED,
        baseline=100.0,
        current=140.0,
        unit="hours",
    )
    assert metric.delta == 40.0
    assert metric.delta_percent == 40.0


def test_metric_with_delta_negative() -> None:
    metric = ValueMetric(
        metric_type=ValueMetricType.ERROR_REDUCTION,
        baseline=0.30,
        current=0.12,
        unit="ratio",
    )
    assert round(metric.delta, 4) == -0.18
    assert round(metric.delta_percent, 2) == -60.0


def test_metric_delta_zero() -> None:
    metric = ValueMetric(metric_type=ValueMetricType.CYCLE_TIME, baseline=10.0, current=10.0)
    assert metric.delta == 0.0
    assert metric.delta_percent == 0.0


def test_metric_serialization() -> None:
    metric = ValueMetric(
        metric_type=ValueMetricType.ATTAINMENT_RATE,
        baseline=0.7,
        current=0.85,
        unit="ratio",
        label="support_ticket_attainment",
    )
    d = metric.to_dict()
    assert d["metric_type"] == "attainment_rate"
    assert d["baseline"] == 0.7
    assert d["current"] == 0.85
    assert d["delta"] == 0.15
    assert d["label"] == "support_ticket_attainment"


def test_metric_accepts_no_baseline() -> None:
    metric = ValueMetric(metric_type=ValueMetricType.HOURS_SAVED, current=12.0, unit="hours")
    assert metric.baseline is None
    assert metric.delta == 12.0


def test_delta_percent_with_zero_baseline() -> None:
    metric = ValueMetric(metric_type=ValueMetricType.HOURS_SAVED, baseline=0.0, current=5.0)
    assert metric.delta_percent is None


def test_invalid_baseline_after_current_raises() -> None:
    with pytest.raises(ValueError):
        # 没有理由 baseline > 0 时 current 无法算 delta；此处验证负数异常被拦截
        ValueMetric(metric_type=ValueMetricType.HOURS_SAVED, baseline=10.0, current=-1.0)


def test_metric_type_enum_values() -> None:
    assert ValueMetricType.HOURS_SAVED.value == "hours_saved"
    assert ValueMetricType.CYCLE_TIME.value == "cycle_time"
    assert ValueMetricType.ERROR_REDUCTION.value == "error_reduction"
    assert ValueMetricType.ATTAINMENT_RATE.value == "attainment_rate"
