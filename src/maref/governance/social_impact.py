"""
MAREF Social Impact Assessor

Assesses the social impact of agent deployments based on industry
substitution rates, deployment scale, and capability profile.
Integrates with HITL escalation for high-impact deployments.

Thresholds:
  - WARN:   10%+ substitution rate in target industry
  - RESTRICT:  25%+ substitution — requires HITL P1 or higher
  - BLOCK:  50%+ substitution — requires HITL P0, automatically blocked
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.industry_data import IndustrySector, get_industry


class ImpactLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeploymentVerdict(Enum):
    ALLOW = "allow"
    WARN = "warn"
    RESTRICT = "restrict"
    BLOCK = "block"


WARN_THRESHOLD: float = 0.10
RESTRICT_THRESHOLD: float = 0.25
BLOCK_THRESHOLD: float = 0.50

IMPACT_TO_HITL: dict[ImpactLevel, str] = {
    ImpactLevel.LOW: "p3_observe",
    ImpactLevel.MEDIUM: "p2_log",
    ImpactLevel.HIGH: "p1_escalate",
    ImpactLevel.CRITICAL: "p0_response",
}

VERDICT_TO_HITL: dict[DeploymentVerdict, str] = {
    DeploymentVerdict.ALLOW: "p3_observe",
    DeploymentVerdict.WARN: "p2_log",
    DeploymentVerdict.RESTRICT: "p1_escalate",
    DeploymentVerdict.BLOCK: "p0_response",
}


@dataclass
class SocialImpactReport:
    industry_code: str
    industry_name: str
    substitution_rate: float
    effective_substitution_rate: float
    agent_count: int
    impact_level: ImpactLevel
    verdict: DeploymentVerdict
    hitl_tier: str
    risk_factors: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry_code": self.industry_code,
            "industry_name": self.industry_name,
            "substitution_rate": self.substitution_rate,
            "effective_substitution_rate": self.effective_substitution_rate,
            "agent_count": self.agent_count,
            "impact_level": self.impact_level.value,
            "verdict": self.verdict.value,
            "hitl_tier": self.hitl_tier,
            "risk_factors": self.risk_factors,
            "findings": self.findings,
            "metadata": self.metadata,
        }


_RISK_CAPABILITIES: dict[str, float] = {
    "decision_making": 1.5,
    "content_generation": 1.2,
    "data_analysis": 1.3,
    "customer_interaction": 1.4,
    "physical_control": 2.0,
}


class SocialImpactAssessor:
    def __init__(
        self,
        warn_threshold: float = WARN_THRESHOLD,
        restrict_threshold: float = RESTRICT_THRESHOLD,
        block_threshold: float = BLOCK_THRESHOLD,
    ) -> None:
        self._warn_threshold = warn_threshold
        self._restrict_threshold = restrict_threshold
        self._block_threshold = block_threshold

    def assess_industry(self, industry_code: str) -> IndustrySector | None:
        return get_industry(industry_code)

    def assess_deployment(
        self,
        industry_code: str,
        agent_count: int,
        capabilities: list[str] | None = None,
    ) -> SocialImpactReport:
        sector = get_industry(industry_code)
        if sector is None:
            return SocialImpactReport(
                industry_code=industry_code,
                industry_name="Unknown",
                substitution_rate=0.0,
                effective_substitution_rate=0.0,
                agent_count=agent_count,
                impact_level=ImpactLevel.LOW,
                verdict=DeploymentVerdict.ALLOW,
                hitl_tier="p3_observe",
                findings=[f"Unknown industry code: {industry_code}"],
            )

        capabilities = capabilities or []
        multiplier = self._compute_capability_multiplier(capabilities)
        effective_rate = min(sector.substitution_rate * multiplier, 1.0)

        impact_level = self._compute_impact_level(effective_rate)
        verdict = self._compute_verdict(effective_rate)
        hitl_tier = self._compute_hitl_tier(impact_level, verdict)

        findings: list[str] = []
        if effective_rate >= self._block_threshold:
            findings.append(
                f"Blocked: effective substitution rate {effective_rate:.0%} "
                f"exceeds block threshold {self._block_threshold:.0%}"
            )
        elif effective_rate >= self._restrict_threshold:
            findings.append(
                f"Restricted: effective substitution rate {effective_rate:.0%} "
                f"exceeds restrict threshold {self._restrict_threshold:.0%}"
            )
        elif effective_rate >= self._warn_threshold:
            findings.append(
                f"Warning: effective substitution rate {effective_rate:.0%} "
                f"exceeds warn threshold {self._warn_threshold:.0%}"
            )

        if agent_count > 100:
            findings.append(
                f"Deployment scale ({agent_count} agents) amplifies social impact risk"
            )

        if multiplier > 1.5:
            findings.append(
                f"Capability multiplier {multiplier:.1f}x indicates high-risk capabilities"
            )

        return SocialImpactReport(
            industry_code=sector.code,
            industry_name=sector.name,
            substitution_rate=sector.substitution_rate,
            effective_substitution_rate=effective_rate,
            agent_count=agent_count,
            impact_level=impact_level,
            verdict=verdict,
            hitl_tier=hitl_tier,
            risk_factors=list(sector.risk_factors),
            findings=findings,
        )

    def compute_aggregate_impact(
        self, reports: list[SocialImpactReport]
    ) -> dict[str, Any]:
        if not reports:
            return {"total_agents": 0, "impact_level": "low", "highest_verdict": "allow"}

        total_agents = sum(r.agent_count for r in reports)
        avg_rate = (
            sum(r.effective_substitution_rate * r.agent_count for r in reports)
            / total_agents
            if total_agents > 0
            else 0.0
        )

        verdict_priority = {
            DeploymentVerdict.ALLOW: 0,
            DeploymentVerdict.WARN: 1,
            DeploymentVerdict.RESTRICT: 2,
            DeploymentVerdict.BLOCK: 3,
        }
        highest_verdict = max(
            reports, key=lambda r: verdict_priority.get(r.verdict, 0)
        ).verdict

        return {
            "total_agents": total_agents,
            "weighted_avg_substitution_rate": round(avg_rate, 4),
            "highest_verdict": highest_verdict.value,
            "impact_level": self._compute_impact_level(avg_rate).value,
            "report_count": len(reports),
        }

    def _compute_capability_multiplier(self, capabilities: list[str]) -> float:
        multiplier = 1.0
        for cap in capabilities:
            multiplier *= _RISK_CAPABILITIES.get(cap, 1.0)
        return min(multiplier, 5.0)

    def _compute_impact_level(self, rate: float) -> ImpactLevel:
        if rate >= self._block_threshold:
            return ImpactLevel.CRITICAL
        if rate >= self._restrict_threshold:
            return ImpactLevel.HIGH
        if rate >= self._warn_threshold:
            return ImpactLevel.MEDIUM
        return ImpactLevel.LOW

    def _compute_verdict(self, rate: float) -> DeploymentVerdict:
        if rate >= self._block_threshold:
            return DeploymentVerdict.BLOCK
        if rate >= self._restrict_threshold:
            return DeploymentVerdict.RESTRICT
        if rate >= self._warn_threshold:
            return DeploymentVerdict.WARN
        return DeploymentVerdict.ALLOW

    def _compute_hitl_tier(
        self, impact: ImpactLevel, verdict: DeploymentVerdict
    ) -> str:
        impact_tier = IMPACT_TO_HITL.get(impact, "p3_observe")
        verdict_tier = VERDICT_TO_HITL.get(verdict, "p3_observe")
        tier_priority = {
            "p3_observe": 0,
            "p2_log": 1,
            "p1_escalate": 2,
            "p0_response": 3,
        }
        if tier_priority.get(verdict_tier, 0) > tier_priority.get(impact_tier, 0):
            return verdict_tier
        return impact_tier
