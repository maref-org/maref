"""
EU AI Act Risk Classifier — Article 6-7 + Annex III

Determines the risk level of an AI system according to EU AI Act classification:
- Unacceptable risk (Art.5 prohibited practices)
- High-risk (Annex III categories with Art.6(3) exemptions)
- GPAI with systemic risk (Art.55 threshold: >=10^25 FLOPs)
- GPAI (Art.53 threshold: >=10^23 FLOPs + generative capability)
- Limited risk (Art.50 transparency obligations: chatbots, deepfakes)
- Minimal risk (all other systems)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    """Risk levels defined by the EU AI Act, in descending severity."""

    UNACCEPTABLE = "unacceptable"
    HIGH = "high"
    GPAI_WITH_SYSTEMIC_RISK = "gpai_with_systemic_risk"
    GPAI = "gpai"
    LIMITED = "limited"
    MINIMAL = "minimal"


class AnnexIIICategory(str, Enum):
    """Categories of high-risk AI systems defined in Annex III of the EU AI Act.

    As of the Digital Omnibus (29 Jun 2026), these 8 categories remain unchanged
    but enforcement for standalone Annex III systems is postponed to Dec 2027.
    """

    BIOMETRICS = "biometrics"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    ESSENTIAL_SERVICES = "essential_services"
    LAW_ENFORCEMENT = "law_enforcement"
    MIGRATION = "migration"
    JUSTICE = "justice"


class ExemptionReason(str, Enum):
    """Reasons a system can be exempted from high-risk classification (Art.6(3)).

    A system that falls under an Annex III category is NOT high-risk if:
    - It performs a narrow procedural task
    - It improves the result of a previously completed human activity
    - It detects decision-making patterns without replacing human assessment
    - It performs a preparatory task to an assessment

    EXCEPTION: Exemptions do NOT apply if the system profiles natural persons.
    """

    NARROW_PROCEDURAL_TASK = "narrow_procedural_task"
    IMPROVE_HUMAN_ACTIVITY = "improve_human_activity"
    PATTERN_DETECTION = "pattern_detection"
    PREPARATORY_TASK = "preparatory_task"
    HUMAN_REVIEW = "human_review"


class GPAIThreshold(str, Enum):
    """Compute thresholds for General Purpose AI classification (Art.53, 55).

    References:
    - Art.53(1)(a): GPAI if >= 10^23 FLOPs training compute
    - Art.55(2)(a): Systemic risk if >= 10^25 FLOPs or Commission designation
    """

    BELOW_THRESHOLD = "below_threshold"
    ABOVE_10_23 = "above_10_23_flops"
    ABOVE_10_25 = "above_10_25_flops"


_ANNEX_III_SET = {c.value for c in AnnexIIICategory}


@dataclass
class ClassificationDetail:
    """Detailed breakdown of a risk classification decision."""

    risk_level: RiskLevel = RiskLevel.MINIMAL
    matched_categories: list[str] = field(default_factory=list)
    applied_exemptions: list[str] = field(default_factory=list)
    is_prohibited: bool = False
    is_gpai: bool = False
    has_systemic_risk: bool = False
    gpai_threshold: GPAIThreshold = GPAIThreshold.BELOW_THRESHOLD
    profiles_natural_persons: bool = False
    reasons: list[str] = field(default_factory=list)


class RiskClassifier:
    """Classifies AI systems according to EU AI Act risk tiers (Art.6-7)."""

    def classify(
        self,
        categories: list[AnnexIIICategory | str],
        is_prohibited: bool = False,
        exemptions: list[ExemptionReason | str] | None = None,
        profiles_natural_persons: bool = False,
        compute_threshold: GPAIThreshold = GPAIThreshold.BELOW_THRESHOLD,
        is_generative: bool = False,
        is_chatbot_or_deepfake: bool = False,
    ) -> RiskLevel:
        """Classify an AI system's risk level.

        Args:
            categories: Annex III categories the system falls under.
            is_prohibited: Whether the system engages in prohibited practices (Art.5).
            exemptions: Art.6(3) exemption reasons.
            profiles_natural_persons: Whether the system profiles natural persons
                (exemptions don't apply if True).
            compute_threshold: Training compute threshold for GPAI classification.
            is_generative: Whether the model has generative capabilities.
            is_chatbot_or_deepfake: Whether the system is a chatbot or generates
                deepfakes (triggers Art.50 transparency).

        Returns:
            The final RiskLevel classification.
        """
        detail = self.classify_with_details(
            categories=categories,
            is_prohibited=is_prohibited,
            exemptions=exemptions,
            profiles_natural_persons=profiles_natural_persons,
            compute_threshold=compute_threshold,
            is_generative=is_generative,
            is_chatbot_or_deepfake=is_chatbot_or_deepfake,
        )
        return detail.risk_level

    def classify_with_details(
        self,
        categories: list[AnnexIIICategory | str],
        is_prohibited: bool = False,
        exemptions: list[ExemptionReason | str] | None = None,
        profiles_natural_persons: bool = False,
        compute_threshold: GPAIThreshold = GPAIThreshold.BELOW_THRESHOLD,
        is_generative: bool = False,
        is_chatbot_or_deepfake: bool = False,
    ) -> ClassificationDetail:
        """Classify with full detail of the decision-making process.

        Returns:
            ClassificationDetail with risk level and decision reasoning.
        """
        detail = ClassificationDetail(
            is_prohibited=is_prohibited,
            profiles_natural_persons=profiles_natural_persons,
            gpai_threshold=compute_threshold,
        )

        exemptions_list = [e.value if isinstance(e, ExemptionReason) else e for e in (exemptions or [])]
        str_categories = [c.value if isinstance(c, AnnexIIICategory) else c for c in categories]

        detail.matched_categories = [c for c in str_categories if c in _ANNEX_III_SET]
        detail.applied_exemptions = list(exemptions_list)

        # Prohibited practices (Art.5) — highest priority
        if is_prohibited:
            detail.risk_level = RiskLevel.UNACCEPTABLE
            detail.reasons.append("System engages in prohibited practices under Art.5")
            return detail

        # GPAI with systemic risk (Art.55) — checked before high-risk
        if compute_threshold == GPAIThreshold.ABOVE_10_25:
            detail.risk_level = RiskLevel.GPAI_WITH_SYSTEMIC_RISK
            detail.is_gpai = True
            detail.has_systemic_risk = True
            detail.reasons.append("GPAI with systemic risk (>=10^25 FLOPs)")
            return detail

        # GPAI (Art.53)
        if compute_threshold == GPAIThreshold.ABOVE_10_23:
            detail.risk_level = RiskLevel.GPAI
            detail.is_gpai = True
            detail.reasons.append("GPAI model (>=10^23 FLOPs)")
            return detail

        # High-risk (Annex III + Art.6(3) exemptions)
        if detail.matched_categories:
            # Art.6(3): exemptions do not apply if profiling natural persons
            can_exempt = not profiles_natural_persons

            if can_exempt and exemptions_list:
                detail.risk_level = RiskLevel.MINIMAL
                detail.reasons.append(
                    f"Exempted from high-risk: {', '.join(exemptions_list)}"
                )
                # Even if exempted, check limited risk
                return detail

            detail.risk_level = RiskLevel.HIGH
            detail.reasons.append(
                f"Annex III categories matched: {', '.join(detail.matched_categories)}"
            )
            return detail

        # Limited risk (Art.50) — chatbots, deepfakes
        if is_chatbot_or_deepfake:
            detail.risk_level = RiskLevel.LIMITED
            detail.reasons.append("Chatbot or deepfake system — Art.50 transparency")
            return detail

        # Default: minimal risk
        detail.risk_level = RiskLevel.MINIMAL
        detail.reasons.append("No risk factors identified")
        return detail
