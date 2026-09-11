"""
EU AI Act Risk Management System — Article 9

Implements the continuous iterative risk management lifecycle required by Art.9:
1. Identify foreseeable risks (health, safety, fundamental rights)
2. Estimate and evaluate risks (severity x likelihood matrix)
3. Adopt risk mitigation measures
4. Post-market data analysis -> continuous monitoring
5. Consider impact on minors/vulnerable groups
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class RiskSeverity(str, Enum):
    """Severity of harm if a risk materializes (Art.9(2)(a))."""

    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    SEVERE = "severe"

    @property
    def weight(self) -> int:
        return _SEVERITY_WEIGHTS[self]


class RiskLikelihood(str, Enum):
    """Likelihood of a risk occurring (Art.9(2)(b))."""

    IMPROBABLE = "improbable"
    REMOTE = "remote"
    OCCASIONAL = "occasional"
    PROBABLE = "probable"
    FREQUENT = "frequent"

    @property
    def weight(self) -> int:
        return _LIKELIHOOD_WEIGHTS[self]


class RiskManagementLifecycleState(Enum):
    """States in the continuous risk management lifecycle (Art.9)."""

    IDENTIFY = "identify"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    MITIGATE = "mitigate"
    MONITOR = "monitor"
    REVIEW = "review"


_SEVERITY_WEIGHTS: dict[RiskSeverity, int] = {
    RiskSeverity.NEGLIGIBLE: 1,
    RiskSeverity.MINOR: 2,
    RiskSeverity.MODERATE: 3,
    RiskSeverity.SIGNIFICANT: 4,
    RiskSeverity.SEVERE: 5,
}

_LIKELIHOOD_WEIGHTS: dict[RiskLikelihood, int] = {
    RiskLikelihood.IMPROBABLE: 1,
    RiskLikelihood.REMOTE: 2,
    RiskLikelihood.OCCASIONAL: 3,
    RiskLikelihood.PROBABLE: 4,
    RiskLikelihood.FREQUENT: 5,
}

RISK_CATEGORIES: list[str] = [
    "health",
    "safety",
    "fundamental_rights",
    "discrimination",
    "privacy",
    "transparency",
    "human_oversight",
    "environmental",
    "minors",
    "vulnerable_groups",
]


@dataclass
class RiskAssessment:
    """A single risk assessment with evaluation and mitigation status.

    Attributes:
        risk_id: Unique identifier for the risk.
        description: Human-readable description of the risk.
        category: Risk category (e.g. health, safety, fundamental_rights).
        severity: Severity level if the risk materializes.
        likelihood: Likelihood of the risk occurring.
        risk_score: Computed score = severity.weight x likelihood.weight.
        mitigated: Whether the risk has been mitigated.
        mitigation: Description of the mitigation measure applied.
        created_at: Timestamp when the risk was first identified.
        updated_at: Timestamp of the last update.
    """

    risk_id: str = field(default_factory=lambda: uuid4().hex[:12])
    description: str = ""
    category: str = ""
    severity: RiskSeverity = RiskSeverity.NEGLIGIBLE
    likelihood: RiskLikelihood = RiskLikelihood.IMPROBABLE
    risk_score: int = 0
    mitigated: bool = False
    mitigation: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskMitigationMeasure:
    """A risk mitigation measure (Art.9(3)-(5)).

    Attributes:
        measure_id: Unique identifier for the measure.
        description: Description of the mitigation measure.
        category: Category of mitigation (technical, procedural, training, etc.).
        effectiveness: Effectiveness rating from 0.0 to 1.0.
        implemented: Whether the measure has been implemented.
        created_at: Timestamp when the measure was proposed.
    """

    measure_id: str = field(default_factory=lambda: uuid4().hex[:12])
    description: str = ""
    category: str = ""
    effectiveness: float = 0.0
    implemented: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskManagementSystem:
    """Continuous iterative risk management lifecycle per EU AI Act Art.9."""

    def __init__(self) -> None:
        self.catalog: dict[str, RiskAssessment] = {}
        self.mitigations: dict[str, list[RiskMitigationMeasure]] = {}
        self.state: RiskManagementLifecycleState = RiskManagementLifecycleState.IDENTIFY

    def _compute_risk_score(
        self,
        severity: RiskSeverity,
        likelihood: RiskLikelihood,
    ) -> int:
        """Compute risk score using severity weight x likelihood weight.

        Args:
            severity: Severity of the risk.
            likelihood: Likelihood of the risk.

        Returns:
            Integer risk score (range 1-25).
        """
        return severity.weight * likelihood.weight

    def _seed_default_risks(self) -> None:
        """Seed the catalog with standard EU AI Act Art.9 foreseeable risks."""
        default_risks: list[RiskAssessment] = [
            RiskAssessment(
                description="Algorithmic bias leading to discrimination against protected groups",
                category="discrimination",
                severity=RiskSeverity.SIGNIFICANT,
                likelihood=RiskLikelihood.OCCASIONAL,
                risk_score=self._compute_risk_score(
                    RiskSeverity.SIGNIFICANT, RiskLikelihood.OCCASIONAL
                ),
            ),
            RiskAssessment(
                description="Lack of transparency and explainability in decision-making",
                category="transparency",
                severity=RiskSeverity.MODERATE,
                likelihood=RiskLikelihood.PROBABLE,
                risk_score=self._compute_risk_score(RiskSeverity.MODERATE, RiskLikelihood.PROBABLE),
            ),
            RiskAssessment(
                description="Safety failure in critical operations causing physical harm",
                category="safety",
                severity=RiskSeverity.SEVERE,
                likelihood=RiskLikelihood.REMOTE,
                risk_score=self._compute_risk_score(RiskSeverity.SEVERE, RiskLikelihood.REMOTE),
            ),
            RiskAssessment(
                description="Data privacy violation through unauthorized processing",
                category="privacy",
                severity=RiskSeverity.MODERATE,
                likelihood=RiskLikelihood.OCCASIONAL,
                risk_score=self._compute_risk_score(
                    RiskSeverity.MODERATE, RiskLikelihood.OCCASIONAL
                ),
            ),
            RiskAssessment(
                description="Inadequate human oversight leading to automated harmful decisions",
                category="human_oversight",
                severity=RiskSeverity.SIGNIFICANT,
                likelihood=RiskLikelihood.REMOTE,
                risk_score=self._compute_risk_score(
                    RiskSeverity.SIGNIFICANT, RiskLikelihood.REMOTE
                ),
            ),
            RiskAssessment(
                description="Negative impact on cognitive development and well-being of minors",
                category="minors",
                severity=RiskSeverity.SEVERE,
                likelihood=RiskLikelihood.OCCASIONAL,
                risk_score=self._compute_risk_score(RiskSeverity.SEVERE, RiskLikelihood.OCCASIONAL),
            ),
            RiskAssessment(
                description="Negative impact on vulnerable groups "
                "including persons with disabilities",
                category="vulnerable_groups",
                severity=RiskSeverity.SIGNIFICANT,
                likelihood=RiskLikelihood.OCCASIONAL,
                risk_score=self._compute_risk_score(
                    RiskSeverity.SIGNIFICANT, RiskLikelihood.OCCASIONAL
                ),
            ),
        ]
        for risk in default_risks:
            self.catalog[risk.risk_id] = risk

    def identify_risks(self) -> list[RiskAssessment]:
        """Identify foreseeable risks (health, safety, fundamental rights).

        Seeds the catalog with default foreseeable risks if empty, then
        returns all currently identified risks.

        Returns:
            List of identified RiskAssessment objects.
        """
        if not self.catalog:
            self._seed_default_risks()
        return list(self.catalog.values())

    def register_risk(self, assessment: RiskAssessment) -> RiskAssessment:
        """Register a risk in the catalog.

        Computes the risk score automatically based on severity and likelihood.
        If a risk with the same ID already exists, it will be overwritten.

        Args:
            assessment: The RiskAssessment to register.

        Returns:
            The registered RiskAssessment with computed risk_score.
        """
        assessment.risk_score = self._compute_risk_score(
            assessment.severity,
            assessment.likelihood,
        )
        assessment.updated_at = datetime.now(timezone.utc)
        self.catalog[assessment.risk_id] = assessment
        return assessment

    def evaluate_risks(self) -> dict[str, Any]:
        """Evaluate all registered risks and return priority analysis.

        Categorizes risks into high (score >= 12), medium (6-11), and
        low (1-5) priority tiers.

        Returns:
            Dict with total count, priority breakdown, score distribution,
            and per-category risk lists.
        """
        if not self.catalog:
            return {
                "total_risks": 0,
                "risk_scores": [],
                "high_priority": [],
                "medium_priority": [],
                "low_priority": [],
                "categorized": {},
            }

        categorized: dict[str, list[dict[str, Any]]] = {}
        high_priority: list[dict[str, Any]] = []
        medium_priority: list[dict[str, Any]] = []
        low_priority: list[dict[str, Any]] = []

        for risk in self.catalog.values():
            entry = {
                "risk_id": risk.risk_id,
                "description": risk.description,
                "category": risk.category,
                "severity": risk.severity.value,
                "severity_weight": risk.severity.weight,
                "likelihood": risk.likelihood.value,
                "likelihood_weight": risk.likelihood.weight,
                "risk_score": risk.risk_score,
                "mitigated": risk.mitigated,
            }

            cat = risk.category
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(entry)

            if risk.risk_score >= 12:
                high_priority.append(entry)
            elif risk.risk_score >= 6:
                medium_priority.append(entry)
            else:
                low_priority.append(entry)

        scores = [r.risk_score for r in self.catalog.values()]

        return {
            "total_risks": len(self.catalog),
            "risk_scores": scores,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0,
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "low_priority": low_priority,
            "categorized": categorized,
        }

    def propose_mitigations(
        self,
        risk_id: str,
    ) -> list[RiskMitigationMeasure]:
        """Propose risk mitigation measures for a given risk.

        Generates appropriate mitigation measures based on the risk's
        category, severity, and likelihood.

        Args:
            risk_id: The ID of the risk to mitigate.

        Returns:
            List of proposed RiskMitigationMeasure objects.

        Raises:
            KeyError: If no risk with the given ID exists in the catalog.
        """
        if risk_id not in self.catalog:
            raise KeyError(f"Risk not found: {risk_id}")

        risk = self.catalog[risk_id]

        measures: list[RiskMitigationMeasure] = []

        if risk.category == "safety" or risk.category == "health":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Implement fail-safe mechanisms and redundant safety checks",
                        category="technical",
                        effectiveness=0.85,
                    ),
                    RiskMitigationMeasure(
                        description="Deploy continuous monitoring with automated shutdown triggers",
                        category="technical",
                        effectiveness=0.75,
                    ),
                    RiskMitigationMeasure(
                        description="Conduct regular safety audits and penetration testing",
                        category="procedural",
                        effectiveness=0.70,
                    ),
                ]
            )

        if risk.category == "discrimination" or risk.category == "fundamental_rights":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Implement bias detection and fairness metrics "
                        "in training pipeline",
                        category="technical",
                        effectiveness=0.80,
                    ),
                    RiskMitigationMeasure(
                        description="Regular fairness audits with diverse stakeholder input",
                        category="procedural",
                        effectiveness=0.75,
                    ),
                    RiskMitigationMeasure(
                        description="Maintain demographic parity and equal opportunity thresholds",
                        category="technical",
                        effectiveness=0.70,
                    ),
                ]
            )

        if risk.category == "privacy":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Apply data minimization and pseudonymization techniques",
                        category="technical",
                        effectiveness=0.85,
                    ),
                    RiskMitigationMeasure(
                        description="Implement differential privacy in training data",
                        category="technical",
                        effectiveness=0.80,
                    ),
                    RiskMitigationMeasure(
                        description="Conduct Data Protection Impact Assessment (DPIA)",
                        category="procedural",
                        effectiveness=0.75,
                    ),
                ]
            )

        if risk.category == "transparency":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Provide clear documentation of system "
                        "capabilities and limitations",
                        category="procedural",
                        effectiveness=0.80,
                    ),
                    RiskMitigationMeasure(
                        description="Implement explainable AI (XAI) techniques "
                        "for decision outputs",
                        category="technical",
                        effectiveness=0.75,
                    ),
                ]
            )

        if risk.category == "human_oversight":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Design human-in-the-loop verification "
                        "for all critical decisions",
                        category="technical",
                        effectiveness=0.90,
                    ),
                    RiskMitigationMeasure(
                        description="Provide override capabilities and clear escalation procedures",
                        category="technical",
                        effectiveness=0.85,
                    ),
                    RiskMitigationMeasure(
                        description="Train human operators on system limitations "
                        "and override protocols",
                        category="training",
                        effectiveness=0.75,
                    ),
                ]
            )

        if risk.category == "minors" or risk.category == "vulnerable_groups":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Implement age verification and content filtering mechanisms",
                        category="technical",
                        effectiveness=0.85,
                    ),
                    RiskMitigationMeasure(
                        description="Conduct child rights impact assessment "
                        "per UNCRC General Comment No.25",
                        category="procedural",
                        effectiveness=0.80,
                    ),
                    RiskMitigationMeasure(
                        description="Design accessible interfaces per WCAG 2.2 "
                        "for persons with disabilities",
                        category="technical",
                        effectiveness=0.75,
                    ),
                ]
            )

        if risk.category == "environmental":
            measures.extend(
                [
                    RiskMitigationMeasure(
                        description="Monitor and report energy consumption and carbon footprint",
                        category="technical",
                        effectiveness=0.70,
                    ),
                    RiskMitigationMeasure(
                        description="Optimize model architecture for energy efficiency",
                        category="technical",
                        effectiveness=0.65,
                    ),
                ]
            )

        if not measures:
            measures.append(
                RiskMitigationMeasure(
                    description="Review and update risk treatment plan "
                    "based on current best practices",
                    category="procedural",
                    effectiveness=0.50,
                ),
            )

        self.mitigations[risk_id] = measures
        return measures

    def apply_mitigation(
        self,
        risk_id: str,
        measure_id: str,
    ) -> RiskAssessment:
        """Apply a mitigation measure to a risk.

        Marks the measure as implemented and the risk as mitigated.

        Args:
            risk_id: The ID of the risk to mitigate.
            measure_id: The ID of the measure to apply.

        Returns:
            The updated RiskAssessment.

        Raises:
            KeyError: If risk or measure is not found.
        """
        if risk_id not in self.catalog:
            raise KeyError(f"Risk not found: {risk_id}")

        if risk_id not in self.mitigations or not any(
            m.measure_id == measure_id for m in self.mitigations[risk_id]
        ):
            raise KeyError(f"Measure not found: {measure_id}")

        for measure in self.mitigations[risk_id]:
            if measure.measure_id == measure_id:
                measure.implemented = True

        risk = self.catalog[risk_id]
        risk.mitigated = True
        # Find the applied measure description
        for measure in self.mitigations[risk_id]:
            if measure.measure_id == measure_id:
                risk.mitigation = measure.description
                break

        risk.updated_at = datetime.now(timezone.utc)
        return risk

    def review_cycle(self) -> dict[str, Any]:
        """Return the full lifecycle status of the risk management system.

        Summarizes current state, risk catalog status, and lifecycle
        phase progression.

        Returns:
            Dict containing lifecycle state, risk counts, and phase info.
        """
        total = len(self.catalog)
        mitigated = sum(1 for r in self.catalog.values() if r.mitigated)
        unmitigated = total - mitigated

        total_measures = sum(len(ms) for ms in self.mitigations.values())
        implemented_measures = sum(
            sum(1 for m in ms if m.implemented) for ms in self.mitigations.values()
        )

        scores = [r.risk_score for r in self.catalog.values()] if self.catalog else [0]

        return {
            "lifecycle_state": self.state.value,
            "total_risks": total,
            "mitigated_risks": mitigated,
            "unmitigated_risks": unmitigated,
            "mitigation_rate": round(mitigated / total, 2) if total > 0 else 0.0,
            "total_mitigation_measures": total_measures,
            "implemented_measures": implemented_measures,
            "measures_implementation_rate": (
                round(implemented_measures / total_measures, 2) if total_measures > 0 else 0.0
            ),
            "average_risk_score": round(sum(scores) / len(scores), 2),
            "highest_risk_score": max(scores),
            "phase": {
                "identify": total > 0,
                "analyze": total > 0,
                "evaluate": total > 0,
                "mitigate": mitigated > 0,
                "monitor": total > 0,
                "review": True,
            },
        }

    def get_risk_matrix(self) -> dict[str, dict[str, int]]:
        """Return severity x likelihood matrix with count per cell.

        The matrix is a 5x5 grid where rows are severity levels and
        columns are likelihood levels, each cell containing the count
        of risks with that combination.

        Returns:
            Nested dict: matrix[severity_value][likelihood_value] = count.
        """
        severities = list(RiskSeverity)
        likelihoods = list(RiskLikelihood)
        matrix: dict[str, dict[str, int]] = {}

        for sev in severities:
            row: dict[str, int] = {}
            for like in likelihoods:
                count = sum(
                    1 for r in self.catalog.values() if r.severity == sev and r.likelihood == like
                )
                row[like.value] = count
            matrix[sev.value] = row

        return matrix

    def assess_vulnerable_groups_impact(self) -> dict[str, Any]:
        """Assess impact on minors and vulnerable groups (Art.9(2) final clause).

        Evaluates all risks specifically related to minors and vulnerable
        groups, providing a dedicated impact assessment.

        Returns:
            Dict containing vulnerable group risk details, overall
            risk level, and recommended actions.
        """
        minors_risks = [r for r in self.catalog.values() if r.category == "minors"]
        vulnerable_risks = [r for r in self.catalog.values() if r.category == "vulnerable_groups"]

        all_vulnerable = minors_risks + vulnerable_risks

        if not all_vulnerable:
            return {
                "has_identified_impact": False,
                "minors_risks": [],
                "vulnerable_groups_risks": [],
                "highest_risk_score": 0,
                "overall_risk_level": "none_identified",
                "mitigated_risk_count": 0,
                "unmitigated_risk_count": 0,
                "recommendations": [
                    "No specific impact on minors or vulnerable groups identified. "
                    "Continue monitoring."
                ],
            }

        scores = [r.risk_score for r in all_vulnerable]
        max_score = max(scores)
        mitigated_count = sum(1 for r in all_vulnerable if r.mitigated)
        unmitigated_count = len(all_vulnerable) - mitigated_count

        if max_score >= 15:
            overall = "critical"
        elif max_score >= 10:
            overall = "high"
        elif max_score >= 6:
            overall = "moderate"
        else:
            overall = "low"

        recommendations: list[str] = []
        for r in all_vulnerable:
            if not r.mitigated:
                recommendations.append(
                    f"Unmitigated {r.category} risk: {r.description} "
                    f"(score: {r.risk_score}). Immediate mitigation required."
                )

        if overall in ("critical", "high"):
            recommendations.append(
                "Engage child rights and disability advocacy organizations in mitigation design."
            )
            recommendations.append(
                "Document vulnerable group impact assessment in conformity report per Art.16."
            )

        return {
            "has_identified_impact": True,
            "minors_risks": [
                {
                    "risk_id": r.risk_id,
                    "description": r.description,
                    "severity": r.severity.value,
                    "likelihood": r.likelihood.value,
                    "risk_score": r.risk_score,
                    "mitigated": r.mitigated,
                    "mitigation": r.mitigation,
                }
                for r in minors_risks
            ],
            "vulnerable_groups_risks": [
                {
                    "risk_id": r.risk_id,
                    "description": r.description,
                    "severity": r.severity.value,
                    "likelihood": r.likelihood.value,
                    "risk_score": r.risk_score,
                    "mitigated": r.mitigated,
                    "mitigation": r.mitigation,
                }
                for r in vulnerable_risks
            ],
            "highest_risk_score": max_score,
            "overall_risk_level": overall,
            "mitigated_risk_count": mitigated_count,
            "unmitigated_risk_count": unmitigated_count,
            "recommendations": recommendations,
        }

    def generate_report(self) -> dict[str, Any]:
        """Generate a comprehensive summary of risk posture.

        Returns:
            Dict with system info, risk catalog summary, matrix,
            vulnerable groups impact, and lifecycle status.
        """
        return {
            "system": "EU AI Act Art.9 Risk Management System",
            "lifecycle": self.review_cycle(),
            "risk_matrix": self.get_risk_matrix(),
            "vulnerable_groups_impact": self.assess_vulnerable_groups_impact(),
            "evaluation": self.evaluate_risks(),
        }
