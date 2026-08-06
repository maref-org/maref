from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.integration.feature_dev.feature_cycle import CycleSnapshot


@dataclass
class LayerTrend:
    layer_name: str
    scores: list[float]
    direction: str
    current_gap: float

    @property
    def slope(self) -> float:
        if len(self.scores) < 2:
            return 0.0
        return self.scores[-1] - self.scores[-2]

    @property
    def is_on_track(self) -> bool:
        if not self.scores:
            return False
        return self.scores[-1] >= 60.0 and (len(self.scores) < 2 or self.slope >= -2.0)

    @property
    def convergence_ratio(self) -> float:
        if len(self.scores) < 3:
            return 1.0
        mid = len(self.scores) // 2
        first = sum(self.scores[:mid]) / max(mid, 1)
        second = sum(self.scores[mid:]) / max(len(self.scores) - mid, 1)
        return second / first if first > 0 else 1.0


@dataclass
class ConvergenceReport:
    feature_name: str
    total_cycles: int
    total_duration_seconds: float
    overall_trend: str
    layer_trends: list[LayerTrend]
    deploy_ready: bool
    deploy_gates: dict[str, bool]
    recommendations: list[str]
    cycle_scores: list[float] = field(default_factory=list)
    final_decision: str = ""
    budget_spent: float = 0.0
    content_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def avg_score(self) -> float:
        latest = [t.scores[-1] for t in self.layer_trends if t.scores]
        return sum(latest) / len(latest) if latest else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "total_cycles": self.total_cycles,
            "total_duration_seconds": round(self.total_duration_seconds, 1),
            "overall_trend": self.overall_trend,
            "layer_trends": [
                {
                    "layer_name": t.layer_name,
                    "scores": t.scores,
                    "direction": t.direction,
                    "slope": round(t.slope, 1),
                    "current_gap": round(t.current_gap, 1),
                    "is_on_track": t.is_on_track,
                }
                for t in self.layer_trends
            ],
            "deploy_ready": self.deploy_ready,
            "deploy_gates": self.deploy_gates,
            "recommendations": self.recommendations,
            "avg_score": round(self.avg_score, 1),
            "cycle_scores": [round(s, 1) for s in self.cycle_scores],
            "final_decision": self.final_decision,
            "budget_spent": round(self.budget_spent, 2),
            "content_stats": self.content_stats,
        }


def _direction(scores: list[float]) -> str:
    if len(scores) < 2:
        return "insufficient_data"
    diffs = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
    pos = sum(1 for d in diffs if d >= 0)
    neg = sum(1 for d in diffs if d < 0)
    if pos >= len(diffs) * 0.8:
        return "converging"
    if neg >= len(diffs) * 0.8:
        return "diverging"
    return "fluctuating"


_RECS: dict[str, list[str]] = {
    "Static Audit": [
        "Add more characters",
        "Increase script count",
        "Cover more deployment stages",
    ],
    "Reasoning Metrics": [
        "Deepen character backstories",
        "Add more episodes per character",
        "Reference document hypotheses in content",
    ],
    "Action Metrics": [
        "Produce more total content",
        "Add scene variety",
        "Increase total duration",
    ],
    "E2E Metrics": ["Complete export pipeline", "Cover all document stages in content"],
    "MAS Dimensions": [
        "Add characters with distinct archetypes",
        "Create crossover episodes",
        "Diversify style palettes",
    ],
}


class ProgressTracker:
    def __init__(self, feature_name: str) -> None:
        self.feature_name = feature_name
        self.snapshots: list[CycleSnapshot] = []

    def add_snapshot(self, snap: CycleSnapshot) -> None:
        self.snapshots.append(snap)

    def generate_report(self) -> ConvergenceReport:
        names = list(self.snapshots[-1].layer_scores.keys()) if self.snapshots else []
        lmap = {n: [] for n in names}
        for snap in self.snapshots:
            for n in names:
                lmap[n].append(snap.layer_scores.get(n, 0.0))

        trends = [
            LayerTrend(
                layer_name=n,
                scores=s,
                direction=_direction(s),
                current_gap=max(0.0, 80.0 - (s[-1] if s else 0.0)),
            )
            for n, s in lmap.items()
        ]

        all_scores = [s.overall_score for s in self.snapshots]
        ot = _direction(all_scores)
        last = self.snapshots[-1].overall_score if self.snapshots else 0.0

        gates = {
            "overall_score >= 80": last >= 80.0,
            "all_layers_on_track": all(t.is_on_track for t in trends),
            "no_diverging_trends": not any(t.direction == "diverging" for t in trends),
        }
        all_pass = all(gates.values())

        recs = []
        if not all_pass:
            recs.append("Deploy blocked. Focus on low-scoring layers.")
        for t in trends:
            if t.current_gap > 10:
                for r in _RECS.get(t.layer_name, []):
                    if f"[{t.layer_name}] {r}" not in recs:
                        recs.append(f"[{t.layer_name}] {r}")
        if not recs:
            recs.append("All gates pass. Feature is deploy-ready.")

        final_decision = self.snapshots[-1].go_nogo_decision if self.snapshots else ""
        budget = sum(s.budget_used for s in self.snapshots)
        last_art = self.snapshots[-1].artifacts if self.snapshots else {}
        chars = len(last_art.get("characters", []))
        scripts = len(last_art.get("scripts", []))
        stages = list(last_art.get("stages_covered", set()))
        reqs = last_art.get("requirements_covered", 0)

        return ConvergenceReport(
            feature_name=self.feature_name,
            total_cycles=len(self.snapshots),
            total_duration_seconds=sum(s.duration_seconds for s in self.snapshots),
            overall_trend=ot,
            layer_trends=trends,
            deploy_ready=all_pass,
            deploy_gates=gates,
            recommendations=recs,
            cycle_scores=all_scores,
            final_decision=final_decision,
            budget_spent=budget,
            content_stats={
                "characters": chars,
                "scripts": scripts,
                "stages_covered": stages,
                "reqs_covered": reqs,
            },
        )
