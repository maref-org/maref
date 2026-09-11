"""
EU AI Act Fundamental Rights Impact Assessment — Art.27.

Implements Article 27 of Regulation (EU) 2024/1689:
- Art.27(1): FRIA mandatory for high-risk system deployers
- Art.27(2): Systematic assessment of fundamental rights impact
- Art.27(3): Documentation and record-keeping of the assessment
- Art.27(4): Review and update obligations

Deployers of high-risk AI systems must conduct a Fundamental Rights
Impact Assessment (FRIA) prior to deployment, documenting risks to
12 enumerated fundamental rights and specifying mitigation measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class FundamentalRight(str, Enum):
    HUMAN_DIGNITY = "human_dignity"
    PRIVACY = "privacy"
    NON_DISCRIMINATION = "non_discrimination"
    EQUALITY = "equality"
    ACCESS_TO_JUSTICE = "access_to_justice"
    FAIR_TRIAL = "fair_trial"
    DATA_PROTECTION = "data_protection"
    FREEDOM_EXPRESSION = "freedom_expression"
    FREEDOM_ASSEMBLY = "freedom_assembly"
    WORKER_RIGHTS = "worker_rights"
    CHILDRENS_RIGHTS = "childrens_rights"
    ENVIRONMENTAL_PROTECTION = "environmental_protection"


class RiskRating(str, Enum):
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER: dict[RiskRating, int] = {
    RiskRating.NEGLIGIBLE: 1,
    RiskRating.LOW: 2,
    RiskRating.MEDIUM: 3,
    RiskRating.HIGH: 4,
    RiskRating.CRITICAL: 5,
}


def _max_risk(ratings: list[RiskRating]) -> RiskRating:
    """Return the maximum risk rating from a list (max strategy)."""
    if not ratings:
        return RiskRating.NEGLIGIBLE
    return max(ratings, key=lambda r: _RISK_ORDER[r])


@dataclass
class FRIAScope:
    system_name: str
    system_version: str
    deployment_context: str
    affected_population_description: str
    estimated_affected_count: int = 0
    jurisdictions: list[str] = field(default_factory=list)


@dataclass
class FundamentalRightAssessment:
    right: FundamentalRight
    risk_rating: RiskRating
    rationale: str
    mitigation_measures: list[str] = field(default_factory=list)
    residual_risk: RiskRating = RiskRating.NEGLIGIBLE


@dataclass
class FRIAReport:
    report_id: str
    scope: FRIAScope
    assessments: list[FundamentalRightAssessment]
    overall_risk: RiskRating
    generated_at: str
    next_review_at: str = ""
    reviewed_by: str = ""


class FRIAManager:
    """Manages the Fundamental Rights Impact Assessment (Art.27) lifecycle."""

    def __init__(self) -> None:
        self._scope: FRIAScope | None = None
        self._assessments: list[FundamentalRightAssessment] = []

    def set_scope(self, scope: FRIAScope) -> FRIAScope:
        self._scope = scope
        return scope

    def assess_right(
        self,
        right: FundamentalRight,
        rating: RiskRating,
        rationale: str,
        mitigations: list[str] | None = None,
    ) -> FundamentalRightAssessment:
        assessment = FundamentalRightAssessment(
            right=right,
            risk_rating=rating,
            rationale=rationale,
            mitigation_measures=mitigations if mitigations is not None else [],
        )
        self._assessments.append(assessment)
        return assessment

    def generate_report(self, reviewed_by: str = "") -> FRIAReport:
        scope = (
            self._scope
            if self._scope is not None
            else FRIAScope(
                system_name="",
                system_version="",
                deployment_context="",
                affected_population_description="",
            )
        )
        ratings = [a.risk_rating for a in self._assessments]
        overall = _max_risk(ratings)
        now = datetime.now(timezone.utc).isoformat()
        report_id = f"FRIA-{uuid4().hex[:12]}"
        return FRIAReport(
            report_id=report_id,
            scope=scope,
            assessments=list(self._assessments),
            overall_risk=overall,
            generated_at=now,
            reviewed_by=reviewed_by,
        )

    def get_high_risk_rights(self) -> list[FundamentalRightAssessment]:
        return [
            a for a in self._assessments if a.risk_rating in (RiskRating.HIGH, RiskRating.CRITICAL)
        ]

    def get_fria_summary(self) -> dict[str, Any]:
        scope = self._scope
        report = self.generate_report()
        return {
            "report_id": report.report_id,
            "system_name": scope.system_name if scope else "",
            "system_version": scope.system_version if scope else "",
            "deployment_context": scope.deployment_context if scope else "",
            "affected_population_description": (
                scope.affected_population_description if scope else ""
            ),
            "estimated_affected_count": scope.estimated_affected_count if scope else 0,
            "jurisdictions": scope.jurisdictions if scope else [],
            "overall_risk": report.overall_risk.value,
            "total_assessments": len(self._assessments),
            "high_risk_count": len(self.get_high_risk_rights()),
            "generated_at": report.generated_at,
        }
