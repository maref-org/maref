"""Tests for EU AI Act Fundamental Rights Impact Assessment (Art.27)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.fria import (
    FRIAManager,
    FRIAReport,
    FRIAScope,
    FundamentalRightAssessment,
)
from maref.compliance.eu_ai_act_v2.fria import FundamentalRight as FundamentalRight
from maref.compliance.eu_ai_act_v2.fria import RiskRating as RiskRating


class TestFundamentalRight:
    def test_all_12_rights_defined(self) -> None:
        assert len(FundamentalRight) == 12

    def test_values_unique(self) -> None:
        values = [r.value for r in FundamentalRight]
        assert len(values) == len(set(values))

    def test_human_dignity_value(self) -> None:
        assert FundamentalRight.HUMAN_DIGNITY.value == "human_dignity"

    def test_privacy_value(self) -> None:
        assert FundamentalRight.PRIVACY.value == "privacy"

    def test_non_discrimination_value(self) -> None:
        assert FundamentalRight.NON_DISCRIMINATION.value == "non_discrimination"

    def test_equality_value(self) -> None:
        assert FundamentalRight.EQUALITY.value == "equality"

    def test_access_to_justice_value(self) -> None:
        assert FundamentalRight.ACCESS_TO_JUSTICE.value == "access_to_justice"

    def test_fair_trial_value(self) -> None:
        assert FundamentalRight.FAIR_TRIAL.value == "fair_trial"

    def test_data_protection_value(self) -> None:
        assert FundamentalRight.DATA_PROTECTION.value == "data_protection"

    def test_freedom_expression_value(self) -> None:
        assert FundamentalRight.FREEDOM_EXPRESSION.value == "freedom_expression"

    def test_freedom_assembly_value(self) -> None:
        assert FundamentalRight.FREEDOM_ASSEMBLY.value == "freedom_assembly"

    def test_worker_rights_value(self) -> None:
        assert FundamentalRight.WORKER_RIGHTS.value == "worker_rights"

    def test_childrens_rights_value(self) -> None:
        assert FundamentalRight.CHILDRENS_RIGHTS.value == "childrens_rights"

    def test_environmental_protection_value(self) -> None:
        assert FundamentalRight.ENVIRONMENTAL_PROTECTION.value == "environmental_protection"


class TestRiskRating:
    def test_all_5_ratings_defined(self) -> None:
        assert len(RiskRating) == 5

    def test_values_unique(self) -> None:
        values = [r.value for r in RiskRating]
        assert len(values) == len(set(values))

    def test_negligible_value(self) -> None:
        assert RiskRating.NEGLIGIBLE.value == "negligible"

    def test_low_value(self) -> None:
        assert RiskRating.LOW.value == "low"

    def test_medium_value(self) -> None:
        assert RiskRating.MEDIUM.value == "medium"

    def test_high_value(self) -> None:
        assert RiskRating.HIGH.value == "high"

    def test_critical_value(self) -> None:
        assert RiskRating.CRITICAL.value == "critical"


class TestFRIAScope:
    def test_create_with_all_fields(self) -> None:
        scope = FRIAScope(
            system_name="FacialRecog-v2",
            system_version="2.1.0",
            deployment_context="Public surveillance in transport hubs",
            affected_population_description="Commuters and bystanders in EU train stations",
            estimated_affected_count=5000000,
            jurisdictions=["DE", "FR", "IT", "ES"],
        )
        assert scope.system_name == "FacialRecog-v2"
        assert scope.system_version == "2.1.0"
        assert scope.deployment_context == "Public surveillance in transport hubs"
        assert scope.affected_population_description == "Commuters and bystanders in EU train stations"
        assert scope.estimated_affected_count == 5000000
        assert scope.jurisdictions == ["DE", "FR", "IT", "ES"]

    def test_create_with_minimal_fields(self) -> None:
        scope = FRIAScope(
            system_name="Minimal",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test group",
        )
        assert scope.system_name == "Minimal"
        assert scope.estimated_affected_count == 0
        assert scope.jurisdictions == []

    def test_zero_affected_population(self) -> None:
        scope = FRIAScope(
            system_name="Zero",
            system_version="1.0",
            deployment_context="Internal",
            affected_population_description="No one",
            estimated_affected_count=0,
        )
        assert scope.estimated_affected_count == 0

    def test_missing_jurisdictions(self) -> None:
        scope = FRIAScope(
            system_name="NoJuris",
            system_version="1.0",
            deployment_context="Global",
            affected_population_description="All",
        )
        assert scope.jurisdictions == []


class TestFundamentalRightAssessment:
    def test_create_with_all_fields(self) -> None:
        assessment = FundamentalRightAssessment(
            right=FundamentalRight.PRIVACY,
            risk_rating=RiskRating.HIGH,
            rationale="System processes biometric data without consent",
            mitigation_measures=[
                "Anonymise biometric embeddings at rest",
                "Implement opt-out mechanism",
            ],
            residual_risk=RiskRating.LOW,
        )
        assert assessment.right == FundamentalRight.PRIVACY
        assert assessment.risk_rating == RiskRating.HIGH
        assert len(assessment.mitigation_measures) == 2
        assert assessment.residual_risk == RiskRating.LOW

    def test_create_with_default_residual_risk(self) -> None:
        assessment = FundamentalRightAssessment(
            right=FundamentalRight.EQUALITY,
            risk_rating=RiskRating.MEDIUM,
            rationale="Potential algorithmic bias",
        )
        assert assessment.residual_risk == RiskRating.NEGLIGIBLE
        assert assessment.mitigation_measures == []

    def test_create_without_mitigations(self) -> None:
        assessment = FundamentalRightAssessment(
            right=FundamentalRight.HUMAN_DIGNITY,
            risk_rating=RiskRating.CRITICAL,
            rationale="System enables mass surveillance",
        )
        assert assessment.mitigation_measures == []


class TestFRIAReport:
    def test_report_dataclass_construction(self) -> None:
        scope = FRIAScope(
            system_name="TestSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test",
        )
        assessments = [
            FundamentalRightAssessment(
                right=FundamentalRight.PRIVACY,
                risk_rating=RiskRating.HIGH,
                rationale="Test",
            ),
        ]
        report = FRIAReport(
            report_id="FRIA-001",
            scope=scope,
            assessments=assessments,
            overall_risk=RiskRating.HIGH,
            generated_at="2026-07-11T12:00:00",
            next_review_at="2026-10-11T12:00:00",
            reviewed_by="Dr. Compliance",
        )
        assert report.report_id == "FRIA-001"
        assert report.scope is scope
        assert len(report.assessments) == 1
        assert report.overall_risk == RiskRating.HIGH
        assert report.generated_at == "2026-07-11T12:00:00"
        assert report.next_review_at == "2026-10-11T12:00:00"
        assert report.reviewed_by == "Dr. Compliance"

    def test_report_empty_review_by_default(self) -> None:
        scope = FRIAScope(
            system_name="TestSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test",
        )
        report = FRIAReport(
            report_id="FRIA-002",
            scope=scope,
            assessments=[],
            overall_risk=RiskRating.LOW,
            generated_at="2026-07-11T12:00:00",
        )
        assert report.reviewed_by == ""
        assert report.next_review_at == ""


class TestFRIAManager:
    def test_initialise(self) -> None:
        manager = FRIAManager()
        assert manager._scope is None
        assert manager._assessments == []

    def test_set_scope(self) -> None:
        manager = FRIAManager()
        scope = FRIAScope(
            system_name="TestSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test",
        )
        result = manager.set_scope(scope)
        assert result is scope
        assert manager._scope is scope

    def test_assess_right(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="TestSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test",
        ))
        assessment = manager.assess_right(
            right=FundamentalRight.PRIVACY,
            rating=RiskRating.HIGH,
            rationale="Biometric data processing",
            mitigations=["Anonymise data"],
        )
        assert assessment.right == FundamentalRight.PRIVACY
        assert assessment.risk_rating == RiskRating.HIGH
        assert assessment.mitigation_measures == ["Anonymise data"]
        assert len(manager._assessments) == 1

    def test_assess_right_no_mitigations(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="TestSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="Test",
        ))
        assessment = manager.assess_right(
            right=FundamentalRight.EQUALITY,
            rating=RiskRating.MEDIUM,
            rationale="Potential bias",
        )
        assert assessment.mitigation_measures == []

    def test_assess_right_all_12_rights(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="FullTest",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="All",
        ))
        for right in FundamentalRight:
            manager.assess_right(
                right=right,
                rating=RiskRating.LOW,
                rationale=f"Assessment for {right.value}",
            )
        assert len(manager._assessments) == 12

    def test_generate_report_overall_risk_max_strategy(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="MaxTest",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="All",
        ))
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Low risk")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.HIGH, "High risk")
        manager.assess_right(FundamentalRight.HUMAN_DIGNITY, RiskRating.MEDIUM, "Medium")
        report = manager.generate_report()
        assert report.overall_risk == RiskRating.HIGH

    def test_generate_report_overall_risk_critical_wins(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="CriticalTest",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="All",
        ))
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Low")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.CRITICAL, "Critical")
        manager.assess_right(FundamentalRight.HUMAN_DIGNITY, RiskRating.HIGH, "High")
        report = manager.generate_report()
        assert report.overall_risk == RiskRating.CRITICAL

    def test_generate_report_all_negligible(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="SafeSys",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="All",
        ))
        for right in FundamentalRight:
            manager.assess_right(right, RiskRating.NEGLIGIBLE, "No risk")
        report = manager.generate_report()
        assert report.overall_risk == RiskRating.NEGLIGIBLE

    def test_generate_report_without_explicit_scope(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        report = manager.generate_report()
        assert report.overall_risk == RiskRating.LOW

    def test_generate_report_contains_scope(self) -> None:
        manager = FRIAManager()
        scope = FRIAScope(
            system_name="ScopeCheck",
            system_version="2.0",
            deployment_context="Test deploy",
            affected_population_description="Workers",
        )
        manager.set_scope(scope)
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.MEDIUM, "Test")
        report = manager.generate_report()
        assert report.scope is scope
        assert report.scope.system_name == "ScopeCheck"

    def test_generate_report_default_scope(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.WORKER_RIGHTS, RiskRating.LOW, "Test")
        report = manager.generate_report()
        assert report.scope.system_name == ""
        assert report.scope.system_version == ""

    def test_generate_report_sets_generated_at(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        report = manager.generate_report()
        assert len(report.generated_at) > 0
        assert "T" in report.generated_at

    def test_generate_report_sets_report_id(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        report = manager.generate_report()
        assert len(report.report_id) > 0
        assert isinstance(report.report_id, str)
        assert report.report_id.startswith("FRIA-")

    def test_generate_report_with_reviewed_by(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        report = manager.generate_report(reviewed_by="Reviewer Alpha")
        assert report.reviewed_by == "Reviewer Alpha"

    def test_generate_report_empty_reviewed_by(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        report = manager.generate_report()
        assert report.reviewed_by == ""

    def test_get_high_risk_rights_filters_correctly(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.HIGH, "High")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.CRITICAL, "Critical")
        manager.assess_right(FundamentalRight.HUMAN_DIGNITY, RiskRating.MEDIUM, "Medium")
        manager.assess_right(FundamentalRight.WORKER_RIGHTS, RiskRating.LOW, "Low")
        manager.assess_right(FundamentalRight.DATA_PROTECTION, RiskRating.NEGLIGIBLE, "None")
        high_risks = manager.get_high_risk_rights()
        rights_found = {a.right for a in high_risks}
        assert FundamentalRight.PRIVACY in rights_found
        assert FundamentalRight.EQUALITY in rights_found
        assert FundamentalRight.HUMAN_DIGNITY not in rights_found
        assert FundamentalRight.WORKER_RIGHTS not in rights_found
        assert FundamentalRight.DATA_PROTECTION not in rights_found

    def test_get_high_risk_rights_empty_when_none(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Low")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.MEDIUM, "Medium")
        result = manager.get_high_risk_rights()
        assert result == []

    def test_get_high_risk_rights_no_assessments(self) -> None:
        manager = FRIAManager()
        assert manager.get_high_risk_rights() == []

    def test_get_fria_summary_basic_structure(self) -> None:
        manager = FRIAManager()
        manager.set_scope(FRIAScope(
            system_name="SummaryTest",
            system_version="1.0",
            deployment_context="Test",
            affected_population_description="All",
            jurisdictions=["EU"],
        ))
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.HIGH, "High risk")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.LOW, "Low risk")
        summary = manager.get_fria_summary()
        assert summary["system_name"] == "SummaryTest"
        assert summary["system_version"] == "1.0"
        assert summary["overall_risk"] == RiskRating.HIGH.value
        assert summary["total_assessments"] == 2
        assert summary["high_risk_count"] == 1
        assert summary["jurisdictions"] == ["EU"]
        assert "report_id" in summary
        assert "generated_at" in summary

    def test_get_fria_summary_without_scope(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "Test")
        summary = manager.get_fria_summary()
        assert summary["system_name"] == ""
        assert summary["overall_risk"] == RiskRating.LOW.value
        assert summary["total_assessments"] == 1
        assert summary["high_risk_count"] == 0

    def test_get_fria_summary_no_assessments(self) -> None:
        manager = FRIAManager()
        summary = manager.get_fria_summary()
        assert summary["overall_risk"] == RiskRating.NEGLIGIBLE.value
        assert summary["total_assessments"] == 0
        assert summary["high_risk_count"] == 0

    def test_assess_high_risk_without_mitigations(self) -> None:
        manager = FRIAManager()
        manager.assess_right(
            right=FundamentalRight.PRIVACY,
            rating=RiskRating.HIGH,
            rationale="No mitigations yet",
        )
        high_risks = manager.get_high_risk_rights()
        assert len(high_risks) == 1
        assert high_risks[0].mitigation_measures == []

    def test_assess_risk_each_rating_level(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.NEGLIGIBLE, "N")
        manager.assess_right(FundamentalRight.EQUALITY, RiskRating.LOW, "L")
        manager.assess_right(FundamentalRight.HUMAN_DIGNITY, RiskRating.MEDIUM, "M")
        manager.assess_right(FundamentalRight.DATA_PROTECTION, RiskRating.HIGH, "H")
        manager.assess_right(FundamentalRight.FAIR_TRIAL, RiskRating.CRITICAL, "C")
        report = manager.generate_report()
        assert report.overall_risk == RiskRating.CRITICAL

    def test_generate_report_preserves_assessments(self) -> None:
        manager = FRIAManager()
        a1 = manager.assess_right(FundamentalRight.PRIVACY, RiskRating.HIGH, "One")
        a2 = manager.assess_right(FundamentalRight.EQUALITY, RiskRating.MEDIUM, "Two")
        report = manager.generate_report()
        assert len(report.assessments) == 2
        assert a1 in report.assessments
        assert a2 in report.assessments

    def test_multiple_assessments_same_right(self) -> None:
        manager = FRIAManager()
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.LOW, "First")
        manager.assess_right(FundamentalRight.PRIVACY, RiskRating.HIGH, "Revised")
        report = manager.generate_report()
        assert len(report.assessments) == 2
        assert report.overall_risk == RiskRating.HIGH

    def test_mitigation_measures_tracked_per_assessment(self) -> None:
        manager = FRIAManager()
        a1 = manager.assess_right(
            FundamentalRight.PRIVACY,
            RiskRating.HIGH,
            "Privacy risk",
            mitigations=["Encryption", "Access control"],
        )
        a2 = manager.assess_right(
            FundamentalRight.EQUALITY,
            RiskRating.MEDIUM,
            "Bias risk",
            mitigations=["Bias audit"],
        )
        assert a1.mitigation_measures == ["Encryption", "Access control"]
        assert a2.mitigation_measures == ["Bias audit"]
