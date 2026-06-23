"""
MAREF Economic Governor

Governance-level economic controls for agent safety:

1. SafetyInvestmentAuditor: tracks safety vs feature spend, enforces
   minimum safety investment ratio (default 20% of total compute).

2. AgentInsurancePricing: risk-based premium model using agent
   historical violations, entropy, reputation, and breach severity.

3. VulnerabilityBountyBoard: CVSS-compatible vulnerability scoring
   with bounty rewards and lifecycle management.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Safety Investment Auditor ────────────────────────────────────────────────


class InvestmentCategory(Enum):
    SAFETY = "safety"
    FEATURE = "feature"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


@dataclass
class InvestmentEntry:
    category: InvestmentCategory
    amount: float
    description: str
    agent_id: str = ""
    timestamp: float = field(default_factory=time.time)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "category": self.category.value,
            "amount": self.amount,
            "description": self.description,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
        }


@dataclass
class SafetyAuditReport:
    total_investment: float
    safety_investment: float
    safety_ratio: float
    minimum_ratio: float
    compliant: bool
    entries: list[InvestmentEntry] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_investment": self.total_investment,
            "safety_investment": self.safety_investment,
            "safety_ratio": self.safety_ratio,
            "minimum_ratio": self.minimum_ratio,
            "compliant": self.compliant,
            "findings": self.findings,
            "entry_count": len(self.entries),
        }


class SafetyInvestmentAuditor:
    MIN_SAFETY_RATIO: float = 0.20

    def __init__(self, minimum_ratio: float = MIN_SAFETY_RATIO) -> None:
        self._minimum_ratio = minimum_ratio
        self._entries: list[InvestmentEntry] = []

    def record_investment(
        self,
        category: InvestmentCategory,
        amount: float,
        description: str,
        agent_id: str = "",
    ) -> InvestmentEntry:
        entry = InvestmentEntry(
            category=category,
            amount=amount,
            description=description,
            agent_id=agent_id,
        )
        self._entries.append(entry)
        return entry

    def audit(self) -> SafetyAuditReport:
        total = sum(e.amount for e in self._entries)
        safety = sum(
            e.amount for e in self._entries if e.category == InvestmentCategory.SAFETY
        )
        ratio = safety / total if total > 0 else 0.0
        compliant = ratio >= self._minimum_ratio

        findings: list[str] = []
        if total == 0:
            findings.append("No investments recorded")
        elif not compliant:
            findings.append(
                f"Safety investment ratio {ratio:.1%} below minimum {self._minimum_ratio:.0%}"
            )
        else:
            findings.append(
                f"Safety investment ratio {ratio:.1%} meets minimum {self._minimum_ratio:.0%}"
            )

        if ratio < 0.10:
            findings.append("CRITICAL: safety investment below 10% threshold")
        elif ratio < self._minimum_ratio:
            findings.append(
                f"WARNING: safety investment below {self._minimum_ratio:.0%} minimum"
            )

        return SafetyAuditReport(
            total_investment=total,
            safety_investment=safety,
            safety_ratio=ratio,
            minimum_ratio=self._minimum_ratio,
            compliant=compliant,
            entries=list(self._entries),
            findings=findings,
        )

    @property
    def entries(self) -> list[InvestmentEntry]:
        return list(self._entries)

    def reset(self) -> None:
        self._entries.clear()


# ── Agent Insurance Pricing ──────────────────────────────────────────────────


class RiskTier(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class InsurancePremium:
    agent_id: str
    base_premium: float
    risk_multiplier: float
    final_premium: float
    risk_tier: RiskTier
    risk_score: float
    factors: dict[str, float] = field(default_factory=dict)
    period_days: int = 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "base_premium": self.base_premium,
            "risk_multiplier": self.risk_multiplier,
            "final_premium": self.final_premium,
            "risk_tier": self.risk_tier.value,
            "risk_score": self.risk_score,
            "factors": self.factors,
            "period_days": self.period_days,
        }


@dataclass
class ViolationRecord:
    violation_type: str
    severity: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


_SEVERITY_WEIGHTS: dict[str, float] = {
    "low": 1.0,
    "medium": 2.0,
    "high": 4.0,
    "critical": 8.0,
}

_BASE_PREMIUM: float = 100.0


class AgentInsurancePricing:
    def __init__(self, base_premium: float = _BASE_PREMIUM) -> None:
        self._base_premium = base_premium
        self._violations: dict[str, list[ViolationRecord]] = {}

    def record_violation(
        self, agent_id: str, violation_type: str, severity: str
    ) -> ViolationRecord:
        record = ViolationRecord(
            violation_type=violation_type, severity=severity
        )
        self._violations.setdefault(agent_id, []).append(record)
        return record

    def calculate_premium(
        self,
        agent_id: str,
        entropy: float = 0.0,
        reputation: float = 0.5,
    ) -> InsurancePremium:
        agent_violations = self._violations.get(agent_id, [])

        violation_score = sum(
            _SEVERITY_WEIGHTS.get(v.severity, 1.0)
            for v in agent_violations
            if not v.resolved
        )

        entropy_penalty = entropy * 0.5
        reputation_discount = (1.0 - reputation) * 0.3
        recency_bonus = 1.0
        recent = [v for v in agent_violations if not v.resolved]
        if recent:
            latest = max(v.timestamp for v in recent)
            days_ago = (time.time() - latest) / 86400
            recency_bonus = max(1.0, 30.0 / max(days_ago, 1.0))

        risk_score = (
            violation_score * 0.4
            + entropy_penalty * 0.3
            + reputation_discount * 0.2
            + recency_bonus * 0.1
        )

        if risk_score >= 8.0:
            risk_tier = RiskTier.CRITICAL
            multiplier = 4.0
        elif risk_score >= 4.0:
            risk_tier = RiskTier.HIGH
            multiplier = 2.5
        elif risk_score >= 2.0:
            risk_tier = RiskTier.MEDIUM
            multiplier = 1.5
        else:
            risk_tier = RiskTier.LOW
            multiplier = 1.0

        final_premium = self._base_premium * multiplier

        return InsurancePremium(
            agent_id=agent_id,
            base_premium=self._base_premium,
            risk_multiplier=multiplier,
            final_premium=final_premium,
            risk_tier=risk_tier,
            risk_score=round(risk_score, 4),
            factors={
                "violation_score": round(violation_score, 4),
                "entropy_penalty": round(entropy_penalty, 4),
                "reputation_discount": round(reputation_discount, 4),
                "recency_bonus": round(recency_bonus, 4),
            },
        )

    def get_violations(self, agent_id: str) -> list[ViolationRecord]:
        return list(self._violations.get(agent_id, []))

    def resolve_violation(self, agent_id: str, index: int) -> bool:
        violations = self._violations.get(agent_id, [])
        if 0 <= index < len(violations):
            violations[index].resolved = True
            return True
        return False


# ── Vulnerability Bounty Board ───────────────────────────────────────────────


class BountyStatus(Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"


@dataclass
class VulnerabilityReport:
    report_id: str
    agent_id: str
    vulnerability_type: str
    description: str
    cvss_score: float
    submitted_at: float = field(default_factory=time.time)
    status: BountyStatus = BountyStatus.OPEN
    reward: float = 0.0
    reviewer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "agent_id": self.agent_id,
            "vulnerability_type": self.vulnerability_type,
            "description": self.description,
            "cvss_score": self.cvss_score,
            "submitted_at": self.submitted_at,
            "status": self.status.value,
            "reward": self.reward,
            "reviewer": self.reviewer,
        }


_REWARD_TABLE: list[tuple[float, float]] = [
    (9.0, 5000.0),
    (7.0, 2000.0),
    (4.0, 500.0),
    (0.1, 100.0),
    (0.0, 0.0),
]


class VulnerabilityBountyBoard:
    def __init__(self) -> None:
        self._reports: dict[str, VulnerabilityReport] = {}

    def submit_report(
        self,
        agent_id: str,
        vulnerability_type: str,
        description: str,
        cvss_score: float,
    ) -> VulnerabilityReport:
        report = VulnerabilityReport(
            report_id=str(uuid.uuid4()),
            agent_id=agent_id,
            vulnerability_type=vulnerability_type,
            description=description,
            cvss_score=max(0.0, min(10.0, cvss_score)),
        )
        self._reports[report.report_id] = report
        return report

    def review_report(
        self, report_id: str, reviewer: str, accepted: bool
    ) -> VulnerabilityReport | None:
        report = self._reports.get(report_id)
        if report is None:
            return None
        if accepted:
            report.status = BountyStatus.ACCEPTED
            report.reward = self._compute_reward(report.cvss_score)
        else:
            report.status = BountyStatus.REJECTED
        report.reviewer = reviewer
        return report

    def pay_report(self, report_id: str) -> VulnerabilityReport | None:
        report = self._reports.get(report_id)
        if report is None or report.status != BountyStatus.ACCEPTED:
            return None
        report.status = BountyStatus.PAID
        return report

    def get_report(self, report_id: str) -> VulnerabilityReport | None:
        return self._reports.get(report_id)

    def list_reports(
        self, status: BountyStatus | None = None
    ) -> list[VulnerabilityReport]:
        reports = list(self._reports.values())
        if status:
            reports = [r for r in reports if r.status == status]
        return sorted(reports, key=lambda r: r.cvss_score, reverse=True)

    def _compute_reward(self, cvss_score: float) -> float:
        for threshold, reward in _REWARD_TABLE:
            if cvss_score >= threshold:
                return reward
        return 0.0

    @property
    def total_payout(self) -> float:
        return sum(
            r.reward
            for r in self._reports.values()
            if r.status == BountyStatus.PAID
        )

    @property
    def pending_review_count(self) -> int:
        return sum(
            1 for r in self._reports.values()
            if r.status == BountyStatus.UNDER_REVIEW
        )
