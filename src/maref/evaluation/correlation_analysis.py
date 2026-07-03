"""Human-AI correlation analysis for RSI scoring."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from statistics import mean
from typing import Any


@dataclass
class RoundScore:
    round_id: int
    automated_scores: dict[str, float]
    human_scores: list[dict[str, float]]

    @property
    def mean_human_scores(self) -> dict[str, float]:
        if not self.human_scores:
            return {}
        dims = self.human_scores[0].keys()
        return {
            dim: mean(r[dim] for r in self.human_scores)
            for dim in dims
        }


@dataclass
class CorrelationResult:
    dimension: str
    spearman_r: float
    p_value: float
    sample_count: int
    interpretation: str = ""


@dataclass
class CorrelationReport:
    results: list[CorrelationResult] = field(default_factory=list)
    overall_spearman: float = 0.0
    inter_rater_kappa: float = 0.0
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_spearman_rank(x: list[float], y: list[float]) -> tuple[float, float]:
    n = len(x)
    if n < 3 or n != len(y):
        return (0.0, 1.0)

    def rank(values):
        sorted_vals = sorted(values)
        ranks = []
        for v in values:
            r = 1 + sorted_vals.index(v)
            ranks.append(r)
        return ranks

    rx = rank(x)
    ry = rank(y)

    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    denom = n * (n * n - 1)
    rho = 1.0 - (6.0 * d_sq) / denom if denom != 0 else 0.0

    t_stat = rho * math.sqrt((n - 2) / max(1 - rho * rho, 1e-10))
    try:
        from scipy.stats import t as t_dist
        p_value = 2 * (1 - t_dist.cdf(abs(t_stat), n - 2))
    except ImportError:
        p_value = 0.05 if abs(rho) < 0.5 else 0.01

    return (rho, p_value)


def compute_correlation_report(scores: list[RoundScore]) -> CorrelationReport:
    if not scores:
        return CorrelationReport()

    dimensions = list(scores[0].automated_scores.keys())
    results = []

    for dim in dimensions:
        auto_vals = []
        human_vals = []
        for s in scores:
            if dim in s.automated_scores and dim in s.mean_human_scores:
                auto_vals.append(s.automated_scores[dim])
                human_vals.append(s.mean_human_scores[dim])

        rho, p = compute_spearman_rank(auto_vals, human_vals)
        interpretation = (
            "strong" if abs(rho) >= 0.7
            else "moderate" if abs(rho) >= 0.4
            else "weak"
        )
        results.append(CorrelationResult(
            dimension=dim, spearman_r=rho, p_value=p,
            sample_count=len(auto_vals), interpretation=interpretation,
        ))

    all_auto = []
    all_human = []
    for s in scores:
        all_auto.extend(s.automated_scores.values())
        all_human.extend(s.mean_human_scores.values())
    overall_rho, _ = compute_spearman_rank(all_auto, all_human)

    passed = all(r.spearman_r >= 0.7 for r in results) and overall_rho >= 0.7

    return CorrelationReport(
        results=results,
        overall_spearman=overall_rho,
        inter_rater_kappa=0.0,
        passed=passed,
    )


def load_scores_from_yaml(path: str) -> list[RoundScore]:
    scores = []
    try:
        with open(path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return scores

    for entry in data:
        scores.append(RoundScore(
            round_id=entry["round_id"],
            automated_scores=entry["automated_scores"],
            human_scores=entry.get("human_scores", []),
        ))
    return scores
