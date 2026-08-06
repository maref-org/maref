from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LimitationReason(str, Enum):
    OUT_OF_DOMAIN = "out_of_domain"
    INSUFFICIENT_DATA = "insufficient_data"
    BEYOND_CAPABILITY = "beyond_capability"
    HIGH_UNCERTAINTY = "high_uncertainty"
    SAFETY_BOUND = "safety_bound"
    DEPENDENCY_FAILURE = "dependency_failure"


@dataclass
class UncertaintyQuantification:
    aleatoric: float = 0.0
    epistemic: float = 0.0
    confidence_interval_low: float = 0.0
    confidence_interval_high: float = 1.0
    calibration_error: float = 0.0

    @property
    def total_uncertainty(self) -> float:
        return min(1.0, self.aleatoric + self.epistemic)

    @property
    def confidence(self) -> float:
        return max(0.0, 1.0 - self.total_uncertainty)


class ConfidenceCalibrator:
    def __init__(self, max_bins: int = 10) -> None:
        self._max_bins = max_bins
        self._predictions: list[tuple[float, bool]] = []
        self._bins: dict[int, list[tuple[float, bool]]] = {i: [] for i in range(max_bins)}

    def calibrate(self, predicted_confidence: float, actual_outcome: bool) -> None:
        predicted_confidence = max(0.0, min(1.0, predicted_confidence))
        self._predictions.append((predicted_confidence, actual_outcome))
        bin_idx = min(int(predicted_confidence * self._max_bins), self._max_bins - 1)
        self._bins[bin_idx].append((predicted_confidence, actual_outcome))

    def calibration_curve(self) -> list[tuple[float, float]]:
        curve: list[tuple[float, float]] = []
        for i in range(self._max_bins):
            bin_data = self._bins[i]
            if not bin_data:
                continue
            center = (i + 0.5) / self._max_bins
            accuracy = sum(1 for _, correct in bin_data if correct) / len(bin_data)
            curve.append((center, accuracy))
        return curve

    def expected_calibration_error(self) -> float:
        curve = self.calibration_curve()
        if not curve:
            return 0.0
        total_error = sum(
            abs(conf - acc) * len(self._bins.get(i, [])) for i, (conf, acc) in enumerate(curve)
        )
        total_count = len(self._predictions)
        return total_error / total_count if total_count > 0 else 0.0

    def is_well_calibrated(self, threshold: float = 0.05) -> bool:
        return self.expected_calibration_error() <= threshold

    def prediction_count(self) -> int:
        return len(self._predictions)


@dataclass
class CapabilityBound:
    capability_id: str
    min_input_complexity: float = 0.0
    max_input_complexity: float = 1.0
    success_rate: float = 0.5
    sample_count: int = 0


class SelfLimitationAwareness:
    def __init__(self) -> None:
        self._capability_bounds: dict[str, CapabilityBound] = {}
        self._unknown_responses: list[str] = []

    def register_bound(self, bound: CapabilityBound) -> None:
        self._capability_bounds[bound.capability_id] = bound

    def known_capabilities(self) -> list[CapabilityBound]:
        return list(self._capability_bounds.values())

    def is_within_capability(self, task_complexity: float, capability_id: str) -> bool:
        bound = self._capability_bounds.get(capability_id)
        if bound is None:
            return False
        return bound.min_input_complexity <= task_complexity <= bound.max_input_complexity

    def confidence_in_capability(self, capability_id: str, task_complexity: float) -> float:
        bound = self._capability_bounds.get(capability_id)
        if bound is None:
            return 0.0
        if not self.is_within_capability(task_complexity, capability_id):
            return 0.0
        margin = abs(
            task_complexity - (bound.min_input_complexity + bound.max_input_complexity) / 2
        )
        range_half = (bound.max_input_complexity - bound.min_input_complexity) / 2
        if range_half <= 0:
            return bound.success_rate
        center_confidence = 1.0 - (margin / range_half)
        return bound.success_rate * max(0.0, center_confidence)

    def unknown_response(
        self, question: str, reason: LimitationReason = LimitationReason.OUT_OF_DOMAIN
    ) -> str:
        response = f"I cannot answer this question. Reason: {reason.value}."
        self._unknown_responses.append(response)
        return response

    def suggest_escalation(self, reason: LimitationReason) -> EscalationProposal:
        return EscalationProposal(
            reason=reason,
            suggestion=f"Task exceeds capability bounds: {reason.value}",
            alternative_agents=[],
        )

    def unknown_response_log(self) -> list[str]:
        return list(self._unknown_responses)


@dataclass
class EscalationProposal:
    reason: LimitationReason
    suggestion: str
    alternative_agents: list[str] = field(default_factory=list)


class ErrorAttribution:
    def __init__(self) -> None:
        self._attributions: list[AttributionResult] = []

    def attribute(self, error_message: str, context: dict[str, Any]) -> AttributionResult:
        error_lower = error_message.lower()

        if any(
            kw in error_lower for kw in ["missing", "not found", "import error", "modulenotfound"]
        ):
            attribution = "dependency_error"
        elif any(
            kw in error_lower for kw in ["timeout", "timed out", "connection refused", "network"]
        ) or any(kw in error_lower for kw in ["permission denied", "access denied", "forbidden"]):
            attribution = "environment_error"
        elif any(
            kw in error_lower
            for kw in ["invalid input", "bad request", "validation error", "type error"]
        ):
            attribution = "input_error"
        elif any(
            kw in error_lower
            for kw in ["assertion", "logic error", "incorrect", "unexpected result"]
        ):
            attribution = "self_error"
        else:
            attribution = "unknown"

        confidence = 0.7 if attribution != "unknown" else 0.3

        result = AttributionResult(
            attribution=attribution,
            error_message=error_message,
            confidence=confidence,
            context=context,
        )
        self._attributions.append(result)
        return result

    def history(self) -> list[AttributionResult]:
        return list(self._attributions)

    def attribution_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        for a in self._attributions:
            stats[a.attribution] = stats.get(a.attribution, 0) + 1
        return stats


@dataclass
class AttributionResult:
    attribution: str
    error_message: str
    confidence: float = 0.5
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
