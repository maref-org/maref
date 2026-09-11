from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class TelemetryBatch:
    deployment_id: str
    telemetry_version: str
    batch_id: str
    exported_at: float
    total_entries: int
    window_hours: float
    fnr: float
    fpr: float
    avg_entropy: float
    state_transition_count: int
    cb_trip_count: int
    anomaly_count: int
    event_type_dist: dict[str, int]
    action_dist: dict[str, int]
    signed_ratio: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalMetrics:
    deployments: int
    total_events: int
    time_window_hours: float
    global_fnr: float
    global_fpr: float
    global_avg_entropy: float
    fnr_trend: Literal["improving", "stable", "degrading"] = "stable"
    fpr_trend: Literal["improving", "stable", "degrading"] = "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployments": self.deployments,
            "total_events": self.total_events,
            "time_window_hours": self.time_window_hours,
            "global_fnr": round(self.global_fnr, 4),
            "global_fpr": round(self.global_fpr, 4),
            "global_avg_entropy": round(self.global_avg_entropy, 4),
            "fnr_trend": self.fnr_trend,
            "fpr_trend": self.fpr_trend,
        }


@dataclass
class PolicyRecommendation:
    version: str
    safety_gate_defaults: dict[str, Any] = field(default_factory=dict)
    circuit_breaker_defaults: dict[str, Any] = field(default_factory=dict)
    trigram_weights: dict[str, float] = field(default_factory=dict)


class TelemetryAggregator:
    def __init__(self, history_size: int = 100):
        self._batches: list[TelemetryBatch] = []
        self._history_size = history_size
        self._fnr_history: list[float] = []
        self._fpr_history: list[float] = []

    def ingest(self, data: dict[str, Any]) -> TelemetryBatch:
        agg = data.get("aggregate", {})
        batch = TelemetryBatch(
            deployment_id=data.get("deployment_id", "unknown"),
            telemetry_version=data.get("telemetry_version", "1.0"),
            batch_id=data.get("batch_id", ""),
            exported_at=agg.get("exported_at", 0.0),
            total_entries=agg.get("total_entries", 0),
            window_hours=agg.get("window_hours", 0.0),
            fnr=agg.get("fnr", 0.0),
            fpr=agg.get("fpr", 0.0),
            avg_entropy=agg.get("avg_entropy", 0.0),
            state_transition_count=agg.get("state_transition_count", 0),
            cb_trip_count=agg.get("cb_trip_count", 0),
            anomaly_count=agg.get("anomaly_count", 0),
            event_type_dist=agg.get("event_type_dist", {}),
            action_dist=agg.get("action_dist", {}),
            signed_ratio=agg.get("signed_ratio", 0.0),
            raw=data,
        )
        self._batches.append(batch)
        self._fnr_history.append(batch.fnr)
        self._fpr_history.append(batch.fpr)
        while len(self._batches) > self._history_size:
            self._batches.pop(0)
            self._fnr_history.pop(0)
            self._fpr_history.pop(0)
        return batch

    def ingest_from_file(self, path: Path) -> list[TelemetryBatch]:
        batches: list[TelemetryBatch] = []
        if not path.exists():
            return batches
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    batches.append(self.ingest(data))
                except (json.JSONDecodeError, KeyError):
                    continue
        return batches

    def recompute_globals(self) -> GlobalMetrics:
        if not self._batches:
            return GlobalMetrics(
                deployments=0,
                total_events=0,
                time_window_hours=0.0,
                global_fnr=0.0,
                global_fpr=0.0,
                global_avg_entropy=0.0,
            )

        deployments = len({b.deployment_id for b in self._batches})
        total_events = sum(b.total_entries for b in self._batches)
        max_window = max(b.window_hours for b in self._batches)

        weighted_fnr = sum(b.fnr * b.total_entries for b in self._batches) / max(total_events, 1)
        weighted_fpr = sum(b.fpr * b.total_entries for b in self._batches) / max(total_events, 1)
        weighted_entropy = sum(b.avg_entropy * b.total_entries for b in self._batches) / max(
            total_events, 1
        )

        fnr_trend = self._compute_trend(self._fnr_history)
        fpr_trend = self._compute_trend(self._fpr_history)

        return GlobalMetrics(
            deployments=deployments,
            total_events=total_events,
            time_window_hours=max_window,
            global_fnr=weighted_fnr,
            global_fpr=weighted_fpr,
            global_avg_entropy=weighted_entropy,
            fnr_trend=fnr_trend,
            fpr_trend=fpr_trend,
        )

    @staticmethod
    def _compute_trend(
        history: list[float], window: int = 5
    ) -> Literal["improving", "stable", "degrading"]:
        if len(history) < window:
            return "stable"
        recent = history[-window:]
        slope = (recent[-1] - recent[0]) / max(len(recent), 1)
        if slope < -0.01:
            return "improving"
        elif slope > 0.01:
            return "degrading"
        return "stable"

    def compute_reward(self) -> float:
        metrics = self.recompute_globals()
        reward = 1.0 - (metrics.global_fnr * 2.0 + metrics.global_fpr)
        return max(0.0, min(1.0, reward))

    def to_evolution_metrics(self) -> dict[str, float]:
        metrics = self.recompute_globals()
        return {
            "fnr": metrics.global_fnr,
            "fpr": metrics.global_fpr,
            "avg_entropy": metrics.global_avg_entropy,
            "reward": self.compute_reward(),
            "deployment_count": float(metrics.deployments),
            "total_events": float(metrics.total_events),
        }

    def recommend_policy(self) -> PolicyRecommendation:
        metrics = self.recompute_globals()
        rec = PolicyRecommendation(version=f"v{int(time.time())}")

        if metrics.global_fnr > 0.15:
            rec.safety_gate_defaults["min_test_pass_rate"] = 0.95
            rec.circuit_breaker_defaults["max_consecutive_failures"] = 3
        elif metrics.global_fnr > 0.10:
            rec.safety_gate_defaults["min_test_pass_rate"] = 0.90
            rec.circuit_breaker_defaults["max_consecutive_failures"] = 5
        else:
            rec.safety_gate_defaults["min_test_pass_rate"] = 0.85
            rec.circuit_breaker_defaults["max_consecutive_failures"] = 7

        if metrics.global_fpr > 0.10:
            rec.trigram_weights = {"kun": 0.6, "zhen": 0.4, "kan": 0.3}
        else:
            rec.trigram_weights = {"qian": 1.0, "li": 0.5, "dui": 0.3}

        return rec
