"""IterationAnalyzer — trend analysis and next-iteration planning based on EvolutionVault history."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from maref.evolution.vault import EvolutionSnapshot, EvolutionVault, TrendDirection, TrendResult


class RecommendationType(Enum):
    REPAIR = "repair"       # Degradation detected → fix it
    AMPLIFY = "amplify"     # Improvement detected → amplify it
    RESEARCH = "research"   # PERCV finding → investigate
    MAINTAIN = "maintain"   # Stable → keep monitoring
    INVESTIGATE = "investigate"  # Anomaly → investigate root cause


@dataclass
class IterationRecommendation:
    recommendation_id: str
    rec_type: RecommendationType
    priority: int  # 1=urgent, 2=high, 3=medium, 4=low
    title: str
    description: str
    target_metric: str
    current_value: float
    target_value: float
    evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.recommendation_id,
            "type": self.rec_type.value,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "target_metric": self.target_metric,
            "current_value": round(self.current_value, 4),
            "target_value": round(self.target_value, 4),
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


@dataclass
class IterationPlan:
    """Complete iteration plan for the next evolution cycle."""
    plan_id: str
    generated_at: float
    analysis_window: int
    recommendations: list[IterationRecommendation] = field(default_factory=list)
    overall_health: str = "unknown"  # healthy/degraded/critical
    key_metrics_summary: dict[str, Any] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "generated_at": self.generated_at,
            "analysis_window": self.analysis_window,
            "overall_health": self.overall_health,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "key_metrics_summary": self.key_metrics_summary,
            "anomalies": self.anomalies,
        }

    def save(self, path: str | Path) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        return str(p)


class IterationAnalyzer:
    """Analyzes EvolutionVault history to generate next-iteration plans.

    Reads recent snapshots, identifies:
    - Degraded metrics → triggers REPAIR recommendations
    - Improving metrics → triggers AMPLIFY recommendations
    - Stable metrics → triggers MAINTAIN recommendations
    - Anomalies → triggers INVESTIGATE recommendations

    Outputs an IterationPlan with prioritized recommendations.
    """

    # Metric thresholds for health assessment
    FNR_CRITICAL = 0.30
    FNR_WARNING = 0.15
    FPR_CRITICAL = 0.20
    FPR_WARNING = 0.10

    # Minimum data points for meaningful analysis
    MIN_SNAPSHOTS = 3

    def __init__(self, vault: EvolutionVault | None = None, vault_dir: str | None = None) -> None:
        self._vault = vault or EvolutionVault(vault_dir=vault_dir)

    def analyze(self, window: int = 7) -> IterationPlan:
        """Analyze recent evolution history and generate iteration plan."""
        import uuid
        history = self._vault.load_history(last_n=window)

        if len(history) < self.MIN_SNAPSHOTS:
            return self._insufficient_data_plan(window, len(history))

        recommendations: list[IterationRecommendation] = []
        anomalies: list[str] = []

        # Analyze key metrics
        fnr_trend = self._vault.get_trend("fnr", window=window)
        fpr_trend = self._vault.get_trend("fpr", window=window)
        entropy_trend = self._vault.get_trend("entropy", window=window)

        # FNR analysis
        recommendations.extend(self._analyze_metric(
            "fnr", fnr_trend, history,
            critical_threshold=self.FNR_CRITICAL,
            warning_threshold=self.FNR_WARNING,
            target=0.05,  # target: < 5% FNR
        ))

        # FPR analysis
        recommendations.extend(self._analyze_metric(
            "fpr", fpr_trend, history,
            critical_threshold=self.FPR_CRITICAL,
            warning_threshold=self.FPR_WARNING,
            target=0.05,
        ))

        # Entropy analysis
        if entropy_trend.direction != TrendDirection.INSUFFICIENT_DATA:
            recommendations.extend(self._analyze_entropy(entropy_trend, history))

        # Anomaly detection
        for snap in history:
            if snap.fnr > self.FNR_CRITICAL:
                anomalies.append(f"Round {snap.round_num}: FNR={snap.fnr:.3f} exceeds critical threshold")
            if snap.fpr > self.FPR_CRITICAL:
                anomalies.append(f"Round {snap.round_num}: FPR={snap.fpr:.3f} exceeds critical threshold")

        # Overall health assessment
        health = self._assess_health(history, fnr_trend, fpr_trend)

        # Key metrics summary
        fnr_values = [s.fnr for s in history]
        fpr_values = [s.fpr for s in history]
        key_metrics = {
            "fnr": {
                "mean": sum(fnr_values) / len(fnr_values),
                "min": min(fnr_values),
                "max": max(fnr_values),
                "trend": fnr_trend.direction.value,
            },
            "fpr": {
                "mean": sum(fpr_values) / len(fpr_values),
                "min": min(fpr_values),
                "max": max(fpr_values),
                "trend": fpr_trend.direction.value,
            },
            "snapshot_count": len(history),
            "cycles": sorted({s.cycle_id for s in history}),
        }

        # Sort recommendations by priority
        recommendations.sort(key=lambda r: r.priority)

        return IterationPlan(
            plan_id=str(uuid.uuid4())[:8],
            generated_at=time.time(),
            analysis_window=window,
            recommendations=recommendations,
            overall_health=health,
            key_metrics_summary=key_metrics,
            anomalies=anomalies,
        )

    def _analyze_metric(
        self,
        metric_name: str,
        trend: TrendResult,
        history: list[EvolutionSnapshot],
        critical_threshold: float,
        warning_threshold: float,
        target: float,
    ) -> list[IterationRecommendation]:
        """Analyze a single metric and generate recommendations."""
        import uuid
        recs: list[IterationRecommendation] = []
        latest_value = getattr(history[-1], metric_name, 0.0) or 0.0

        if trend.direction == TrendDirection.RISING and metric_name in ("fnr", "fpr"):
            # Rising error rate → repair
            if latest_value > critical_threshold:
                recs.append(IterationRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    rec_type=RecommendationType.REPAIR,
                    priority=1,
                    title=f"URGENT: {metric_name.upper()} degradation detected",
                    description=f"{metric_name.upper()} is rising ({latest_value:.3f}) and exceeds critical threshold ({critical_threshold}). Immediate investigation and fix required.",
                    target_metric=metric_name,
                    current_value=latest_value,
                    target_value=target,
                    evidence=f"Trend slope: {trend.slope:.4f}, window mean: {trend.mean:.4f}",
                ))
            elif latest_value > warning_threshold:
                recs.append(IterationRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    rec_type=RecommendationType.REPAIR,
                    priority=2,
                    title=f"{metric_name.upper()} rising above warning level",
                    description=f"{metric_name.upper()} is rising ({latest_value:.3f}) above warning threshold ({warning_threshold}). Plan to investigate and fix.",
                    target_metric=metric_name,
                    current_value=latest_value,
                    target_value=target,
                    evidence=f"Trend slope: {trend.slope:.4f}",
                ))

        elif trend.direction == TrendDirection.FALLING and metric_name in ("fnr", "fpr"):
            # Falling error rate → amplify
            recs.append(IterationRecommendation(
                recommendation_id=str(uuid.uuid4())[:8],
                rec_type=RecommendationType.AMPLIFY,
                priority=3,
                title=f"{metric_name.upper()} improving — amplify",
                description=f"{metric_name.upper()} is improving ({latest_value:.3f}, slope {trend.slope:.4f}). Identify what's working and amplify it.",
                target_metric=metric_name,
                current_value=latest_value,
                target_value=target,
                evidence=f"Trend slope: {trend.slope:.4f}",
            ))

        elif trend.direction == TrendDirection.STABLE:
            if latest_value <= warning_threshold:
                recs.append(IterationRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    rec_type=RecommendationType.MAINTAIN,
                    priority=4,
                    title=f"{metric_name.upper()} stable and healthy",
                    description=f"{metric_name.upper()} is stable at {latest_value:.3f}. Continue monitoring.",
                    target_metric=metric_name,
                    current_value=latest_value,
                    target_value=target,
                    evidence=f"Mean: {trend.mean:.4f}, std: {trend.std:.4f}",
                ))
            else:
                recs.append(IterationRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    rec_type=RecommendationType.INVESTIGATE,
                    priority=2,
                    title=f"{metric_name.upper()} stable but elevated",
                    description=f"{metric_name.upper()} is stable but at elevated level ({latest_value:.3f}). Investigate root cause.",
                    target_metric=metric_name,
                    current_value=latest_value,
                    target_value=target,
                    evidence=f"Mean: {trend.mean:.4f}, std: {trend.std:.4f}",
                ))

        return recs

    def _analyze_entropy(
        self,
        trend: TrendResult,
        history: list[EvolutionSnapshot],
    ) -> list[IterationRecommendation]:
        """Analyze entropy trend for system stability."""
        import uuid
        recs: list[IterationRecommendation] = []
        latest = getattr(history[-1], "entropy", 0.0) or 0.0

        if trend.direction == TrendDirection.RISING:
            recs.append(IterationRecommendation(
                recommendation_id=str(uuid.uuid4())[:8],
                rec_type=RecommendationType.INVESTIGATE,
                priority=2,
                title="System entropy increasing",
                description=f"System entropy is rising ({latest:.2f}). This may indicate growing complexity or instability.",
                target_metric="entropy",
                current_value=latest,
                target_value=0.0,
                evidence=f"Trend slope: {trend.slope:.4f}",
            ))

        return recs

    def _assess_health(
        self,
        history: list[EvolutionSnapshot],
        fnr_trend: TrendResult,
        fpr_trend: TrendResult,
    ) -> str:
        """Assess overall system health based on metrics."""
        latest_fnr = history[-1].fnr
        latest_fpr = history[-1].fpr

        if latest_fnr > self.FNR_CRITICAL or latest_fpr > self.FPR_CRITICAL:
            return "critical"

        if latest_fnr > self.FNR_WARNING or latest_fpr > self.FPR_WARNING:
            return "degraded"

        if fnr_trend.direction == TrendDirection.RISING or fpr_trend.direction == TrendDirection.RISING:
            return "degraded"

        return "healthy"

    def _insufficient_data_plan(self, window: int, available: int) -> IterationPlan:
        """Generate a plan when insufficient data is available."""
        import uuid
        return IterationPlan(
            plan_id=str(uuid.uuid4())[:8],
            generated_at=time.time(),
            analysis_window=window,
            overall_health="unknown",
            key_metrics_summary={
                "status": "insufficient_data",
                "required": self.MIN_SNAPSHOTS,
                "available": available,
            },
            recommendations=[IterationRecommendation(
                recommendation_id=str(uuid.uuid4())[:8],
                rec_type=RecommendationType.MAINTAIN,
                priority=4,
                title="Insufficient data for trend analysis",
                description=f"Only {available} snapshots available, need at least {self.MIN_SNAPSHOTS}. Run more evolution rounds before next analysis.",
                target_metric="all",
                current_value=0.0,
                target_value=0.0,
            )],
        )
