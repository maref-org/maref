from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.observability.metric_store import MetricStore

logger = logging.getLogger(__name__)


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
    """Meter and track gas consumption for governance operations.

    Each operation type has a predefined cost structure (base gas + per-token
    + per-second). GasMeter records each metered operation and provides
    total spent and estimation queries.
    """

    def __init__(self, operation_costs: dict[str, OperationCost] | None = None) -> None:
        """Initialize the gas meter.

        Args:
            operation_costs: Custom operation cost map. Defaults to _DEFAULT_OPERATION_COSTS.
        """
        self._operation_costs = operation_costs or dict(_DEFAULT_OPERATION_COSTS)
        self._records: list[GasRecord] = []

    def meter(
        self,
        operation_type: str,
        input_size: int = 0,
        output_size: int = 0,
        duration_seconds: float = 0.0,
    ) -> float:
        """Meter an operation and record the gas cost.

        Computes cost as: base_gas + input * gas_per_input + output * gas_per_output
        + duration * gas_per_second.

        Args:
            operation_type: Type of operation being metered.
            input_size: Number of input tokens/bytes.
            output_size: Number of output tokens/bytes.
            duration_seconds: Wall-clock duration of the operation.

        Returns:
            The computed gas cost for this operation.
        """
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

    def estimate(
        self,
        operation_type: str,
        input_size: int = 0,
        output_size: int = 0,
        duration_seconds: float = 0.0,
    ) -> float:
        """Estimate gas cost without recording the operation.

        Args:
            operation_type: Type of operation to estimate.
            input_size: Estimated input tokens/bytes.
            output_size: Estimated output tokens/bytes.
            duration_seconds: Estimated duration in seconds.

        Returns:
            The estimated gas cost.
        """
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
        """Total gas spent across all metered operations.

        Returns:
            Sum of all recorded gas costs.
        """
        return sum(r.gas_spent for r in self._records)

    def records(self) -> list[GasRecord]:
        """Return all gas meter records.

        Returns:
            A copy of the list of GasRecord instances.
        """
        return list(self._records)

    def set_operation_cost(self, operation_type: str, cost: OperationCost) -> None:
        """Set or update the cost structure for an operation type.

        Args:
            operation_type: The operation type key.
            cost: The OperationCost definition to assign.
        """
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
    """Manages budget allocations for tasks and agents.

    Supports per-agent budgets, per-task allocations, force-break for
    emergency halting, and optional MetricStore persistence.
    """

    def __init__(self, default_budget: float = 100.0, metric_store: MetricStore | None = None) -> None:
        """Initialize the budget guard.

        Args:
            default_budget: Default budget for tasks without explicit allocation.
            metric_store: Optional MetricStore for persisting cost records.
        """
        self._default_budget = default_budget
        self._allocations: dict[str, BudgetAllocation] = {}
        self._agent_budgets: dict[str, float] = {}
        self._force_breaks: set[str] = set()
        self._metric_store = metric_store

    def allocate(
        self, task_id: str, budget: float | None = None, agent_id: str = ""
    ) -> BudgetAllocation:
        """Allocate a budget for a task.

        Uses agent-level budget if agent_id has a custom budget set,
        otherwise falls back to the provided budget or default.

        Args:
            task_id: The task to allocate budget for.
            budget: Explicit budget amount. Overrides default but not agent budget.
            agent_id: Optional agent for agent-level budget lookup.

        Returns:
            A new BudgetAllocation instance.
        """
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
        """Consume budget from an allocation.

        Args:
            allocation_id: The allocation to deduct from.
            amount: Amount to consume.

        Returns:
            True if consumption was allowed, False if allocation not found,
            force-broken, or insufficient budget remaining.
        """
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
        """Get remaining budget for an allocation.

        Args:
            allocation_id: The allocation to query.

        Returns:
            Remaining budget, or 0.0 if allocation not found.
        """
        alloc = self._allocations.get(allocation_id)
        return alloc.remaining if alloc else 0.0

    def force_break(self, task_id: str) -> None:
        """Forcefully stop all allocations for a task.

        Marks allocations as force-broken, preventing further consumption.

        Args:
            task_id: The task whose allocations should be broken.
        """
        for alloc in self._allocations.values():
            if alloc.task_id == task_id:
                self._force_breaks.add(alloc.allocation_id)

    def set_agent_budget(self, agent_id: str, budget: float) -> None:
        """Set a custom budget limit for an agent.

        Args:
            agent_id: The agent identifier.
            budget: The budget amount.
        """
        self._agent_budgets[agent_id] = budget

    def agent_remaining(self, agent_id: str) -> float:
        """Get remaining budget for an agent across all tasks.

        Combines in-memory consumption with optional MetricStore records.

        Args:
            agent_id: The agent identifier.

        Returns:
            Remaining budget (never negative).
        """
        total_consumed = sum(
            alloc.consumed for alloc in self._allocations.values() if agent_id in alloc.task_id
        )
        if self._metric_store:
            db_records = self._metric_store.query("cost", agent_id=agent_id, table="cost_metrics")
            total_consumed += sum(r["value"] for r in db_records)
        budget = self._agent_budgets.get(agent_id, self._default_budget)
        return max(0.0, budget - total_consumed)

    def task_allocations(self, task_id: str) -> list[BudgetAllocation]:
        """Get all allocations for a specific task.

        Args:
            task_id: The task identifier.

        Returns:
            List of BudgetAllocation instances for this task.
        """
        return [a for a in self._allocations.values() if a.task_id == task_id]

    def reset_budget(self, agent_id: str, period: str) -> None:
        """Reset budget for an agent for a new period.

        Clears force-breaks and removes stale allocations for this agent.

        Args:
            agent_id: The agent to reset.
            period: Period identifier (e.g. 'daily', 'monthly').
        """
        self._force_breaks.clear()
        stale = [
            aid
            for aid, alloc in self._allocations.items()
            if agent_id in alloc.task_id
        ]
        for aid in stale:
            self._allocations.pop(aid, None)
        if agent_id in self._agent_budgets:
            self._agent_budgets[agent_id] = self._default_budget


@dataclass
class CostRecord:
    timestamp: float
    agent_id: str
    task_id: str
    operation: str
    cost: float
    allocation_id: str = ""
    team: str = ""
    project: str = ""


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
    """Tracks operation costs per agent, task, and team.

    Maintains a sliding window of cost records in memory and optionally
    persists to MetricStore. Supports per-agent reports, anomaly detection,
    and team-level cost aggregation.
    """

    def __init__(self, window_size: int = 1000, metric_store: MetricStore | None = None) -> None:
        """Initialize the cost tracker.

        Args:
            window_size: Maximum number of in-memory records to retain.
            metric_store: Optional MetricStore for persistent cost tracking.
        """
        self._records: list[CostRecord] = []
        self._window_size = window_size
        self._baseline_costs: dict[str, list[float]] = {}
        self._metric_store = metric_store

    def track(
        self, operation: str, cost: float, agent_id: str, task_id: str = "",
        allocation_id: str = "", team: str = "", project: str = "",
    ) -> None:
        """Record a cost tracking event.

        Appends to the in-memory sliding window and optionally persists
        to MetricStore.

        Args:
            operation: Name of the operation being tracked.
            cost: Cost value of the operation.
            agent_id: The agent that performed the operation.
            task_id: Optional task identifier.
            allocation_id: Optional budget allocation identifier.
            team: Optional team label for aggregation.
            project: Optional project label for aggregation.
        """
        record = CostRecord(
            timestamp=time.time(),
            agent_id=agent_id,
            task_id=task_id,
            operation=operation,
            cost=cost,
            allocation_id=allocation_id,
            team=team,
            project=project,
        )
        self._records.append(record)
        if len(self._records) > self._window_size:
            self._records = self._records[-self._window_size :]
        if self._metric_store:
            try:
                self._metric_store.record(
                    "cost", cost,
                    labels={"operation": operation, "task_id": task_id, "team": team, "project": project},
                    agent_id=agent_id, table="cost_metrics",
                )
            except Exception as exc:
                logger.warning("Failed to record cost metric: %s", exc)

    def per_agent_report(self, agent_id: str, window_hours: float | None = None) -> CostReport:
        """Generate a cost report for a specific agent.

        Args:
            agent_id: The agent to report on.
            window_hours: Optional time window in hours. If None, all records.

        Returns:
            CostReport with total_cost, operation_breakdown, and record_count.
        """
        now = time.time()
        report = CostReport(agent_id=agent_id, period_end=now)

        cutoff = now - (window_hours * 3600) if window_hours else 0.0
        relevant = [r for r in self._records if r.agent_id == agent_id and r.timestamp >= cutoff]
        if relevant:
            report.period_start = min(r.timestamp for r in relevant)
        report.record_count = len(relevant)
        report.total_cost = sum(r.cost for r in relevant)
        for r in relevant:
            report.operation_breakdown[r.operation] = (
                report.operation_breakdown.get(r.operation, 0.0) + r.cost
            )
        return report

    def per_task_report(self, task_id: str) -> CostReport:
        """Generate a cost report for a specific task.

        Args:
            task_id: The task to report on.

        Returns:
            CostReport with total_cost and operation_breakdown.
        """
        relevant = [r for r in self._records if r.task_id == task_id]
        agent_id = relevant[0].agent_id if relevant else ""
        report = CostReport(agent_id=agent_id)
        report.record_count = len(relevant)
        report.total_cost = sum(r.cost for r in relevant)
        if relevant:
            report.period_start = min(r.timestamp for r in relevant)
            report.period_end = max(r.timestamp for r in relevant)
        for r in relevant:
            report.operation_breakdown[r.operation] = (
                report.operation_breakdown.get(r.operation, 0.0) + r.cost
            )
        return report

    def detect_anomaly(self, spike_ratio: float = 3.0, min_records: int = 10) -> list[AnomalyFlag]:
        """Detect cost anomalies across all tracked agents.

        Compares recent average cost to overall average for spike detection,
        and flags individual operations that exceed a cost threshold.

        Args:
            spike_ratio: Ratio threshold for spike detection (default 3.0x).
            min_records: Minimum records needed per agent for analysis.

        Returns:
            List of AnomalyFlag instances with severity WARNING or HIGH.
        """
        flags: list[AnomalyFlag] = []
        by_agent: dict[str, list[float]] = {}
        for r in self._records:
            by_agent.setdefault(r.agent_id, []).append(r.cost)

        for agent_id, costs in by_agent.items():
            if len(costs) < min_records:
                continue
            avg = sum(costs) / len(costs)
            if avg > 0:
                recent = costs[-max(5, len(costs) // 5) :]
                recent_avg = sum(recent) / len(recent)
                ratio = recent_avg / avg
                if ratio >= spike_ratio:
                    flags.append(
                        AnomalyFlag(
                            agent_id=agent_id,
                            anomaly_type="cost_spike",
                            description=f"Recent cost {recent_avg:.4f} is {ratio:.1f}x baseline {avg:.4f}",
                            severity="WARNING" if ratio < 5.0 else "HIGH",
                            cost_spike_ratio=ratio,
                        )
                    )

        for r in self._records:
            if r.cost > 1.0:
                flags.append(
                    AnomalyFlag(
                        agent_id=r.agent_id,
                        anomaly_type="single_expensive_op",
                        description=f"Operation '{r.operation}' cost {r.cost:.2f} exceeds threshold",
                        severity="WARNING",
                        cost_spike_ratio=r.cost / 0.01,
                    )
                )

        return flags

    def get_cost_report(self, agent_id: str | None = None, since: str | None = None) -> dict[str, Any]:
        """Get a cost report, optionally from MetricStore persistence.

        Args:
            agent_id: Optional agent filter.
            since: Optional ISO 8601 start timestamp.

        Returns:
            Dictionary with agent_id, total_cost, record_count, and records.
        """
        if self._metric_store:
            try:
                results = self._metric_store.query("cost", agent_id=agent_id, since=since, table="cost_metrics")
                return {
                    "agent_id": agent_id or "all",
                    "total_cost": sum(r["value"] for r in results),
                    "record_count": len(results),
                    "records": results,
                }
            except Exception as exc:
                logger.warning("Failed to query cost report: %s", exc)
        report = self.per_agent_report(agent_id) if agent_id else CostReport(agent_id="all")
        return {
            "agent_id": agent_id or "all",
            "total_cost": report.total_cost,
            "record_count": report.record_count,
        }

    def get_cost_by_team(self) -> dict[str, float]:
        """Aggregate costs by team label.

        Queries MetricStore first if available, otherwise falls back to
        in-memory records.

        Returns:
            Dictionary mapping team names to total costs.
        """
        teams: dict[str, float] = {}
        if self._metric_store:
            try:
                results = self._metric_store.query("cost", table="cost_metrics")
                for r in results:
                    labels = r.get("labels", {})
                    team = labels.get("team", "unknown")
                    teams[team] = teams.get(team, 0.0) + r["value"]
                return teams
            except Exception as exc:
                logger.warning("Failed to query cost by team: %s", exc)
        for record in self._records:
            team = record.team or "unknown"
            teams[team] = teams.get(team, 0.0) + record.cost
        return teams


class CostForecast:
    """Forecasts and trends for agent operation costs.

    Uses historical data from CostTracker to predict future costs and
    compute linear regression trends.
    """

    def __init__(self, tracker: CostTracker) -> None:
        """Initialize the cost forecaster.

        Args:
            tracker: The CostTracker instance to source historical data from.
        """
        self._tracker = tracker

    def predict(self, task_description: str, agent_capabilities: list[str]) -> CostEstimate:
        """Predict the cost of a task based on required capabilities.

        Args:
            task_description: Description of the task.
            agent_capabilities: List of capability names required.

        Returns:
            CostEstimate with estimated_total and per-capability breakdown.
        """
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
        """Compute a cost trend for an agent using linear regression.

        Args:
            agent_id: The agent to analyze.
            window_hours: Time window in hours (default 24).

        Returns:
            CostTrend with slope, direction, and data points.
        """
        report = self._tracker.per_agent_report(agent_id, window_hours)
        records = [
            r
            for r in self._tracker._records
            if r.agent_id == agent_id and r.timestamp >= report.period_start
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
