"""Cross-Impact Circuit Breaker — protects against cross-dimensional degradation.

Monitors correlations between improvement dimensions. When improving
dimension A consistently degrades dimension B beyond threshold, this
breaker trips to prevent cascading quality loss.

Integrates with SafetyGateV2 for audit logging and existing CircuitBreaker
for state management.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CrossImpactState(Enum):
    MONITORING = "monitoring"
    ALERTED = "alerted"
    TRIPPED = "tripped"
    RECOVERING = "recovering"


@dataclass
class CrossImpactEvent:
    """Record of a cross-impact detection or trip."""

    timestamp: float
    source_dim: str
    target_dim: str
    correlation: float
    severity: str
    event_type: str
    detail: str


@dataclass
class DimensionHealth:
    """Health snapshot for a single dimension."""

    dim: str
    current_score: float
    trend: str
    variance: float
    correlated_negatives: list[tuple[str, float]] = field(default_factory=list)


class CrossImpactCircuitBreaker:
    """
    Circuit breaker for cross-dimensional improvement conflicts.

    Monitors dimension correlations across RSI experiment history.
    When improving one dimension consistently degrades another:
    1. First occurrence: ALERT (log warning, continue)
    2. Persistent pattern: TRIP (pause source dimension improvement)
    3. Recovery: After cooldown, attempt probe improvement

    Configuration:
    - negative_threshold: correlation below this triggers alert (default: -0.3)
    - trip_threshold: correlation below this triggers trip (default: -0.7)
    - alert_window: consecutive alerts before trip (default: 3)
    - cooldown_seconds: time before auto-recovery (default: 60.0)
    - max_tripped_dims: max dimensions that can be tripped simultaneously (default: 2)
    """

    def __init__(
        self,
        negative_threshold: float = -0.3,
        trip_threshold: float = -0.7,
        alert_window: int = 3,
        cooldown_seconds: float = 60.0,
        max_tripped_dims: int = 2,
    ) -> None:
        self._negative_threshold = negative_threshold
        self._trip_threshold = trip_threshold
        self._alert_window = alert_window
        self._cooldown_seconds = cooldown_seconds
        self._max_tripped_dims = max_tripped_dims
        self._state = CrossImpactState.MONITORING
        self._alert_counts: dict[tuple[str, str], int] = {}
        self._tripped_dims: dict[str, float] = {}
        self._events: list[CrossImpactEvent] = []
        self._last_trip_time: float = 0.0
        self._max_events = 500

    @property
    def state(self) -> CrossImpactState:
        return self._state

    @state.setter
    def state(self, value: CrossImpactState) -> None:
        self._state = value

    @property
    def tripped_dimensions(self) -> list[str]:
        return list(self._tripped_dims.keys())

    def _pearson(self, xs: list[float], ys: list[float]) -> float:
        """Compute Pearson correlation coefficient between two lists."""
        n = len(xs)
        if n < 2:
            return 0.0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        den_x = math.sqrt(sum((xs[i] - mean_x) ** 2 for i in range(n)))
        den_y = math.sqrt(sum((ys[i] - mean_y) ** 2 for i in range(n)))
        den = den_x * den_y
        if den == 0.0:
            return 0.0
        r = num / den
        return max(-1.0, min(1.0, r))

    def _compute_trend(self, scores: list[float]) -> str:
        if len(scores) < 2:
            return "stable"
        recent = scores[-3:] if len(scores) >= 3 else scores
        if len(recent) < 2:
            return "stable"
        slope = recent[-1] - recent[0]
        if slope > 0.05:
            return "improving"
        if slope < -0.05:
            return "worsening"
        return "stable"

    def _compute_variance(self, scores: list[float]) -> float:
        n = len(scores)
        if n < 2:
            return 0.0
        mean = sum(scores) / n
        return sum((s - mean) ** 2 for s in scores) / n

    def _trim_events(self) -> None:
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def analyze(self, dimension_scores: list[dict[str, float]]) -> list[CrossImpactEvent]:
        """Analyze dimension score history for cross-impact patterns.

        Args:
            dimension_scores: List of dicts {dim: score, ...} over time.

        Returns:
            List of CrossImpactEvent dicts (may be empty).

        Side effects:
            - If same negative pattern persists >= alert_window, state -> TRIPPED.
            - If state is TRIPPED and cooldown expired, state -> RECOVERING.
        """
        new_events: list[CrossImpactEvent] = []
        try:
            if not dimension_scores or len(dimension_scores) < 2:
                return new_events

            dims = list(dimension_scores[0].keys())
            if len(dims) < 2:
                return new_events
            return self._analyze_impl(dimension_scores, dims, new_events)
        except Exception:
            logger.exception("analyze() failed — returning partial results")
            return new_events

    def _analyze_impl(
        self,
        dimension_scores: list[dict[str, float]],
        dims: list[str],
        new_events: list[CrossImpactEvent],
    ) -> list[CrossImpactEvent]:

        if self._state == CrossImpactState.TRIPPED:
            expired = [
                dim
                for dim, trip_time in self._tripped_dims.items()
                if (time.time() - trip_time) >= self._cooldown_seconds
            ]
            for dim in expired:
                del self._tripped_dims[dim]
                event = CrossImpactEvent(
                    timestamp=time.time(),
                    source_dim=dim,
                    target_dim="",
                    correlation=0.0,
                    severity="INFO",
                    event_type="recovery",
                    detail="cooldown expired, dimension recovering",
                )
                self._events.append(event)
                new_events.append(event)

            if not self._tripped_dims:
                self._state = CrossImpactState.RECOVERING

        for i, source_dim in enumerate(dims):
            for j, target_dim in enumerate(dims):
                if i >= j:
                    continue

                xs = [d[source_dim] for d in dimension_scores]
                ys = [d[target_dim] for d in dimension_scores]

                correlation = self._pearson(xs, ys)

                if correlation < self._trip_threshold:
                    key = (source_dim, target_dim)
                    self._alert_counts[key] = self._alert_counts.get(key, 0) + 1
                    alert_count = self._alert_counts[key]

                    event = CrossImpactEvent(
                        timestamp=time.time(),
                        source_dim=source_dim,
                        target_dim=target_dim,
                        correlation=correlation,
                        severity="CRITICAL",
                        event_type="trip",
                        detail=f"correlation={correlation:.4f}, alerts={alert_count}",
                    )

                    if alert_count >= self._alert_window and source_dim not in self._tripped_dims:
                        if len(self._tripped_dims) < self._max_tripped_dims:
                            self._tripped_dims[source_dim] = time.time()
                            self._state = CrossImpactState.TRIPPED
                            self._last_trip_time = time.time()
                            event.event_type = "trip"
                        else:
                            event.event_type = "correlation_alert"
                            event.detail += " (max_tripped_dims reached, alert only)"
                            self._state = CrossImpactState.ALERTED
                    else:
                        event.event_type = "correlation_alert"
                        self._state = CrossImpactState.ALERTED

                    self._events.append(event)
                    new_events.append(event)

                elif correlation < self._negative_threshold:
                    key = (source_dim, target_dim)
                    self._alert_counts[key] = self._alert_counts.get(key, 0) + 1
                    alert_count = self._alert_counts[key]

                    if alert_count >= self._alert_window and source_dim not in self._tripped_dims:
                        if len(self._tripped_dims) < self._max_tripped_dims:
                            self._tripped_dims[source_dim] = time.time()
                            self._state = CrossImpactState.TRIPPED
                            self._last_trip_time = time.time()
                            event = CrossImpactEvent(
                                timestamp=time.time(),
                                source_dim=source_dim,
                                target_dim=target_dim,
                                correlation=correlation,
                                severity="HIGH",
                                event_type="trip",
                                detail=f"correlation={correlation:.4f}, alerts={alert_count}",
                            )
                            self._events.append(event)
                            new_events.append(event)
                        else:
                            event = CrossImpactEvent(
                                timestamp=time.time(),
                                source_dim=source_dim,
                                target_dim=target_dim,
                                correlation=correlation,
                                severity="HIGH",
                                event_type="correlation_alert",
                                detail=f"correlation={correlation:.4f}, alerts={alert_count} (max_tripped_dims reached)",
                            )
                            self._events.append(event)
                            new_events.append(event)
                    else:
                        self._state = CrossImpactState.ALERTED
                        event = CrossImpactEvent(
                            timestamp=time.time(),
                            source_dim=source_dim,
                            target_dim=target_dim,
                            correlation=correlation,
                            severity="WARNING",
                            event_type="correlation_alert",
                            detail=f"correlation={correlation:.4f}, alerts={alert_count}/{self._alert_window}",
                        )
                        self._events.append(event)
                        new_events.append(event)
                else:
                    key = (source_dim, target_dim)
                    if key in self._alert_counts:
                        self._alert_counts[key] = max(0, self._alert_counts[key] - 1)

        self._trim_events()
        return new_events

    def check_dimension(self, source_dim: str, target_dim: str, correlation: float) -> bool:
        """Check if improving source_dim is allowed given impact on target_dim.

        Returns True if allowed, False if blocked (tripped).
        """
        if source_dim in self._tripped_dims:
            return False

        if correlation < self._trip_threshold:
            key = (source_dim, target_dim)
            self._alert_counts[key] = self._alert_counts.get(key, 0) + 1
            if self._alert_counts[key] >= self._alert_window:
                if source_dim not in self._tripped_dims and len(self._tripped_dims) < self._max_tripped_dims:
                    self._tripped_dims[source_dim] = time.time()
                    self._state = CrossImpactState.TRIPPED
                    self._last_trip_time = time.time()
                return False
            return False

        if correlation < self._negative_threshold:
            key = (source_dim, target_dim)
            self._alert_counts[key] = self._alert_counts.get(key, 0) + 1
            if self._alert_counts[key] >= self._alert_window:
                if source_dim not in self._tripped_dims and len(self._tripped_dims) < self._max_tripped_dims:
                    self._tripped_dims[source_dim] = time.time()
                    self._state = CrossImpactState.TRIPPED
                    self._last_trip_time = time.time()
                return False

        return True

    def release_dimension(self, dim: str) -> bool:
        """Manually release a tripped dimension. Returns True if released."""
        if dim in self._tripped_dims:
            del self._tripped_dims[dim]
            event = CrossImpactEvent(
                timestamp=time.time(),
                source_dim=dim,
                target_dim="",
                correlation=0.0,
                severity="INFO",
                event_type="recovery",
                detail="manually released",
            )
            self._events.append(event)
            if not self._tripped_dims:
                self._state = CrossImpactState.RECOVERING
            return True
        return False

    def get_dimension_health(self, dimension_scores: list[dict[str, float]]) -> list[DimensionHealth]:
        """Get health report for all dimensions."""
        if not dimension_scores:
            return []

        dims = list(dimension_scores[0].keys())
        health_reports: list[DimensionHealth] = []

        for dim in dims:
            scores = [d[dim] for d in dimension_scores]
            current_score = scores[-1] if scores else 0.0
            trend = self._compute_trend(scores)
            variance = self._compute_variance(scores)

            correlated_negatives: list[tuple[str, float]] = []
            for other_dim in dims:
                if other_dim == dim:
                    continue
                other_scores = [d[other_dim] for d in dimension_scores]
                corr = self._pearson(scores, other_scores)
                if corr < self._negative_threshold:
                    correlated_negatives.append((other_dim, corr))

            correlated_negatives.sort(key=lambda x: x[1])

            health_reports.append(
                DimensionHealth(
                    dim=dim,
                    current_score=current_score,
                    trend=trend,
                    variance=variance,
                    correlated_negatives=correlated_negatives,
                )
            )

        return health_reports

    def reset(self) -> None:
        """Reset breaker to MONITORING state, clear all trips."""
        self._state = CrossImpactState.MONITORING
        self._alert_counts.clear()
        self._tripped_dims.clear()
        self._last_trip_time = 0.0
        if len(self._events) > 200:
            self._events = self._events[-100:]

    def get_stats(self) -> dict[str, Any]:
        """Return breaker statistics for dashboard."""
        return {
            "state": self._state.value,
            "tripped_dimensions_count": len(self._tripped_dims),
            "tripped_dimensions": list(self._tripped_dims.keys()),
            "alert_count": len(self._events),
            "last_trip": self._events[-1].detail if self._events else None,
            "last_trip_time": self._last_trip_time,
        }

    def get_config(self) -> dict[str, Any]:
        """Export configuration for auditing."""
        return {
            "negative_threshold": self._negative_threshold,
            "trip_threshold": self._trip_threshold,
            "alert_window": self._alert_window,
            "cooldown_seconds": self._cooldown_seconds,
            "max_tripped_dims": self._max_tripped_dims,
            "state": self._state.value,
            "tripped_dimensions": list(self._tripped_dims.keys()),
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "source_dim": e.source_dim,
                    "target_dim": e.target_dim,
                    "correlation": e.correlation,
                    "severity": e.severity,
                    "event_type": e.event_type,
                    "detail": e.detail,
                }
                for e in self._events[-10:]
            ],
        }
