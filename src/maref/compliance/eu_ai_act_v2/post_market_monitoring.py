"""EU AI Act Post-Market Monitoring — Art.61.

Implements Article 61 of Regulation (EU) 2024/1689:
- Art.61(1): Establish, document and maintain a post-market monitoring system
- Art.61(2): Collect and analyse data on performance throughout lifetime
- Art.61(3): Periodic review reports and trend analysis
- Art.61(4): Obligation for all high-risk and GPAI systems

Provides PMMPlan definition, observation recording, trend analysis with
slope computation, periodic report generation, and review scheduling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


@dataclass
class PMMPlan:
    """Post-market monitoring plan for a deployed AI system (Art.61(1)-(2))."""

    plan_id: str
    system_name: str
    system_version: str
    monitoring_objectives: list[str]
    data_sources: list[str]
    kpis: list[dict[str, Any]]
    review_interval_days: int = 365
    last_review_at: str = ""
    next_review_at: str = ""


@dataclass
class PMMObservation:
    """Single observation recorded from a monitoring data source."""

    obs_id: str
    plan_id: str
    source: str
    metric: str
    value: float
    threshold: float | None = None
    threshold_breached: bool = False
    timestamp: str = ""
    details: str = ""


@dataclass
class PMMTrendAnalysis:
    """Trend analysis result for a monitoring period (Art.61(3))."""

    period_start: str
    period_end: str
    metric_trends: dict[str, dict[str, float]]
    thresholds_breached: list[str]
    incident_correlation: list[dict[str, Any]]
    overall_assessment: str


@dataclass
class PeriodicReport:
    """Periodic post-market monitoring report (Art.61(3)-(4))."""

    report_id: str
    plan_id: str
    period_start: str
    period_end: str
    observation_count: int
    trend_analysis: PMMTrendAnalysis | None = None
    incidents_in_period: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""


def _compute_slope(values: list[float]) -> float:
    """Compute linear slope using least-squares approximation.

    Returns the slope coefficient; 0.0 for single-value or constant series.
    """
    n = len(values)
    if n < 2:
        return 0.0
    indices = list(range(n))
    sum_x = sum(indices)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(indices, values, strict=False))
    sum_xx = sum(x * x for x in indices)
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


class PMMManager:
    """Manages post-market monitoring plans, observations, and reports.

    Implements the Art.61 post-market monitoring system for high-risk
    and GPAI systems, including trend analysis, periodic reporting,
    and review scheduling.
    """

    def __init__(self) -> None:
        self._plans: dict[str, PMMPlan] = {}
        self._observations: dict[str, list[PMMObservation]] = {}
        self._reports: dict[str, list[PeriodicReport]] = {}

    def create_plan(
        self,
        system_name: str,
        objectives: list[str],
        data_sources: list[str],
        kpis: list[dict[str, Any]],
        **kwargs: Any,
    ) -> PMMPlan:
        """Create a new post-market monitoring plan.

        Args:
            system_name: Name of the AI system.
            objectives: Monitoring objectives.
            data_sources: Data sources for monitoring.
            kpis: Key performance indicators with thresholds.
            **kwargs: Additional fields (system_version, review_interval_days,
                last_review_at, next_review_at).

        Returns:
            The newly created PMMPlan.
        """
        plan_id = f"pmm-{uuid4().hex[:8]}"
        plan = PMMPlan(
            plan_id=plan_id,
            system_name=system_name,
            system_version=kwargs.pop("system_version", "1.0.0"),
            monitoring_objectives=list(objectives),
            data_sources=list(data_sources),
            kpis=list(kpis),
            review_interval_days=kwargs.pop("review_interval_days", 365),
            last_review_at=kwargs.pop("last_review_at", ""),
            next_review_at=kwargs.pop("next_review_at", ""),
        )
        self._plans[plan_id] = plan
        self._observations[plan_id] = []
        self._reports[plan_id] = []
        return plan

    @staticmethod
    def _is_threshold_breach(
        value: float,
        threshold: float,
        kpi_target: float | None = None,
    ) -> bool:
        """Determine if a value breaches a threshold.

        Uses the KPI target to infer breach direction:
        - If target > threshold (e.g. accuracy): higher is better,
          breach when value < threshold.
        - If target < threshold (e.g. latency): lower is better,
          breach when value > threshold.
        - If no target: default to value > threshold.
        """
        if kpi_target is not None and kpi_target > threshold:
            return value < threshold
        return value > threshold

    def record_observation(
        self,
        plan_id: str,
        source: str,
        metric: str,
        value: float,
        **kwargs: Any,
    ) -> PMMObservation:
        """Record a monitoring observation.

        Automatically detects threshold breach by comparing the value
        against the provided threshold or the KPI threshold from the plan.

        Args:
            plan_id: The monitoring plan ID.
            source: Data source name.
            metric: Metric name.
            value: Observed value.
            **kwargs: Additional fields (threshold, details, timestamp).

        Returns:
            The recorded PMMObservation.
        """
        threshold = kwargs.get("threshold")
        details = kwargs.get("details", "")
        timestamp = kwargs.get("timestamp", datetime.now(timezone.utc).isoformat())

        kpi_target: float | None = None
        plan = self._plans.get(plan_id)
        if plan and threshold is not None:
            for kpi in plan.kpis:
                if kpi.get("name") == metric and "target" in kpi:
                    kpi_target = float(kpi["target"])
                    break

        threshold_breached = False
        if threshold is not None:
            threshold_breached = self._is_threshold_breach(value, threshold, kpi_target)

        obs = PMMObservation(
            obs_id=f"obs-{uuid4().hex[:8]}",
            plan_id=plan_id,
            source=source,
            metric=metric,
            value=value,
            threshold=threshold,
            threshold_breached=threshold_breached,
            timestamp=timestamp,
            details=details,
        )
        if plan_id in self._observations:
            self._observations[plan_id].append(obs)
        return obs

    def run_trend_analysis(
        self,
        plan_id: str,
        period_start: str,
        period_end: str,
    ) -> PMMTrendAnalysis:
        """Run trend analysis for a plan over a given period.

        For each metric observed in the period, calculates mean, min,
        max, std, and linear slope. Determines overall assessment:
        - "critical" if any threshold breached
        - "degrading" if any negative slope suggests degradation
        - "stable" otherwise

        Args:
            plan_id: The monitoring plan ID.
            period_start: ISO date string for period start.
            period_end: ISO date string for period end.

        Returns:
            PMMTrendAnalysis with metric trends, breached thresholds,
            incident correlations, and overall assessment.
        """
        plan = self._plans.get(plan_id)
        kpi_thresholds: dict[str, float] = {}
        kpi_targets: dict[str, float] = {}
        if plan:
            for kpi in plan.kpis:
                name = kpi.get("name", "")
                if "threshold" in kpi and kpi["threshold"] is not None:
                    kpi_thresholds[name] = float(kpi["threshold"])
                if "target" in kpi and kpi["target"] is not None:
                    kpi_targets[name] = float(kpi["target"])

        raw = self._observations.get(plan_id, [])
        filtered = [
            o for o in raw
            if (not o.timestamp or period_start <= o.timestamp.split("T")[0] <= period_end or period_start <= o.timestamp.split(" ")[0] <= period_end)
        ]

        metrics: dict[str, list[PMMObservation]] = {}
        for obs in filtered:
            metrics.setdefault(obs.metric, []).append(obs)

        metric_trends: dict[str, dict[str, float]] = {}
        thresholds_breached: set[str] = set()
        incident_correlation: list[dict[str, Any]] = []

        for metric_name, observations in metrics.items():
            values = [o.value for o in observations]
            n = len(values)
            if n == 0:
                continue
            mean_val = sum(values) / n
            min_val = min(values)
            max_val = max(values)
            if n > 1:
                variance = sum((v - mean_val) ** 2 for v in values) / n
                std_val = math.sqrt(variance)
            else:
                std_val = 0.0
            slope = _compute_slope(values)

            metric_trends[metric_name] = {
                "mean": mean_val,
                "std": std_val,
                "min": min_val,
                "max": max_val,
                "slope": slope,
            }

            effective_threshold = kpi_thresholds.get(metric_name)
            effective_target = kpi_targets.get(metric_name)
            for obs in observations:
                t = obs.threshold if obs.threshold is not None else effective_threshold
                if t is not None and self._is_threshold_breach(obs.value, t, effective_target):
                    thresholds_breached.add(metric_name)
                if obs.threshold_breached:
                    thresholds_breached.add(metric_name)

            for obs in observations:
                if "incident" in obs.details.lower() or "INC-" in obs.details:
                    incident_correlation.append({
                        "metric": metric_name,
                        "observation_id": obs.obs_id,
                        "details": obs.details,
                    })

        breached_list = sorted(thresholds_breached)

        if breached_list:
            overall_assessment = "critical"
        elif any(
            t.get("slope", 0) < -0.01
            for t in metric_trends.values()
        ):
            overall_assessment = "degrading"
        else:
            overall_assessment = "stable"

        return PMMTrendAnalysis(
            period_start=period_start,
            period_end=period_end,
            metric_trends=metric_trends,
            thresholds_breached=breached_list,
            incident_correlation=incident_correlation,
            overall_assessment=overall_assessment,
        )

    def generate_periodic_report(
        self,
        plan_id: str,
        period_start: str,
        period_end: str,
    ) -> PeriodicReport:
        """Generate a periodic post-market monitoring report.

        Aggregates observations in the period, runs trend analysis,
        extracts incident references, and produces recommendations.

        Args:
            plan_id: The monitoring plan ID.
            period_start: ISO date string for period start.
            period_end: ISO date string for period end.

        Returns:
            PeriodicReport with trend analysis and recommendations.
        """
        trend = self.run_trend_analysis(plan_id, period_start, period_end)

        raw = self._observations.get(plan_id, [])
        filtered = [
            o for o in raw
            if (not o.timestamp or period_start <= o.timestamp.split("T")[0] <= period_end or period_start <= o.timestamp.split(" ")[0] <= period_end)
        ]

        observation_count = len(filtered)

        incidents: list[str] = []
        recommendations: list[str] = []
        for obs in filtered:
            if "incident" in obs.details.lower() or "INC-" in obs.details:
                incidents.append(obs.details)
                recommendations.append(
                    f"Investigate {obs.details} — {obs.metric} recorded {obs.value} from {obs.source}"
                )

        if trend.overall_assessment == "critical":
            recommendations.append(
                f"Critical assessment: thresholds breached for {', '.join(trend.thresholds_breached)}. "
                "Immediate corrective action required."
            )
        elif trend.overall_assessment == "degrading":
            recommendations.append(
                "Degrading trend detected. Schedule increased monitoring frequency."
            )

        report = PeriodicReport(
            report_id=f"rpt-{uuid4().hex[:8]}",
            plan_id=plan_id,
            period_start=period_start,
            period_end=period_end,
            observation_count=observation_count,
            trend_analysis=trend,
            incidents_in_period=list(set(incidents)),
            recommendations=recommendations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        if plan_id in self._reports:
            self._reports[plan_id].append(report)

        return report

    def check_review_due(self, plan_id: str) -> bool:
        """Check if a plan's review is due.

        Checks next_review_at first, then falls back to computing from
        last_review_at + review_interval_days.

        Args:
            plan_id: The monitoring plan ID.

        Returns:
            True if the review is due or overdue.
        """
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        now = datetime.now(timezone.utc)

        if plan.next_review_at:
            try:
                next_review = datetime.fromisoformat(plan.next_review_at)
                if next_review.tzinfo is None:
                    next_review = next_review.replace(tzinfo=timezone.utc)
                return now >= next_review
            except (ValueError, TypeError):
                pass

        if plan.last_review_at:
            try:
                last_review = datetime.fromisoformat(plan.last_review_at)
                if last_review.tzinfo is None:
                    last_review = last_review.replace(tzinfo=timezone.utc)
                due_date = last_review + timedelta(days=plan.review_interval_days)
                return now >= due_date
            except (ValueError, TypeError):
                pass

        return False

    def get_pmm_summary(self) -> dict[str, Any]:
        """Get a summary of all monitoring plans and observations.

        Returns:
            Dictionary with total_plans, total_observations, and
            list of plan summaries.
        """
        total_observations = sum(len(obs) for obs in self._observations.values())
        plans = []
        for pid, plan in self._plans.items():
            obs_count = len(self._observations.get(pid, []))
            plans.append({
                "plan_id": pid,
                "system_name": plan.system_name,
                "system_version": plan.system_version,
                "observation_count": obs_count,
                "kpi_count": len(plan.kpis),
            })
        return {
            "total_plans": len(self._plans),
            "total_observations": total_observations,
            "plans": plans,
        }
