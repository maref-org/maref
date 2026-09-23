"""Bottleneck channel diagnosis for the evolution loop.

Implements a DIANOIA-style three-channel decomposition of multi-agent
reasoning gain: coverage (breadth of proposed candidates), fidelity
(correctness of execution), and synthesis (convergence of iteration).

The diagnoser is a pure, side-effect-free component: it reads evolution
results, scores each channel, and reports the bottleneck. Budget
adjustments are returned as advisory allocations that callers may apply
or merely record — the diagnoser never mutates wallets or budgets itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, pstdev
from typing import Any

_BALANCED_THRESHOLD = 0.65


class BottleneckChannel(str, Enum):
    COVERAGE = "coverage"
    FIDELITY = "fidelity"
    SYNTHESIS = "synthesis"


@dataclass
class ChannelScore:
    channel: BottleneckChannel
    score: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class BottleneckDiagnosis:
    bottleneck: BottleneckChannel | None
    scores: list[ChannelScore]
    rationale: str
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bottleneck": self.bottleneck.value if self.bottleneck else None,
            "scores": {s.channel.value: round(s.score, 3) for s in self.scores},
            "rationale": self.rationale,
            "trace_id": self.trace_id,
        }


@dataclass
class BudgetAllocation:
    channel: BottleneckChannel | None
    sample_multiplier: float
    verify_rounds: int
    synthesis_iterations: int
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value if self.channel else None,
            "sample_multiplier": self.sample_multiplier,
            "verify_rounds": self.verify_rounds,
            "synthesis_iterations": self.synthesis_iterations,
            "rationale": self.rationale,
        }


def _as_ratio(value: Any, default: float) -> float:
    """Normalize a metric to [0, 1]; percent values (> 1) are scaled by 1/100."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v > 1.0:
        v /= 100.0
    return max(0.0, min(1.0, v))


def _extract_metrics(item: Any) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        metrics = item.get("metrics")
        if isinstance(metrics, Mapping):
            return metrics
        return item
    metrics = getattr(item, "metrics", None)
    if isinstance(metrics, Mapping):
        return metrics
    return {}


def _coverage_scores(metrics_seq: Sequence[Mapping[str, Any]]) -> list[float]:
    return [_as_ratio(m.get("coverage"), 0.0) for m in metrics_seq]


def _fidelity_scores(metrics_seq: Sequence[Mapping[str, Any]]) -> list[float]:
    scores: list[float] = []
    for m in metrics_seq:
        fnr = _as_ratio(m.get("fnr"), 0.0)
        pass_rate = _as_ratio(m.get("test_pass_rate"), 0.0)
        scores.append(0.5 * (1.0 - fnr) + 0.5 * pass_rate)
    return scores


def _synthesis_score(series: Sequence[float]) -> float:
    """Convergence score = 1 - coefficient of variation over the series."""
    if len(series) < 2:
        return 0.5
    series_mean = mean(series)
    if series_mean <= 0.0:
        return 0.5
    cv = pstdev(series) / series_mean
    return max(0.0, min(1.0, 1.0 - cv))


def _score_channel(
    channel: BottleneckChannel, series: Sequence[float]
) -> ChannelScore:
    if not series:
        return ChannelScore(channel, 0.5, ["no data"])
    return ChannelScore(channel, round(mean(series), 3), [f"mean={mean(series):.3f} n={len(series)}"])


def diagnose(
    results: Sequence[Any],
    balanced_threshold: float = _BALANCED_THRESHOLD,
    trace_id: str = "",
) -> BottleneckDiagnosis:
    """Diagnose the bottleneck channel across a sequence of evolution results."""
    if not results:
        return BottleneckDiagnosis(None, [], "no evolution results available", trace_id)

    metrics_seq = [_extract_metrics(r) for r in results]
    coverage = _coverage_scores(metrics_seq)
    fidelity = _fidelity_scores(metrics_seq)

    scores = [
        _score_channel(BottleneckChannel.COVERAGE, coverage),
        _score_channel(BottleneckChannel.FIDELITY, fidelity),
    ]

    synthesis_base = coverage or fidelity
    synthesis_score = _synthesis_score(synthesis_base)
    synthesis_evidence = (
        ["cv=%.3f" % (pstdev(synthesis_base) / mean(synthesis_base))]
        if len(synthesis_base) >= 2 and mean(synthesis_base) > 0
        else ["stable/insufficient data"]
    )
    scores.append(ChannelScore(BottleneckChannel.SYNTHESIS, round(synthesis_score, 3), synthesis_evidence))

    min_score = min(scores, key=lambda s: s.score)
    if min_score.score >= balanced_threshold:
        return BottleneckDiagnosis(
            None,
            scores,
            f"all channels at or above {balanced_threshold}: balanced",
            trace_id,
        )
    return BottleneckDiagnosis(
        min_score.channel,
        scores,
        f"lowest channel {min_score.channel.value} ({min_score.score}) below {balanced_threshold}",
        trace_id,
    )


def allocate_for_channel(channel: BottleneckChannel | None) -> BudgetAllocation:
    """Advisory budget allocation for a diagnosed bottleneck channel."""
    if channel is BottleneckChannel.COVERAGE:
        return BudgetAllocation(channel, 2.0, 1, 1, "broaden proposer sampling")
    if channel is BottleneckChannel.FIDELITY:
        return BudgetAllocation(channel, 1.0, 2, 1, "deepen verification rounds")
    if channel is BottleneckChannel.SYNTHESIS:
        return BudgetAllocation(channel, 1.0, 1, 2, "raise synthesis iterations")
    return BudgetAllocation(None, 1.0, 1, 1, "balanced baseline")
