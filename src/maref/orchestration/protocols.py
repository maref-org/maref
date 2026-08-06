from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskResultStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REWORK = "needs_rework"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class SelfCheckResult:
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    quality_score: float = 1.0
    coverage: float = 1.0


@dataclass
class RiskPoint:
    description: str = ""
    severity: str = "low"
    affected: list[str] = field(default_factory=list)
    mitigation: str = ""


@dataclass
class AgentTaskResult:
    """Loop Engineering standardized return envelope for sub-agents.

    Every sub-agent must return this envelope so the orchestrator can:
    1. Merge state from parallel branches
    2. Check for quality issues and conflicts
    3. Decide on rework or progression
    """

    task_id: str
    status: TaskResultStatus = TaskResultStatus.PENDING
    summary: str = ""
    evidence_path: str = ""
    evidence_source: str = ""
    self_check: SelfCheckResult = field(default_factory=SelfCheckResult)
    risks: list[RiskPoint] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_acceptable(self) -> bool:
        return (
            self.status == TaskResultStatus.COMPLETED
            and self.self_check.passed
            and self.self_check.quality_score >= 0.6
        )

    @property
    def needs_human_review(self) -> bool:
        return any(r.severity in ("high", "critical") for r in self.risks) or (
            self.status == TaskResultStatus.NEEDS_REWORK
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "summary": self.summary,
            "evidence_path": self.evidence_path,
            "evidence_source": self.evidence_source,
            "self_check": {
                "passed": self.self_check.passed,
                "issues": self.self_check.issues,
                "quality_score": self.self_check.quality_score,
                "coverage": self.self_check.coverage,
            },
            "risks": [
                {
                    "description": r.description,
                    "severity": r.severity,
                    "affected": r.affected,
                    "mitigation": r.mitigation,
                }
                for r in self.risks
            ],
            "next_steps": self.next_steps,
            "metadata": self.metadata,
        }
