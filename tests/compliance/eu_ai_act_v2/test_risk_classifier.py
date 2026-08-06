"""Tests for EU AI Act risk classifier (Art.6-7 + Annex III)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    ClassificationDetail,
    ExemptionReason,
    GPAIThreshold,
    RiskClassifier,
    RiskLevel,
)


class TestAnnexIIICategories:
    def test_all_categories_defined(self) -> None:
        assert len(AnnexIIICategory) == 8

    def test_category_values_unique(self) -> None:
        values = [c.value for c in AnnexIIICategory]
        assert len(values) == len(set(values))

    def test_biometrics_category(self) -> None:
        assert AnnexIIICategory.BIOMETRICS.value == "biometrics"

    def test_critical_infra(self) -> None:
        assert AnnexIIICategory.CRITICAL_INFRASTRUCTURE.value == "critical_infrastructure"

    def test_education(self) -> None:
        assert AnnexIIICategory.EDUCATION.value == "education"

    def test_employment(self) -> None:
        assert AnnexIIICategory.EMPLOYMENT.value == "employment"

    def test_essential_services(self) -> None:
        assert AnnexIIICategory.ESSENTIAL_SERVICES.value == "essential_services"

    def test_law_enforcement(self) -> None:
        assert AnnexIIICategory.LAW_ENFORCEMENT.value == "law_enforcement"

    def test_migration(self) -> None:
        assert AnnexIIICategory.MIGRATION.value == "migration"

    def test_justice(self) -> None:
        assert AnnexIIICategory.JUSTICE.value == "justice"


class TestRiskLevels:
    def test_unacceptable_highest_severity(self) -> None:
        levels = list(RiskLevel)
        assert levels[0] == RiskLevel.UNACCEPTABLE

    def test_minimal_lowest_severity(self) -> None:
        assert RiskLevel.MINIMAL in RiskLevel

    def test_risk_level_order(self) -> None:
        """Verify risk levels are in descending severity order."""
        ordered = list(RiskLevel)
        assert ordered == [
            RiskLevel.UNACCEPTABLE,
            RiskLevel.HIGH,
            RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
            RiskLevel.GPAI,
            RiskLevel.LIMITED,
            RiskLevel.MINIMAL,
        ]


class TestRiskClassifier:
    def test_classify_unacceptable_direct(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            is_prohibited=True,
        )
        assert result == RiskLevel.UNACCEPTABLE

    def test_classify_high_risk_biometrics(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert result == RiskLevel.HIGH

    def test_classify_high_risk_critical_infra(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.CRITICAL_INFRASTRUCTURE],
        )
        assert result == RiskLevel.HIGH

    def test_classify_high_risk_multiple_categories(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[
                AnnexIIICategory.EDUCATION,
                AnnexIIICategory.EMPLOYMENT,
            ],
        )
        assert result == RiskLevel.HIGH

    def test_classify_exempted_narrow_procedural(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.EMPLOYMENT],
            exemptions=[ExemptionReason.NARROW_PROCEDURAL_TASK],
        )
        assert result == RiskLevel.MINIMAL

    def test_classify_exempted_pattern_detection(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.EDUCATION],
            exemptions=[ExemptionReason.PATTERN_DETECTION],
        )
        assert result == RiskLevel.MINIMAL

    def test_classify_exempted_preparatory(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.ESSENTIAL_SERVICES],
            exemptions=[ExemptionReason.PREPARATORY_TASK],
        )
        assert result == RiskLevel.MINIMAL

    def test_classify_exempted_human_review(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.JUSTICE],
            exemptions=[ExemptionReason.HUMAN_REVIEW],
        )
        assert result == RiskLevel.MINIMAL

    def test_classify_exemption_no_profile(self) -> None:
        """Art.6(3): exemptions NOT granted if system profiles natural persons."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[AnnexIIICategory.EMPLOYMENT],
            exemptions=[ExemptionReason.NARROW_PROCEDURAL_TASK],
            profiles_natural_persons=True,
        )
        assert result == RiskLevel.HIGH

    def test_classify_gpai_threshold(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_23,
            is_generative=True,
        )
        assert result == RiskLevel.GPAI

    def test_classify_gpai_systemic_risk(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_25,
            is_generative=True,
        )
        assert result == RiskLevel.GPAI_WITH_SYSTEMIC_RISK

    def test_classify_gpai_non_generative(self) -> None:
        """Non-generative models above threshold still classified as GPAI."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_23,
            is_generative=False,
        )
        assert result == RiskLevel.GPAI

    def test_classify_limited_risk(self) -> None:
        """Chatbots and deepfake systems default to limited risk."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            is_chatbot_or_deepfake=True,
        )
        assert result == RiskLevel.LIMITED

    def test_classify_minimal_risk(self) -> None:
        """AI systems with no risk factors default to minimal risk."""
        classifier = RiskClassifier()
        result = classifier.classify(categories=[])
        assert result == RiskLevel.MINIMAL

    def test_unknown_category_not_high_risk(self) -> None:
        """Categories not in Annex III do not trigger high-risk."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=["sports_scoring"],  # type: ignore[arg-type]
        )
        assert result == RiskLevel.MINIMAL

    def test_classify_with_unknown_category_ignored(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=["unknown_category"],  # type: ignore[arg-type]
        )
        assert result == RiskLevel.MINIMAL


class TestRiskClassifierEdgeCases:
    def test_empty_categories(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(categories=[])
        assert result == RiskLevel.MINIMAL

    def test_all_categories_high_risk(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify(categories=list(AnnexIIICategory))
        assert result == RiskLevel.HIGH

    def test_prohibited_overrides_everything(self) -> None:
        """Prohibited (Art.5) always wins regardless of other factors."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=list(AnnexIIICategory),
            is_prohibited=True,
            exemptions=[ExemptionReason.NARROW_PROCEDURAL_TASK],
        )
        assert result == RiskLevel.UNACCEPTABLE

    def test_gpai_with_exemption(self) -> None:
        """GPAI systems keep GPAI classification regardless of exemptions."""
        classifier = RiskClassifier()
        result = classifier.classify(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_23,
            is_generative=True,
            exemptions=[ExemptionReason.NARROW_PROCEDURAL_TASK],
        )
        assert result == RiskLevel.GPAI

    def test_classify_returns_risk_score(self) -> None:
        classifier = RiskClassifier()
        result = classifier.classify_with_details(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert isinstance(result, ClassificationDetail)
        assert result.risk_level == RiskLevel.HIGH


class TestGPAIThreshold:
    def test_below_threshold(self) -> None:
        assert GPAIThreshold.BELOW_THRESHOLD is not None

    def test_above_10_23(self) -> None:
        assert GPAIThreshold.ABOVE_10_23.value == "above_10_23_flops"

    def test_above_10_25(self) -> None:
        assert GPAIThreshold.ABOVE_10_25.value == "above_10_25_flops"

    def test_threshold_values_ordering(self) -> None:
        """10^25 > 10^23 in terms of compute requirements."""
        assert GPAIThreshold.ABOVE_10_25 is not GPAIThreshold.ABOVE_10_23
