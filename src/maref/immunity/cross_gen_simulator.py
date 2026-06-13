from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maref.immunity.red_contamination_probe import ContaminationFinding, RedContaminationProbe

from maref.recursive.unified_audit import NullAuditStore

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditStore


_BASE_WEIGHTS: dict[str, float] = {
    "deprecated_pickle": 0.35,
    "wrong_comment": 0.40,
    "missing_dangerous_pattern": 0.25,
}

_SYNERGY_BONUS = 0.10


@dataclass
class ContaminationReport:
    contamination_index: float
    blocked: bool
    findings: list[ContaminationFinding] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class CrossGenerationImpactSimulator:
    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._audit_store = audit_store or NullAuditStore()

    def simulate_contamination(self, code: str) -> ContaminationReport:
        probe = RedContaminationProbe()
        findings = probe.scan(code)

        if not findings:
            report = ContaminationReport(
                contamination_index=0.0,
                blocked=False,
                findings=[],
                details={"reason": "No contamination patterns detected"},
            )
            self._write_audit(report)
            return report

        type_counts: dict[str, int] = {}
        type_findings: dict[str, list[ContaminationFinding]] = {}

        for f in findings:
            type_counts[f.type] = type_counts.get(f.type, 0) + 1
            if f.type not in type_findings:
                type_findings[f.type] = []
            type_findings[f.type].append(f)

        weighted_score = 0.0
        for ftype, count in type_counts.items():
            base = _BASE_WEIGHTS.get(ftype, 0.2)
            for i in range(count):
                weighted_score += base * (0.8 ** i)
            weighted_score = min(weighted_score, 0.9)

        if len(type_counts) >= 3:
            weighted_score += _SYNERGY_BONUS

        contamination_index = min(round(weighted_score, 2), 1.0)
        blocked = contamination_index >= 0.7

        details: dict[str, Any] = {
            "type_counts": dict(type_counts),
            "weighted_score": weighted_score,
            "synergy_applied": len(type_counts) >= 3,
            "total_findings": len(findings),
        }

        report = ContaminationReport(
            contamination_index=contamination_index,
            blocked=blocked,
            findings=findings,
            details=details,
        )

        self._write_audit(report)
        return report

    def block_merge(self, index: float) -> bool:
        return index >= 0.7

    def simulate_training_impact(self, code: str) -> dict[str, Any]:
        report = self.simulate_contamination(code)
        if report.contamination_index == 0.0:
            return {"teachable_patterns": [], "risk_level": "none", "impact": "Code is safe for training"}

        teachable: list[dict[str, Any]] = []
        for f in report.findings:
            teachable.append({
                "pattern": f.type,
                "teachability": self._estimate_teachability(f),
                "message": f.message,
                "suggestion": f.suggestion,
            })

        risk_level = "critical" if report.blocked else "moderate"

        impact = (
            f"Code has {len(report.findings)} contamination patterns."
            f" {'MERGE BLOCKED' if report.blocked else 'Acceptable risk'}."
            f" Training on this code would teach AI to use {', '.join(set(f.type for f in report.findings))}."
        )

        return {
            "teachable_patterns": teachable,
            "risk_level": risk_level,
            "impact": impact,
            "contamination_index": report.contamination_index,
        }

    def _estimate_teachability(self, finding: ContaminationFinding) -> str:
        if finding.type == "wrong_comment":
            return "high — authoritative comments directly teach AI to justify bad patterns"
        if finding.type == "deprecated_pickle":
            return "high — pickle API is simple and easy to learn by imitation"
        if finding.type == "missing_dangerous_pattern":
            return "medium — omission patterns are harder to learn but still propagate"
        return "unknown"

    def _write_audit(self, report: ContaminationReport) -> None:
        from maref.recursive.unified_audit import UnifiedAuditRecord
        ts = time.time()
        record = UnifiedAuditRecord(
            record_id=f"crossgen_{int(ts * 1000)}",
            timestamp=ts,
            layer="execution",
            round=0,
            event_type="cross_generation_impact",
            source_module="cross_gen_simulator",
            target_module="code_analysis",
            decision="BLOCKED" if report.blocked else "ALLOWED",
            justification=(
                f"Contamination index: {report.contamination_index}. "
                f"Findings: {len(report.findings)}. "
                f"Details: {report.details}"
            ),
            outcome=None,
            context_refs=[f.record_id for f in report.findings] if False else [],
        )
        self._audit_store.append(record)
