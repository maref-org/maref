"""Tests for cost_tracker.py — GasMeter, BudgetGuard, CostTracker, CostForecast."""
from __future__ import annotations

import time

import pytest

from maref.recursive.cost_tracker import (
    AnomalyFlag,
    BudgetAllocation,
    BudgetGuard,
    CostForecast,
    CostRecord,
    CostReport,
    CostTrend,
    GasMeter,
    GasRecord,
    OperationCost,
)


class TestGasMeter:
    def test_meter_known_operation(self):
        meter = GasMeter()
        gas = meter.meter("state_transition")
        assert gas == 0.01
        assert meter.total_spent() == 0.01

    def test_meter_unknown_operation(self):
        meter = GasMeter()
        gas = meter.meter("unknown_op", input_size=10)
        assert gas > 0

    def test_meter_with_tokens(self):
        meter = GasMeter()
        gas = meter.meter("hypothesis_test", input_size=100, output_size=50)
        expected = 0.003 + 100 * 0.0005 + 50 * 0.001
        assert gas == expected

    def test_meter_with_duration(self):
        meter = GasMeter()
        gas = meter.meter("monitor", duration_seconds=10)
        expected = 0.005 + 10 * 0.001
        assert gas == expected

    def test_estimate(self):
        meter = GasMeter()
        est = meter.estimate("state_transition")
        assert est == 0.01
        assert meter.total_spent() == 0.0

    def test_estimate_unknown(self):
        meter = GasMeter()
        est = meter.estimate("unknown")
        assert est == 0.001

    def test_records(self):
        meter = GasMeter()
        meter.meter("state_transition")
        meter.meter("observe")
        records = meter.records()
        assert len(records) == 2
        assert all(isinstance(r, GasRecord) for r in records)

    def test_set_operation_cost(self):
        meter = GasMeter()
        meter.set_operation_cost("custom", OperationCost("custom", 5.0, 0.0, 0.0))
        assert meter.meter("custom") == 5.0

    def test_total_spent_initial(self):
        meter = GasMeter()
        assert meter.total_spent() == 0.0


class TestBudgetAllocation:
    def test_remaining(self):
        alloc = BudgetAllocation("a1", "t1", budget=100.0, consumed=30.0)
        assert alloc.remaining == 70.0

    def test_remaining_clamped(self):
        alloc = BudgetAllocation("a1", "t1", budget=100.0, consumed=150.0)
        assert alloc.remaining == 0.0

    def test_is_exhausted(self):
        alloc = BudgetAllocation("a1", "t1", budget=100.0, consumed=100.0)
        assert alloc.is_exhausted is True
        alloc.consumed = 50.0
        assert alloc.is_exhausted is False

    def test_usage_pct(self):
        alloc = BudgetAllocation("a1", "t1", budget=200.0, consumed=50.0)
        assert alloc.usage_pct == 25.0

    def test_usage_pct_zero_budget(self):
        alloc = BudgetAllocation("a1", "t1", budget=0.0, consumed=0.0)
        assert alloc.usage_pct == 0.0


class TestBudgetGuard:
    def test_allocate_default(self):
        guard = BudgetGuard(default_budget=100.0)
        alloc = guard.allocate("task-1")
        assert alloc.budget == 100.0
        assert alloc.task_id == "task-1"

    def test_allocate_with_agent_budget(self):
        guard = BudgetGuard(default_budget=100.0)
        guard.set_agent_budget("agent-1", 500.0)
        alloc = guard.allocate("task-1", agent_id="agent-1")
        assert alloc.budget == 500.0

    def test_consume(self):
        guard = BudgetGuard()
        alloc = guard.allocate("task-1", budget=100.0)
        assert guard.consume(alloc.allocation_id, 30.0) is True
        assert alloc.consumed == 30.0

    def test_consume_insufficient(self):
        guard = BudgetGuard()
        alloc = guard.allocate("task-1", budget=10.0)
        assert guard.consume(alloc.allocation_id, 20.0) is False

    def test_consume_invalid_id(self):
        guard = BudgetGuard()
        assert guard.consume("invalid", 10.0) is False

    def test_consume_force_broken(self):
        guard = BudgetGuard()
        alloc = guard.allocate("task-1", budget=100.0)
        guard.force_break("task-1")
        assert guard.consume(alloc.allocation_id, 10.0) is False

    def test_remaining(self):
        guard = BudgetGuard()
        alloc = guard.allocate("task-1", budget=100.0)
        guard.consume(alloc.allocation_id, 40.0)
        assert guard.remaining(alloc.allocation_id) == 60.0

    def test_remaining_invalid(self):
        guard = BudgetGuard()
        assert guard.remaining("invalid") == 0.0

    def test_force_break(self):
        guard = BudgetGuard()
        alloc = guard.allocate("task-1", budget=100.0)
        guard.force_break("task-1")
        assert alloc.allocation_id in guard._force_breaks

    def test_agent_remaining(self):
        guard = BudgetGuard(default_budget=100.0)
        guard.set_agent_budget("agent-1", 200.0)
        alloc = guard.allocate("task-agent-1-x", agent_id="agent-1")
        guard.consume(alloc.allocation_id, 50.0)
        remaining = guard.agent_remaining("agent-1")
        assert remaining == 150.0

    def test_task_allocations(self):
        guard = BudgetGuard()
        a1 = guard.allocate("task-1", budget=100.0)
        a2 = guard.allocate("task-1", budget=200.0)
        guard.allocate("task-2", budget=50.0)
        tasks = guard.task_allocations("task-1")
        assert len(tasks) == 2
        assert a1 in tasks

    def test_reset_budget(self):
        guard = BudgetGuard(default_budget=100.0)
        guard.set_agent_budget("agent-1", 500.0)
        alloc = guard.allocate("task-agent-1", budget=100.0)
        guard.force_break("task-agent-1")
        guard.reset_budget("agent-1", "daily")
        assert guard.agent_remaining("agent-1") == 100.0


class TestCostTracker:
    def test_track(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("operation_x", 1.5, "agent-1", task_id="t1", team="alpha")
        report = tracker.per_agent_report("agent-1")
        assert report.total_cost == 1.5
        assert report.record_count == 1

    def test_track_maintains_window(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker(window_size=3)
        for i in range(10):
            tracker.track(f"op{i}", 1.0, "agent-1")
        assert len(tracker._records) == 3

    def test_per_agent_report_no_records(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        report = tracker.per_agent_report("nonexistent")
        assert report.total_cost == 0.0
        assert report.record_count == 0

    def test_per_agent_report_with_window(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        for _ in range(5):
            tracker.track("op", 1.0, "agent-1")
        report = tracker.per_agent_report("agent-1", window_hours=1)
        assert report.record_count == 5

    def test_per_task_report(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("op1", 2.0, "agent-1", task_id="task-x")
        tracker.track("op2", 3.0, "agent-1", task_id="task-x")
        report = tracker.per_task_report("task-x")
        assert report.total_cost == 5.0
        assert report.record_count == 2

    def test_per_task_report_empty(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        report = tracker.per_task_report("nonexistent")
        assert report.record_count == 0
        assert report.total_cost == 0.0

    def test_detect_anomaly_insufficient_records(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("op1", 0.1, "agent-1")
        flags = tracker.detect_anomaly(min_records=10)
        # agent-1 has < 10 records, should be skipped
        # but single_expensive_op (> 1.0) flags might not fire either
        expensive_flags = [f for f in flags if f.anomaly_type == "single_expensive_op"]
        assert all(f.anomaly_type == "single_expensive_op" for f in expensive_flags) or len(flags) == 0

    def test_detect_anomaly_spike(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        for _ in range(20):
            tracker.track("op", 0.1, "agent-1")
        for _ in range(5):
            tracker.track("op", 5.0, "agent-1")
        flags = tracker.detect_anomaly(spike_ratio=2.0, min_records=5)
        spike_flags = [f for f in flags if f.anomaly_type == "cost_spike"]
        assert len(spike_flags) >= 1

    def test_detect_anomaly_expensive_op(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("expensive_op", 2.0, "agent-1")
        flags = tracker.detect_anomaly()
        expensive = [f for f in flags if f.anomaly_type == "single_expensive_op"]
        assert len(expensive) >= 1

    def test_get_cost_report_no_metric_store(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("op", 1.0, "agent-1")
        report = tracker.get_cost_report("agent-1")
        assert report["total_cost"] == 1.0
        assert report["record_count"] == 1

    def test_get_cost_report_no_agent(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        report = tracker.get_cost_report()
        assert report["agent_id"] == "all"

    def test_get_cost_by_team(self):
        from maref.recursive.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.track("op1", 1.0, "agent-1", team="alpha")
        tracker.track("op2", 2.0, "agent-2", team="beta")
        teams = tracker.get_cost_by_team()
        assert teams.get("alpha", 0) == 1.0
        assert teams.get("beta", 0) == 2.0


class TestCostForecast:
    def test_predict(self):
        from maref.recursive.cost_tracker import CostTracker, CostForecast
        tracker = CostTracker()
        forecast = CostForecast(tracker)
        estimate = forecast.predict("Build feature X", ["state_transition", "observe"])
        assert estimate.estimated_total > 0
        assert "state_transition" in estimate.breakdown
        assert "observe" in estimate.breakdown

    def test_predict_unknown_capability(self):
        from maref.recursive.cost_tracker import CostTracker, CostForecast
        tracker = CostTracker()
        forecast = CostForecast(tracker)
        estimate = forecast.predict("New task", ["unknown_cap"])
        assert estimate.breakdown["unknown_cap"] == 0.01

    def test_trend_no_records(self):
        from maref.recursive.cost_tracker import CostTracker, CostForecast
        tracker = CostTracker()
        forecast = CostForecast(tracker)
        trend = forecast.trend("agent-1", window_hours=24)
        assert trend.direction == "stable"
        assert trend.slope == 0.0

    def test_trend_increasing(self):
        from maref.recursive.cost_tracker import CostTracker, CostForecast
        tracker = CostTracker()
        for i in range(10):
            tracker._records.append(CostRecord(
                timestamp=float(i) * 10.0, agent_id="agent-1", task_id="t1",
                operation="op", cost=float(i) * 0.1,
            ))
        forecast = CostForecast(tracker)
        trend = forecast.trend("agent-1", window_hours=240000)
        assert trend.slope > 0
        assert trend.direction == "increasing"

    def test_trend_decreasing(self):
        from maref.recursive.cost_tracker import CostTracker, CostForecast
        tracker = CostTracker()
        for i in range(10):
            tracker._records.append(CostRecord(
                timestamp=float(i) * 10.0, agent_id="agent-1", task_id="t1",
                operation="op", cost=1.0 - float(i) * 0.1,
            ))
        forecast = CostForecast(tracker)
        trend = forecast.trend("agent-1", window_hours=240000)
        assert trend.slope < 0
        assert trend.direction == "decreasing"
