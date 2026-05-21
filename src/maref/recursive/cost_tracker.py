from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class OperationCost:
    operation_type: str
    base_gas: float
    gas_per_input_token: float
    gas_per_output_token: float
    gas_per_second: float = 0.0


_DEFAULT_OPERATION_COSTS: dict[str, OperationCost] = {
    "state_transition": OperationCost("state_transition", 0.01, 0.0, 0.0),
    "circuit_break": OperationCost("circuit_break", 0.0, 0.0, 0.0),
    "halt": OperationCost("halt", 0.0, 0.0, 0.0),
    "observe": OperationCost("observe", 0.001, 0.0, 0.0),
    "collect": OperationCost("collect", 0.002, 0.0, 0.0),
    "monitor": OperationCost("monitor", 0.005, 0.0, 0.0, 0.001),
    "graph_query": OperationCost("graph_query", 0.001, 0.0, 0.0),
    "hypothesis_test": OperationCost("hypothesis_test", 0.003, 0.0005, 0.001),
    "relation_infer": OperationCost("relation_infer", 0.002, 0.001, 0.0),
    "did_resolve": OperationCost("did_resolve", 0.001, 0.0, 0.0),
    "vc_verify": OperationCost("vc_verify", 0.001, 0.0, 0.0),
    "trust_evaluate": OperationCost("trust_evaluate", 0.002, 0.0, 0.0),
    "negotiation": OperationCost("negotiation", 0.005, 0.001, 0.001),
    "handoff": OperationCost("handoff", 0.003, 0.0, 0.0),
    "dispatch": OperationCost("dispatch", 0.001, 0.0, 0.0),
}


class GasMeter:
    def __init__(self, operation_costs: dict[str, OperationCost] | None = None) -> None:
        self._operation_costs = operation_costs or dict(_DEFAULT_OPERATION_COSTS)
        self._records: list[GasRecord] = []

    def meter(self, operation_type: str, input_size: int = 0,
              output_size: int = 0, duration_seconds: float = 0.0) -> float:
        cost_entry = self._operation_costs.get(operation_type)
        if cost_entry is None:
            cost_entry = OperationCost(operation_type, 0.001, 0.0, 0.0)
        gas = (
            cost_entry.base_gas
            + input_size * cost_entry.gas_per_input_token
            + output_size * cost_entry.gas_per_output_token
            + duration_seconds * cost_entry.gas_per_second
        )
        record = GasRecord(
            operation_type=operation_type,
            gas_spent=gas,
            input_size=input_size,
            output_size=output_size,
        )
        self._records.append(record)
        return gas

    def estimate(self, operation_type: str, input_size: int = 0,
                 output_size: int = 0, duration_seconds: float = 0.0) -> float:
        cost_entry = self._operation_costs.get(operation_type)
        if cost_entry is None:
            cost_entry = OperationCost(operation_type, 0.001, 0.0, 0.0)
        return (
            cost_entry.base_gas
            + input_size * cost_entry.gas_per_input_token
            + output_size * cost_entry.gas_per_output_token
            + duration_seconds * cost_entry.gas_per_second
        )

    def total_spent(self) -> float:
        return sum(r.gas_spent for r in self._records)

    def records(self) -> list[GasRecord]:
        return list(self._records)

    def set_operation_cost(self, operation_type: str, cost: OperationCost) -> None:
        self._operation_costs[operation_type] = cost


@dataclass
class GasRecord:
    operation_type: str
    gas_spent: float
    input_size: int = 0
    output_size: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class BudgetAllocation:
    allocation_id: str
    task_id: str
    budget: float
    consumed: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.consumed)

    @property
    def is_exhausted(self) -> bool:
        return self.consumed >= self.budget

    @property
    def usage_pct(self) -> float:
        return (self.consumed / self.budget * 100) if self.budget > 0 else 0.0


class BudgetGuard:
    def __init__(self, default_budget: float = 100.0) -> None:
        self._default_budget = default_budget
        self._allocations: dict[str, BudgetAllocation] = {}
        self._agent_budgets: dict[str, float] = {}
        self._force_breaks: set[str] = set()

    def allocate(self, task_id: str, budget: float | None = None,
                 agent_id: str = "") -> BudgetAllocation:
        effective_budget = budget or self._default_budget
        if agent_id and agent_id in self._agent_budgets:
            effective_budget = self._agent_budgets[agent_id]
        alloc = BudgetAllocation(
            allocation_id=uuid.uuid4().hex[:12],
            task_id=task_id,
            budget=effective_budget,
        )
        self._allocations[alloc.allocation_id] = alloc
        return alloc

    def consume(self, allocation_id: str, amount: float) -> bool:
        alloc = self._allocations.get(allocation_id)
        if alloc is None:
            return False
        if allocation_id in self._force_breaks:
            return False
        if alloc.consumed + amount > alloc.budget:
            return False
        alloc.consumed += amount
        return True

    def remaining(self, allocation_id: str) -> float:
        alloc = self._allocations.get(allocation_id)
        return alloc.remaining if alloc else 0.0

    def force_break(self, task_id: str) -> None:
        for alloc in self._allocations.values():
            if alloc.task_id == task_id:
                self._force_breaks.add(alloc.allocation_id)

    def set_agent_budget(self, agent_id: str, budget: float) -> None:
        self._agent_budgets[agent_id] = budget

    def agent_remaining(self, agent_id: str) -> float:
        total_consumed = sum(
            alloc.consumed for alloc in self._allocations.values()
            if agent_id in alloc.task_id
        )
        budget = self._agent_budgets.get(agent_id, self._default_budget)
        return max(0.0, budget - total_consumed)

    def task_allocations(self, task_id: str) -> list[BudgetAllocation]:
        return [a for a in self._allocations.values() if a.task_id == task_id]


@dataclass
class CostRecord:
    timestamp: float
    agent_id: str
    task_id: str
    operation: str
    cost: float
    allocation_id: str = ""


@dataclass
class CostReport:
    agent_id: str
    total_cost: float = 0.0
    operation_breakdown: dict[str, float] = field(default_factory=dict)
    record_count: int = 0
    period_start: float = 0.0
    period_end: float = 0.0


@dataclass
class AnomalyFlag:
    agent_id: str
    anomaly_type: str
    description: str
    severity: str
    cost_spike_ratio: float = 0.0


@dataclass
class CostTrend:
    agent_id: str
    window_hours: int
    data_points: list[tuple[float, float]] = field(default_factory=list)
    slope: float = 0.0
    direction: str = "stable"


class CostTracker:
    def __init__(self, window_size: int = 1000) -> None:
        self._records: list[CostRecord] = []
        self._window_size = window_size
        self._baseline_costs: dict[str, list[float]] = {}

    def track(self, operation: str, cost: float, agent_id: str,
              task_id: str = "", allocation_id: str = "") -> None:
        self._records.append(CostRecord(
            timestamp=time.time(),
            agent_id=agent_id,
            task_id=task_id,
            operation=operation,
            cost=cost,
            allocation_id=allocation_id,
        ))
        if len(self._records) > self._window_size:
            self._records = self._records[-self._window_size:]

    def per_agent_report(self, agent_id: str,
                         window_hours: float | None = None) -> CostReport:
        now = time.time()
        report = CostReport(agent_id=agent_id, period_end=now)

        cutoff = now - (window_hours * 3600) if window_hours else 0.0
        relevant = [
            r for r in self._records
            if r.agent_id == agent_id and r.timestamp >= cutoff
        ]
        if relevant:
            report.period_start = min(r.timestamp for r in relevant)
        report.record_count = len(relevant)
        report.total_cost = sum(r.cost for r in relevant)
        for r in relevant:
            report.operation_breakdown[r.operation] = \
                report.operation_breakdown.get(r.operation, 0.0) + r.cost
        return report

    def per_task_report(self, task_id: str) -> CostReport:
        relevant = [r for r in self._records if r.task_id == task_id]
        agent_id = relevant[0].agent_id if relevant else ""
        report = CostReport(agent_id=agent_id)
        report.record_count = len(relevant)
        report.total_cost = sum(r.cost for r in relevant)
        if relevant:
            report.period_start = min(r.timestamp for r in relevant)
            report.period_end = max(r.timestamp for r in relevant)
        for r in relevant:
            report.operation_breakdown[r.operation] = \
                report.operation_breakdown.get(r.operation, 0.0) + r.cost
        return report

    def detect_anomaly(self, spike_ratio: float = 3.0,
                        min_records: int = 10) -> list[AnomalyFlag]:
        flags: list[AnomalyFlag] = []
        by_agent: dict[str, list[float]] = {}
        for r in self._records:
            by_agent.setdefault(r.agent_id, []).append(r.cost)

        for agent_id, costs in by_agent.items():
            if len(costs) < min_records:
                continue
            avg = sum(costs) / len(costs)
            if avg > 0:
                recent = costs[-max(5, len(costs) // 5):]
                recent_avg = sum(recent) / len(recent)
                ratio = recent_avg / avg
                if ratio >= spike_ratio:
                    flags.append(AnomalyFlag(
                        agent_id=agent_id,
                        anomaly_type="cost_spike",
                        description=f"Recent cost {recent_avg:.4f} is {ratio:.1f}x baseline {avg:.4f}",
                        severity="WARNING" if ratio < 5.0 else "HIGH",
                        cost_spike_ratio=ratio,
                    ))

        for r in self._records:
            if r.cost > 1.0:
                flags.append(AnomalyFlag(
                    agent_id=r.agent_id,
                    anomaly_type="single_expensive_op",
                    description=f"Operation '{r.operation}' cost {r.cost:.2f} exceeds threshold",
                    severity="WARNING",
                    cost_spike_ratio=r.cost / 0.01,
                ))

        return flags


class CostForecast:
    def __init__(self, tracker: CostTracker) -> None:
        self._tracker = tracker

    def predict(self, task_description: str,
                agent_capabilities: list[str]) -> CostEstimate:
        total_estimate = 0.0
        breakdown: dict[str, float] = {}
        for cap in agent_capabilities:
            est = _DEFAULT_OPERATION_COSTS.get(cap)
            if est:
                cost = est.base_gas * 2
                breakdown[cap] = cost
                total_estimate += cost
            else:
                breakdown[cap] = 0.01
                total_estimate += 0.01
        return CostEstimate(
            task_description=task_description,
            estimated_total=total_estimate,
            breakdown=breakdown,
        )

    def trend(self, agent_id: str, window_hours: int = 24) -> CostTrend:
        report = self._tracker.per_agent_report(agent_id, window_hours)
        records = [
            r for r in self._tracker._records
            if r.agent_id == agent_id
            and r.timestamp >= report.period_start
        ]

        if not records or len(records) < 2:
            return CostTrend(agent_id=agent_id, window_hours=window_hours)

        sorted_records = sorted(records, key=lambda r: r.timestamp)
        data_points = [(r.timestamp, r.cost) for r in sorted_records]
        n = len(data_points)

        sum_x = sum(p[0] for p in data_points)
        sum_y = sum(p[1] for p in data_points)
        sum_xy = sum(p[0] * p[1] for p in data_points)
        sum_xx = sum(p[0] * p[0] for p in data_points)
        denominator = n * sum_xx - sum_x * sum_x
        slope = (n * sum_xy - sum_x * sum_y) / denominator if denominator != 0 else 0.0

        direction = "stable"
        if slope > 0.001:
            direction = "increasing"
        elif slope < -0.001:
            direction = "decreasing"

        return CostTrend(
            agent_id=agent_id,
            window_hours=window_hours,
            data_points=[(p[0], p[1]) for p in data_points[-20:]],
            slope=slope,
            direction=direction,
        )


@dataclass
class CostEstimate:
    task_description: str
    estimated_total: float
    breakdown: dict[str, float] = field(default_factory=dict)
