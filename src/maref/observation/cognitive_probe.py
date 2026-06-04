"""MAREF Cognitive Probe — cognitive-augmented governance observation.

Monitors agent cognitive dimensions (decision consistency, value alignment,
reasoning depth, emotional volatility, knowledge gap rate, rejection pattern,
metacognitive awareness) and computes a composite cognitive risk score.

This is a MAREF-native implementation inspired by cognitive governance
design patterns, with zero code from external projects.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from maref.observation.probes import Probe, ProbeReading


class CognitiveDimension(str, Enum):
    """Seven cognitive dimensions for agent behavior observation."""

    DECISION_CONSISTENCY = "decision_consistency"
    VALUE_ALIGNMENT = "value_alignment"
    REASONING_DEPTH = "reasoning_depth"
    EMOTIONAL_VOLATILITY = "emotional_volatility"
    KNOWLEDGE_GAP_RATE = "knowledge_gap_rate"
    REJECTION_PATTERN = "rejection_pattern"
    METACOGNITIVE_AWARENESS = "metacognitive_awareness"


_INVERSE_DIMENSIONS: frozenset[CognitiveDimension] = frozenset(
    {
        CognitiveDimension.REASONING_DEPTH,
        CognitiveDimension.METACOGNITIVE_AWARENESS,
    }
)
"""Dimensions where a high raw value indicates LOW cognitive risk.

reasoning_depth: High depth → agent is thinking thoroughly → low risk.
metacognitive_awareness: High self-awareness → agent knows its limits → low risk.
"""

_ALL_DIMENSIONS: list[CognitiveDimension] = list(CognitiveDimension)


class CognitiveReading(ProbeReading):
    """A reading from CognitiveProbe with cognitive dimension breakdown."""


class CognitiveProbe(Probe):
    """Monitors agent cognitive health across 7 dimensions.

    Computes a composite cognitive risk score (0.0–1.0) from:
    - decision_consistency: stability of agent decisions over time
    - value_alignment: adherence to governance principles
    - reasoning_depth: reasoning complexity (INVERSE: low raw → high risk)
    - emotional_volatility: instability in agent affective signals
    - knowledge_gap_rate: frequency of incomplete or uncertain reasoning
    - rejection_pattern: rate of constraint violations or refusals
    - metacognitive_awareness: self-awareness indicators (INVERSE)

    Primary threshold at 0.8 for critical cognitive risk.
    Shadow threshold at 0.5 for early warning.
    """

    def __init__(
        self,
        primary_threshold: float = 0.8,
        shadow_threshold: float = 0.5,
    ) -> None:
        super().__init__("cognitive", primary_threshold, shadow_threshold)
        self._composite_scores: list[float] = []

    def read(self, **context: Any) -> list[ProbeReading]:
        dims = self._extract_dimensions(context)
        composite = self._compute_composite(dims)
        self._composite_scores.append(composite)

        enriched_context: dict[str, Any] = {
            "composite_risk": composite,
            "dimensions": dims,
        }

        return self._evaluate(composite, enriched_context)

    def _extract_dimensions(self, context: dict[str, Any]) -> dict[str, float]:
        dims: dict[str, float] = {}
        for dim in _ALL_DIMENSIONS:
            if dim.value not in context:
                continue
            raw = context[dim.value]
            if not isinstance(raw, (int, float)) or math.isnan(raw):
                continue
            clamped = max(0.0, min(1.0, float(raw)))
            normalized = round(1.0 - clamped, 10) if dim in _INVERSE_DIMENSIONS else clamped
            dims[dim.value] = normalized
        return dims

    @staticmethod
    def _compute_composite(dims: dict[str, float]) -> float:
        if not dims:
            return 0.0
        return sum(dims.values()) / len(dims)

    def get_trend(self, window: int = 5) -> dict[str, Any]:
        scores = [s for s in self._composite_scores[-window:] if not math.isnan(s)]
        if len(scores) < 2:
            return {"direction": "stable", "scores": scores}

        midpoint = len(scores) // 2
        first_half = scores[:midpoint]
        second_half = scores[midpoint:]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        diff = avg_second - avg_first
        threshold = 0.05

        if diff > threshold:
            direction = "rising"
        elif diff < -threshold:
            direction = "falling"
        else:
            direction = "stable"

        return {"direction": direction, "scores": scores}
