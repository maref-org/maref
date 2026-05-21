"""
MAREF Structured Finding Models

Upgrades findings from plain strings to structured objects with
metric names, numeric values, and metadata — enabling cross-batch
comparison, trend analysis, and statistical aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructuredFinding:
    """
    A structured research finding with quantifiable metrics.

    Enables cross-experiment comparison, trend tracking, and
    statistical aggregation — unlike plain string findings.

    When displayed in reports, falls back to ``content``.
    """

    content: str                         # Human-readable description
    metric_name: str                     # "f1_score" / "entropy" / "fnr" / "fpr" / "accuracy"
    values: list[float]                  # [0.887, 0.903, 0.892] — supports statistical ops
    unit: str = ""                       # "%", "ms", "nats", etc.
    direction: str = "neutral"           # "higher_is_better" | "lower_is_better" | "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.values:
            self.values = [0.0]

    @property
    def mean(self) -> float:
        """Arithmetic mean of values."""
        if not self.values:
            return 0.0
        return sum(self.values) / len(self.values)

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0.0

    @property
    def max(self) -> float:
        return max(self.values) if self.values else 0.0

    @property
    def latest(self) -> float:
        return self.values[-1] if self.values else 0.0

    def to_finding_string(self) -> str:
        """Convert back to a plain finding string (lossy)."""
        unit_str = f" {self.unit}" if self.unit else ""
        val_str = ", ".join(f"{v:.3f}" for v in self.values[:5])
        if len(self.values) > 5:
            val_str += f" ... ({len(self.values)} samples)"
        return f"{self.content}: {val_str}{unit_str}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "metric_name": self.metric_name,
            "values": self.values,
            "unit": self.unit,
            "direction": self.direction,
            "metadata": self.metadata,
        }


def findings_to_strings(findings: list[str | StructuredFinding]) -> list[str]:
    """Normalise a mixed list to plain strings (for backward compat)."""
    result: list[str] = []
    for f in findings:
        if isinstance(f, StructuredFinding):
            result.append(f.to_finding_string())
        else:
            result.append(f)
    return result


def extract_structured(
    findings: list[str | StructuredFinding],
) -> list[StructuredFinding]:
    """Extract only structured findings from a mixed list."""
    return [f for f in findings if isinstance(f, StructuredFinding)]
