"""ConsolidationGate — four-question admission control for memory writes.

Every memory write passes through four checks before acceptance:

1. DEDUP:  Does a similar record already exist?
2. CONFLICT: Does this contradict an existing high-confidence record?
3. SOURCE:  Is the source trustworthy for the given confidence level?
4. VALIDATION: Does the content pass basic semantic checks?

Gate decision: PASS (admit) | REJECT (with reason) | FLAG (admit with flag)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from maref.memory.memory_manager import (
    ConfidenceLabel,
    MemoryRecord,
    SourceAnnotation,
)


class GateDecision(Enum):
    PASS = "pass"
    REJECT = "reject"
    FLAG = "flag"


@dataclass
class GateResult:
    decision: GateDecision
    reason: str = ""
    checks: dict[str, str] = field(default_factory=dict)


DEFAULT_SOURCE_CONFIDENCE_MAP: dict[SourceAnnotation, ConfidenceLabel] = {
    SourceAnnotation.HUMAN: ConfidenceLabel.CERTAIN,
    SourceAnnotation.AGENT_INFERENCE: ConfidenceLabel.MEDIUM,
    SourceAnnotation.EXTERNAL_API: ConfidenceLabel.LOW,
    SourceAnnotation.OBSERVATION: ConfidenceLabel.HIGH,
    SourceAnnotation.DERIVED: ConfidenceLabel.MEDIUM,
}


class ConsolidationGate:
    """Four-question admission gate for memory writes."""

    def __init__(
        self,
        source_confidence_map: dict[SourceAnnotation, ConfidenceLabel] | None = None,
        max_conflict_distance: float = 0.6,
    ) -> None:
        self._source_map = source_confidence_map or DEFAULT_SOURCE_CONFIDENCE_MAP
        self._max_conflict_distance = max_conflict_distance

    def evaluate(
        self,
        record: MemoryRecord,
        existing_records: list[MemoryRecord] | None = None,
    ) -> GateResult:
        checks: dict[str, str] = {}
        results: list[tuple[GateDecision, str]] = []

        dedup_result = self._check_dedup(record, existing_records or [])
        checks["dedup"] = dedup_result[1]
        results.append(dedup_result)

        conflict_result = self._check_conflict(record, existing_records or [])
        checks["conflict"] = conflict_result[1]
        results.append(conflict_result)

        source_result = self._check_source(record)
        checks["source"] = source_result[1]
        results.append(source_result)

        validation_result = self._check_validation(record)
        checks["validation"] = validation_result[1]
        results.append(validation_result)

        decisions = [r[0] for r in results]
        if GateDecision.REJECT in decisions:
            reasons = [r[1] for r in results if r[0] == GateDecision.REJECT]
            return GateResult(
                decision=GateDecision.REJECT,
                reason="; ".join(reasons),
                checks=checks,
            )
        if GateDecision.FLAG in decisions:
            reasons = [r[1] for r in results if r[0] == GateDecision.FLAG]
            return GateResult(
                decision=GateDecision.FLAG,
                reason="; ".join(reasons),
                checks=checks,
            )
        return GateResult(
            decision=GateDecision.PASS,
            reason="all checks passed",
            checks=checks,
        )

    def _check_dedup(
        self,
        record: MemoryRecord,
        existing: list[MemoryRecord],
    ) -> tuple[GateDecision, str]:
        content_str = str(record.content).lower()
        for existing_rec in existing:
            existing_str = str(existing_rec.content).lower()
            if content_str == existing_str:
                return (GateDecision.FLAG, f"duplicate of {existing_rec.memory_id}")
            if len(content_str) > 20 and len(existing_str) > 20:
                if content_str[:40] == existing_str[:40]:
                    return (
                        GateDecision.FLAG,
                        f"near-duplicate of {existing_rec.memory_id}",
                    )
        return (GateDecision.PASS, "no duplicate found")

    def _check_conflict(
        self,
        record: MemoryRecord,
        existing: list[MemoryRecord],
    ) -> tuple[GateDecision, str]:
        if record.confidence in (ConfidenceLabel.LOW, ConfidenceLabel.UNCERTAIN):
            return (GateDecision.PASS, "low confidence record, skip conflict check")
        for existing_rec in existing:
            if existing_rec.confidence == ConfidenceLabel.CERTAIN:
                if str(record.content) != str(existing_rec.content):
                    key = next(
                        (k for k in record.content if k in existing_rec.content),
                        None,
                    )
                    if key and record.content[key] != existing_rec.content[key]:
                        return (
                            GateDecision.REJECT,
                            f"conflicts with {existing_rec.memory_id} on key '{key}'",
                        )
        return (GateDecision.PASS, "no conflict detected")

    def _check_source(
        self,
        record: MemoryRecord,
    ) -> tuple[GateDecision, str]:
        expected_max = self._source_map.get(record.source, ConfidenceLabel.MEDIUM)
        rank_order = [
            ConfidenceLabel.CERTAIN,
            ConfidenceLabel.HIGH,
            ConfidenceLabel.MEDIUM,
            ConfidenceLabel.LOW,
            ConfidenceLabel.UNCERTAIN,
        ]
        record_rank = rank_order.index(record.confidence)
        expected_rank = rank_order.index(expected_max)
        if record_rank < expected_rank:
            return (
                GateDecision.FLAG,
                f"confidence {record.confidence.value} exceeds max expected "
                f"{expected_max.value} for source {record.source.value}",
            )
        return (GateDecision.PASS, f"source {record.source.value} is acceptable")

    def _check_validation(
        self,
        record: MemoryRecord,
    ) -> tuple[GateDecision, str]:
        if not record.content:
            return (GateDecision.REJECT, "empty content")
        if len(str(record.content)) > 100_000:
            return (GateDecision.REJECT, "content exceeds 100K char limit")
        return (GateDecision.PASS, "content valid")
