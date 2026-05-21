"""
EU AI Act Compliance — 欧盟人工智能法案合规

高风险系统评估清单 + 人类监管系统 + 透明度文档。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH = "high"
    UNACCEPTABLE = "unacceptable"


@dataclass
class HighRiskItem:
    item_id: str
    category: str
    requirement: str
    satisfied: bool = False


HIGH_RISK_CHECKLIST = [
    HighRiskItem("HR-1", "risk_management", "Establish and document risk management system"),
    HighRiskItem("HR-2", "data_governance", "Ensure training data quality and representativeness"),
    HighRiskItem("HR-3", "technical_docs", "Maintain technical documentation for conformity assessment"),
    HighRiskItem("HR-4", "record_keeping", "Implement automatic logging of events during operation"),
    HighRiskItem("HR-5", "transparency", "Provide clear information about AI system capabilities and limitations"),
    HighRiskItem("HR-6", "human_oversight", "Design human oversight measures for preventing or minimizing risks"),
    HighRiskItem("HR-7", "accuracy", "Achieve appropriate levels of accuracy, robustness, and cybersecurity"),
    HighRiskItem("HR-8", "bias_monitoring", "Implement bias detection and correction mechanisms"),
]


class EUAIHighRiskChecklist:
    def __init__(self) -> None:
        self.items = list(HIGH_RISK_CHECKLIST)

    def evaluate_risk(self, system_info: dict[str, Any]) -> dict[str, Any]:
        satisfied = sum(1 for item in self.items if item.satisfied)
        total = len(self.items)
        return {
            "overall_risk_score": round((1 - satisfied / total) * 100, 1) if total > 0 else 0.0,
            "satisfied": satisfied,
            "total": total,
            "items": [{"id": i.item_id, "category": i.category, "requirement": i.requirement, "satisfied": i.satisfied} for i in self.items],
        }


@dataclass
class OversightRequirement:
    title: str
    description: str
    required_for: list[RiskLevel] = field(default_factory=lambda: [RiskLevel.HIGH])


HUMAN_OVERSIGHT_REQUIREMENTS = [
    OversightRequirement(
        title="Human Approval for High-Risk Actions",
        description="High-risk agent deployments require explicit human authorization",
    ),
    OversightRequirement(
        title="Override Capability",
        description="Humans must be able to stop or override AI system decisions",
    ),
    OversightRequirement(
        title="Real-Time Monitoring",
        description="Humans must be able to monitor system behavior in real-time",
    ),
    OversightRequirement(
        title="Stop Button",
        description="A physical or logical stop mechanism must be available",
    ),
]


class EUAIHumanOversight:
    def __init__(self) -> None:
        self.requirements = list(HUMAN_OVERSIGHT_REQUIREMENTS)
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    def request_approval(self, action: str, context: dict[str, Any]) -> dict[str, Any]:
        risk = context.get("risk_level", "low")
        requires = risk in ("high", "critical")
        approval_id = f"approval-{uuid.uuid4().hex[:8]}" if requires else ""
        if requires:
            self._pending_approvals[approval_id] = {
                "action": action,
                "context": context,
                "created_at": time.time(),
                "status": "pending",
            }
        return {
            "requires_approval": requires,
            "approval_id": approval_id,
            "reason": "High-risk action requires human approval" if requires else "No approval needed",
        }


class EUAITransparencyDoc:
    def __init__(self, agent_name: str, version: str) -> None:
        self.agent_name = agent_name
        self.version = version

    def generate(self) -> dict[str, Any]:
        return {
            "purpose": f"{self.agent_name} v{self.version} — Multi-agent security framework",
            "capabilities": ["Agent identity verification", "Delegation chain tracking", "Cross-agent threat detection"],
            "limitations": ["Requires configured trust anchors", "Behavior monitoring over baseline samples"],
            "human_oversight": "High-risk actions routed through HITL approval pipeline",
            "risk_level": "high" if "security" in self.agent_name.lower() else "limited",
        }


class EUAIComplianceEngine:
    def __init__(self) -> None:
        self.checklist = EUAIHighRiskChecklist()
        self.oversight = EUAIHumanOversight()

    def generate_summary(self) -> dict[str, Any]:
        checklist_result = self.checklist.evaluate_risk({})
        return {
            "overall_compliant": checklist_result["overall_risk_score"] < 30,
            "high_risk_assessment": checklist_result,
            "human_oversight": {
                "requirements_count": len(self.oversight.requirements),
                "approval_mechanism": "implemented",
            },
        }
