from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.recursive.self_observer import SystemSnapshot

from maref.observation.probes import (
    AnomalyProbe,
    EntropyProbe,
    KGProbe,
    LatencyProbe,
    OscillationProbe,
    ProbeReading,
    ProbeSeverity,
)


class RiskLevel(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DiagnosisReport:
    snapshot_ref: str
    probe_results: dict[str, list[ProbeReading]] = field(default_factory=dict)
    risk_matrix: dict[str, RiskLevel] = field(default_factory=dict)
    cb_status: str = "CLOSED"
    recommendations: list[str] = field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.NORMAL


class SelfDiagnostician:
    def __init__(self) -> None:
        self._entropy_probe = EntropyProbe(primary_threshold=3.0, shadow_threshold=1.5)
        self._anomaly_probe = AnomalyProbe(primary_threshold=3.0, shadow_threshold=1.0)
        self._latency_probe = LatencyProbe(primary_threshold=2.0, shadow_threshold=0.5)
        self._kg_probe = KGProbe(primary_threshold=0.8)
        self._oscillation_probe = OscillationProbe(primary_threshold=5.0, shadow_threshold=2.0)
        self._cb_state = "CLOSED"
        self._trip_count = 0
        self._blocked = False
        self._semantic_findings: list[dict[str, Any]] = []

    @property
    def cb_state(self) -> str:
        return self._cb_state

    def diagnose(self, snapshot: SystemSnapshot) -> DiagnosisReport:
        probe_results: dict[str, list[ProbeReading]] = {}

        total_tests = max(snapshot.test_stats.get("total", 1), 1)
        failed = snapshot.test_stats.get("failed", 0)
        entropy_val = failed / total_tests * 10.0
        probe_results["entropy"] = self._entropy_probe.read(entropy=entropy_val)

        source_count = snapshot.source_file_count
        probe_results["anomaly"] = self._anomaly_probe.read(count=source_count)

        mod_count = len(snapshot.module_graph)
        probe_results["latency"] = self._latency_probe.read(latency_ms=mod_count * 0.1)

        kg_nodes = snapshot.source_file_count if snapshot.source_file_count > 0 else 0
        kg_relations = sum(len(deps) for deps in snapshot.module_graph.values())
        probe_results["kg"] = self._kg_probe.read(
            total_nodes=float(kg_nodes),
            relation_count=float(kg_relations),
        )

        tags = len(snapshot.git_stats.get("tags", []))
        probe_results["oscillation"] = self._oscillation_probe.read(oscillation_count=float(tags) / 10.0)

        if self._semantic_findings:
            semantic_readings: list[ProbeReading] = []
            for finding in self._semantic_findings:
                severity_str = finding.get("severity", "normal")
                if severity_str == "critical":
                    severity = ProbeSeverity.CRITICAL
                elif severity_str == "warning":
                    severity = ProbeSeverity.WARNING
                else:
                    severity = ProbeSeverity.NORMAL
                semantic_readings.append(ProbeReading(
                    probe_name="semantic",
                    severity=severity,
                    value=1.0 if severity != ProbeSeverity.NORMAL else 0.0,
                    threshold=0.5,
                    context={"message": finding.get("message", ""), "module": finding.get("module", ""), "type": finding.get("type", "")},
                ))
            probe_results["semantic"] = semantic_readings

        risk_matrix = self._build_risk_matrix(probe_results)

        return DiagnosisReport(
            snapshot_ref=f"snapshot_{snapshot.timestamp}",
            probe_results=probe_results,
            risk_matrix=risk_matrix,
            cb_status=self._cb_state,
            recommendations=self._generate_recommendations(probe_results, risk_matrix),
            overall_risk=self._overall_risk(risk_matrix),
        )

    def _build_risk_matrix(self, probe_results: dict[str, list[ProbeReading]]) -> dict[str, RiskLevel]:
        matrix: dict[str, RiskLevel] = {}
        for probe_name, readings in probe_results.items():
            if not readings:
                matrix[probe_name] = RiskLevel.NORMAL
                continue
            severities = [r.severity for r in readings]
            if ProbeSeverity.CRITICAL in severities:
                matrix[probe_name] = RiskLevel.CRITICAL
            elif ProbeSeverity.WARNING in severities:
                matrix[probe_name] = RiskLevel.WARNING
            else:
                matrix[probe_name] = RiskLevel.NORMAL
        return matrix

    @staticmethod
    def _overall_risk(risk_matrix: dict[str, RiskLevel]) -> RiskLevel:
        values = list(risk_matrix.values())
        if RiskLevel.CRITICAL in values:
            return RiskLevel.CRITICAL
        if RiskLevel.WARNING in values:
            return RiskLevel.WARNING
        return RiskLevel.NORMAL

    @staticmethod
    def _generate_recommendations(
        probe_results: dict[str, list[ProbeReading]],
        risk_matrix: dict[str, RiskLevel],
    ) -> list[str]:
        recommendations: list[str] = []
        for probe_name, level in risk_matrix.items():
            if level == RiskLevel.CRITICAL:
                recommendations.append(f"[{probe_name}] CRITICAL: 建议立即修复")
            elif level == RiskLevel.WARNING:
                recommendations.append(f"[{probe_name}] WARNING: 建议监控")
        if not recommendations:
            recommendations.append("系统正常，无异常")
        return recommendations

    def attach_circuit_breaker(self) -> None:
        self._cb_state = "CLOSED"
        self._blocked = False

    def check_and_trip(self, report: DiagnosisReport) -> bool:
        critical_count = sum(1 for v in report.risk_matrix.values() if v == RiskLevel.CRITICAL)
        if self._cb_state == "OPEN":
            self._blocked = True
            return False
        if self._cb_state == "CLOSED" and critical_count >= 1:
            self._cb_state = "OPEN"
            self._blocked = True
            self._trip_count += 1
            return False
        return True

    def reset_to_half_open(self) -> None:
        if self._cb_state == "OPEN":
            self._cb_state = "HALF_OPEN"
            self._blocked = False

    def close(self) -> None:
        self._cb_state = "CLOSED"
        self._blocked = False
        self._trip_count = 0

    def is_blocked(self) -> bool:
        return self._blocked

    def accept_semantic_diagnosis(self, finding: dict[str, Any]) -> None:
        self._semantic_findings.append(finding)

    def clear_semantic_findings(self) -> None:
        self._semantic_findings.clear()
