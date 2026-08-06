from __future__ import annotations

from maref.recursive.cost_tracker import (
    BudgetGuard,
    CostEstimate,
    CostForecast,
    CostTracker,
    GasMeter,
    OperationCost,
)


class TestGasMeter:
    def test_meter_known_operation(self) -> None:
        meter = GasMeter()
        cost = meter.meter("state_transition")
        assert cost >= 0
        assert meter.total_spent() == cost

    def test_meter_unknown_operation(self) -> None:
        meter = GasMeter()
        cost = meter.meter("custom_operation", input_size=100, output_size=50)
        assert cost >= 0

    def test_estimate(self) -> None:
        meter = GasMeter()
        estimated = meter.estimate("observe")
        assert estimated >= 0

    def test_multiple_operations(self) -> None:
        meter = GasMeter()
        meter.meter("state_transition")
        meter.meter("circuit_break")
        meter.meter("halt")
        assert len(meter.records()) == 3
        assert meter.total_spent() > 0

    def test_set_operation_cost(self) -> None:
        meter = GasMeter()
        meter.set_operation_cost("custom_op", OperationCost("custom_op", 0.5, 0.01, 0.02))
        cost = meter.meter("custom_op", input_size=10, output_size=5)
        assert cost == 0.5 + 0.1 + 0.1

    def test_records_are_sequential(self) -> None:
        meter = GasMeter()
        meter.meter("state_transition")
        meter.meter("observe")
        records = meter.records()
        assert records[0].operation_type == "state_transition"
        assert records[1].operation_type == "observe"


class TestBudgetGuard:
    def test_allocate_and_consume(self) -> None:
        guard = BudgetGuard()
        alloc = guard.allocate("task_1", budget=100.0)
        assert guard.consume(alloc.allocation_id, 30.0)
        assert alloc.consumed == 30.0
        assert alloc.remaining == 70.0

    def test_consume_exceeds_budget(self) -> None:
        guard = BudgetGuard()
        alloc = guard.allocate("task_1", budget=10.0)
        assert guard.consume(alloc.allocation_id, 5.0)
        assert not guard.consume(alloc.allocation_id, 10.0)
        assert alloc.consumed == 5.0

    def test_force_break(self) -> None:
        guard = BudgetGuard()
        alloc = guard.allocate("task_1", budget=100.0)
        guard.consume(alloc.allocation_id, 10.0)
        guard.force_break("task_1")
        assert not guard.consume(alloc.allocation_id, 5.0)

    def test_remaining(self) -> None:
        guard = BudgetGuard()
        alloc = guard.allocate("task_x", budget=50.0)
        guard.consume(alloc.allocation_id, 20.0)
        assert guard.remaining(alloc.allocation_id) == 30.0

    def test_agent_budget(self) -> None:
        guard = BudgetGuard()
        guard.set_agent_budget("agent_a", 200.0)
        alloc = guard.allocate("task_1", None, agent_id="agent_a")
        assert alloc.budget == 200.0

    def test_task_allocations(self) -> None:
        guard = BudgetGuard()
        guard.allocate("task_1", budget=10.0)
        guard.allocate("task_1", budget=20.0)
        allocs = guard.task_allocations("task_1")
        assert len(allocs) == 2

    def test_allocation_exhausted(self) -> None:
        guard = BudgetGuard()
        alloc = guard.allocate("task_1", budget=5.0)
        guard.consume(alloc.allocation_id, 5.0)
        assert alloc.is_exhausted
        assert alloc.usage_pct == 100.0


class TestCostTracker:
    def test_track_and_report(self) -> None:
        tracker = CostTracker()
        tracker.track("state_transition", 0.01, "agent_a", "task_1")
        tracker.track("observe", 0.001, "agent_a", "task_1")
        tracker.track("circuit_break", 0.0, "agent_b", "task_2")

        report_a = tracker.per_agent_report("agent_a")
        assert report_a.record_count == 2
        assert report_a.total_cost > 0

    def test_per_task_report(self) -> None:
        tracker = CostTracker()
        tracker.track("state_transition", 0.01, "agent_a", "task_1")
        tracker.track("observe", 0.001, "agent_b", "task_1")

        report = tracker.per_task_report("task_1")
        assert report.record_count == 2

    def test_detect_anomaly_spike(self) -> None:
        tracker = CostTracker()
        for _ in range(10):
            tracker.track("observe", 0.001, "agent_a", "task_normal")
        tracker.track("state_transition", 10.0, "agent_a", "task_spike")

        anomalies = tracker.detect_anomaly(spike_ratio=2.0)
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == "single_expensive_op" for a in anomalies)

    def test_operation_breakdown(self) -> None:
        tracker = CostTracker()
        tracker.track("state_transition", 0.01, "agent_a", "t")
        tracker.track("observe", 0.001, "agent_a", "t")
        tracker.track("observe", 0.002, "agent_a", "t")

        report = tracker.per_agent_report("agent_a")
        assert "state_transition" in report.operation_breakdown
        assert "observe" in report.operation_breakdown

    def test_detect_no_anomaly_normal(self) -> None:
        tracker = CostTracker()
        for _ in range(20):
            tracker.track("observe", 0.001, "agent_a", "normal_task")
        anomalies = tracker.detect_anomaly()
        assert len(anomalies) == 0


class TestCostForecast:
    def test_predict_from_capabilities(self) -> None:
        tracker = CostTracker()
        forecaster = CostForecast(tracker)
        estimate = forecaster.predict("test task", ["state_transition", "observe"])
        assert isinstance(estimate, CostEstimate)
        assert estimate.estimated_total > 0
        assert "state_transition" in estimate.breakdown

    def test_trend_no_data(self) -> None:
        tracker = CostTracker()
        forecaster = CostForecast(tracker)
        trend = forecaster.trend("nonexistent_agent")
        assert trend.direction == "stable"

    def test_trend_with_data(self) -> None:
        tracker = CostTracker()
        for i in range(10):
            tracker.track("observe", 0.001 * (i + 1), "agent_a", "task_trend")
        forecaster = CostForecast(tracker)
        trend = forecaster.trend("agent_a")
        assert trend.agent_id == "agent_a"
