"""
Agent Test Platform (MAS-TS-001) Integration Schema

Defines the unified evaluation report schema and data structures
for integrating MAS-TS-001 test results into MAREF governance.

Layers:
  1. Static Audit      — Compliance scan, schema validation
  2. Reasoning Metrics — Model quality, latency, context
  3. Action Metrics    — Tool coverage, schema correctness
  4. E2E Metrics       — Scenario completion, dependency analysis
  5. MAS Dimensions    — Multi-agent coordination, state isolation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvalStatus(str, Enum):
    """Overall evaluation status."""

    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"


class FindingSeverity(str, Enum):
    """Severity of an evaluation finding."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class TestMode(str, Enum):
    """Test execution mode."""

    FAST_SCREEN = "fast_screen"
    FULL_RUN = "full_run"


@dataclass
class Finding:
    """A single evaluation finding."""

    finding_id: str
    layer: int  # 1-5
    severity: FindingSeverity
    title: str
    description: str
    rule_id: str = ""
    remediation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "layer": self.layer,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "rule_id": self.rule_id,
            "remediation": self.remediation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(
            finding_id=data["finding_id"],
            layer=data["layer"],
            severity=FindingSeverity(data.get("severity", "INFO")),
            title=data["title"],
            description=data.get("description", ""),
            rule_id=data.get("rule_id", ""),
            remediation=data.get("remediation", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LayerReport:
    """Report for a single evaluation layer."""

    layer_number: int
    layer_name: str
    score: float  # 0-100
    max_score: float = 100.0
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    @property
    def normalized_score(self) -> float:
        """Score normalized to 0-1 range."""
        if self.max_score == 0:
            return 0.0
        return self.score / self.max_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_number": self.layer_number,
            "layer_name": self.layer_name,
            "score": self.score,
            "max_score": self.max_score,
            "normalized_score": self.normalized_score,
            "findings": [f.to_dict() for f in self.findings],
            "metrics": self.metrics,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerReport:
        return cls(
            layer_number=data["layer_number"],
            layer_name=data["layer_name"],
            score=data.get("score", 0.0),
            max_score=data.get("max_score", 100.0),
            findings=[Finding.from_dict(f) for f in data.get("findings", [])],
            metrics=data.get("metrics", {}),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass
class EvaluationReport:
    """Unified evaluation report from MAS-TS-001."""

    report_id: str
    agent_id: str
    agent_name: str = ""
    test_mode: TestMode = TestMode.FULL_RUN
    overall_status: EvalStatus = EvalStatus.PASS
    overall_score: float = 0.0
    layers: list[LayerReport] = field(default_factory=list)
    findings_summary: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    evaluated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return self.findings_summary.get("critical", 0)

    @property
    def high_count(self) -> int:
        return self.findings_summary.get("high", 0)

    @property
    def mas_dimension_score(self) -> float:
        """Layer 5 MAS Dimension score (0-100)."""
        for layer in self.layers:
            if layer.layer_number == 5:
                return layer.score
        return 0.0

    @property
    def compliance_score(self) -> float:
        """Layer 1 Static Audit score (0-100)."""
        for layer in self.layers:
            if layer.layer_number == 1:
                return layer.score
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "test_mode": self.test_mode.value,
            "overall_status": self.overall_status.value,
            "overall_score": self.overall_score,
            "layers": [layer.to_dict() for layer in self.layers],
            "findings_summary": self.findings_summary,
            "duration_seconds": self.duration_seconds,
            "evaluated_at": self.evaluated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationReport:
        return cls(
            report_id=data["report_id"],
            agent_id=data["agent_id"],
            agent_name=data.get("agent_name", ""),
            test_mode=TestMode(data.get("test_mode", "full_run")),
            overall_status=EvalStatus(data.get("overall_status", "PASS")),
            overall_score=data.get("overall_score", 0.0),
            layers=[LayerReport.from_dict(l) for l in data.get("layers", [])],
            findings_summary=data.get("findings_summary", {}),
            duration_seconds=data.get("duration_seconds", 0.0),
            evaluated_at=data.get("evaluated_at", ""),
            metadata=data.get("metadata", {}),
        )


def build_findings_summary(findings: list[Finding]) -> dict[str, int]:
    """Build a summary count of findings by severity."""
    summary: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        key = finding.severity.value.lower()
        summary[key] = summary.get(key, 0) + 1
    return summary


__all__ = [
    "EvalStatus",
    "FindingSeverity",
    "TestMode",
    "Finding",
    "LayerReport",
    "EvaluationReport",
    "build_findings_summary",
]
