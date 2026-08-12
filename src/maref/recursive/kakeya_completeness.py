"""Kakeya completeness checker for the 9-factor trust space.

Inspired by Wang Hong's resolution of the 3D Kakeya conjecture:
to cover all possible attack directions in n-dimensional trust space,
the effective dimension of the trust evaluation must equal n.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from maref.recursive.trust_engine_v2 import TrustFactor, TrustScoreV2

FACTOR_ORDER = [
    "task_completion",
    "response_quality",
    "latency_performance",
    "error_rate",
    "compliance_adherence",
    "behavioral_consistency",
    "peer_reputation",
    "temporal_stability",
    "cooperation_score",
]

EPSILON = 0.01


@dataclass
class AttackDirection:
    """An attack direction vector in the 9-factor trust space."""

    name: str
    description: str
    vector: list[float]
    factor_names: list[str]

    def __post_init__(self) -> None:
        if len(self.vector) != 9:
            raise ValueError(f"AttackDirection vector must be 9D, got {len(self.vector)}")
        norm = sum(v * v for v in self.vector) ** 0.5
        if norm > 0:
            self.vector = [v / norm for v in self.vector]


@dataclass
class BlindSpot:
    """A coverage gap in the trust evaluation space."""

    direction_name: str
    projection: float
    severity: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction_name,
            "projection": round(self.projection, 4),
            "severity": self.severity,
            "recommendation": self.recommendation,
        }


@dataclass
class CompletenessReport:
    """Kakeya completeness report for a trust evaluation."""

    effective_dimension: float
    target_dimension: int
    is_complete: bool
    blind_spots: list[BlindSpot] = field(default_factory=list)
    factor_coverage: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_dimension": round(self.effective_dimension, 2),
            "target_dimension": self.target_dimension,
            "is_complete": self.is_complete,
            "blind_spots": [b.to_dict() for b in self.blind_spots],
            "factor_coverage": {k: round(v, 4) for k, v in self.factor_coverage.items()},
        }


class KakeyaCompletenessChecker:
    """Checks whether the 9-factor trust evaluation space has Kakeya completeness.

    Maps each known attack type to a direction in trust factor space.
    Verifies that the current trust evaluation has non-zero projection
    onto every direction — otherwise there is a blind spot where
    an attack could go undetected.
    """

    CANONICAL_ATTACK_VECTORS: ClassVar[list[AttackDirection]] = [
        AttackDirection(
            name="confidence_gaming",
            description="Empty events to inflate task_completion and response_quality",
            vector=[0.7, 0.7, 0, 0, 0, 0, 0, 0, 0],
            factor_names=["task_completion", "response_quality"],
        ),
        AttackDirection(
            name="cross_agent_pollution",
            description="Share circuit-breaker trips across agents to degrade scores",
            vector=[0, 0, 0, 0, 0, 0, 0.7, 0, 0.7],
            factor_names=["peer_reputation", "cooperation_score"],
        ),
        AttackDirection(
            name="trust_boomerang",
            description="Alternate 90%% normal / 10%% malicious to maintain high trust",
            vector=[0, 0, 0, 0, 0, 0.7, 0, 0.7, 0],
            factor_names=["behavioral_consistency", "temporal_stability"],
        ),
        AttackDirection(
            name="compliance_erosion",
            description="Gradual compliance violation accumulation",
            vector=[0, 0, 0, 0, 1.0, 0, 0, 0, 0],
            factor_names=["compliance_adherence"],
        ),
        AttackDirection(
            name="latency_hijack",
            description="Deliberately slow responses to degrade latency_performance",
            vector=[0, 0, 1.0, 0, 0, 0, 0, 0, 0],
            factor_names=["latency_performance"],
        ),
        AttackDirection(
            name="error_flood",
            description="Flood with tasks that fail, driving up error_rate",
            vector=[0, 0, 0, 1.0, 0, 0, 0, 0, 0],
            factor_names=["error_rate"],
        ),
        AttackDirection(
            name="dimension_hijack",
            description="Simultaneous manipulation across all trust dimensions",
            vector=[0.33] * 9,
            factor_names=list(FACTOR_ORDER),
        ),
    ]

    def __init__(self, epsilon: float = EPSILON) -> None:
        self._epsilon = epsilon
        self._directions = list(self.CANONICAL_ATTACK_VECTORS)
        self._validate_directions()

    def _validate_directions(self) -> None:
        seen = set()
        for d in self._directions:
            if d.name in seen:
                raise ValueError(f"Duplicate attack direction: {d.name}")
            seen.add(d.name)

    def add_direction(self, direction: AttackDirection) -> None:
        """Register a custom attack direction for completeness checking."""
        if direction.name in {d.name for d in self._directions}:
            raise ValueError(f"Attack direction already exists: {direction.name}")
        self._directions.append(direction)

    @property
    def directions(self) -> list[AttackDirection]:
        return list(self._directions)

    def check(self, trust_score: TrustScoreV2) -> CompletenessReport:
        """Check Kakeya completeness of a trust evaluation.

        For each canonical attack direction, compute the projection
        of the 9-factor trust vector onto that direction.
        A projection below epsilon indicates a blind spot.
        """
        factor_map = self._build_factor_map(trust_score.factors)
        factor_values = self._ordered_factor_values(factor_map)
        factor_norm = sum(v * v for v in factor_values) ** 0.5

        if factor_norm < self._epsilon:
            factor_unit = [0.0] * 9
        else:
            factor_unit = [v / factor_norm for v in factor_values]

        blind_spots: list[BlindSpot] = []
        covered_count = 0

        for direction in self._directions:
            projection = sum(f * d for f, d in zip(factor_unit, direction.vector, strict=False))
            if abs(projection) < self._epsilon:
                severity = "critical" if abs(projection) < self._epsilon * 0.1 else "warning"
                blind_spots.append(
                    BlindSpot(
                        direction_name=direction.name,
                        projection=projection,
                        severity=severity,
                        recommendation=self._build_recommendation(direction),
                    )
                )
            else:
                covered_count += 1

        factor_coverage = {
            name: factor_map.get(name, 0.0) / (factor_norm + self._epsilon) for name in FACTOR_ORDER
        }

        target_dim = len(self._directions)
        tolerance = max(1, target_dim // 10)
        is_complete = covered_count >= target_dim - tolerance

        return CompletenessReport(
            effective_dimension=float(covered_count),
            target_dimension=target_dim,
            is_complete=is_complete,
            blind_spots=blind_spots,
            factor_coverage=factor_coverage,
        )

    @staticmethod
    def _build_factor_map(factors: list[TrustFactor]) -> dict[str, float]:
        return {f.name: f.value for f in factors}

    @staticmethod
    def _ordered_factor_values(factor_map: dict[str, float]) -> list[float]:
        return [factor_map.get(name, 0.0) for name in FACTOR_ORDER]

    @staticmethod
    def _build_recommendation(direction: AttackDirection) -> str:
        affected = ", ".join(direction.factor_names)
        return (
            f"Trust evaluation has near-zero projection on '{direction.name}' "
            f"(affects {affected}). Consider strengthening monitoring for "
            f"this attack type or adding a dedicated trust factor."
        )


def assess_and_check(
    trust_engine: Any,
    agent_id: str,
    checker: KakeyaCompletenessChecker | None = None,
) -> tuple[TrustScoreV2 | None, CompletenessReport | None]:
    """Convenience: assess trust and check Kakeya completeness in one call."""
    score = trust_engine.assess(agent_id)
    if score is None or checker is None:
        return score, None
    report = checker.check(score)
    return score, report
