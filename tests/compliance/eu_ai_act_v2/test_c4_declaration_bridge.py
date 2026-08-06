"""Tests for C4 bridge: EU Declaration of Conformity + CE marking pipeline."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.conformity_assessment import (
    ConformityAssessmentManager,
    ConformityRoute,
    DeclarationStatus,
    SubstantialModificationType,
)
from maref.compliance.eu_ai_act_v2.engine import EUAIComplianceEngineV2
from maref.compliance.eu_ai_act_v2.risk_classifier import AnnexIIICategory, RiskLevel

# ------------------------------------------------------------------ #
# engine.generate_declaration_of_conformity()
# ------------------------------------------------------------------ #

class TestGenerateDeclarationOfConformity:
    def test_full_pipeline_high_risk(self) -> None:
        engine = EUAIComplianceEngineV2("test-system", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            issuer="MAREF Operator",
            categories=["biometrics"],
        )
        assert result["risk_level"] == "high"
        assert result["route"] == "third_party"
        assert result["assessment_id"] is not None
        assert result["declaration_id"] is not None
        assert result["ce_marking_id"] is not None
        assert result["registration_id"] is not None
        assert result["ce_eligible"] is True

    def test_no_route_for_low_risk(self) -> None:
        engine = EUAIComplianceEngineV2("low-risk", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            categories=[],
        )
        assert result["risk_level"] == "minimal"
        assert result["route"] is None
        assert result["ce_eligible"] is False
        assert "message" in result

    def test_declaration_validity_period(self) -> None:
        engine = EUAIComplianceEngineV2("validity-test", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            issuer="Operator",
            categories=["biometrics"],
        )
        assert result["declaration_valid_until"] is not None
        assert "T" in result["declaration_valid_until"]

    def test_registration_has_risk_level(self) -> None:
        engine = EUAIComplianceEngineV2("reg-test", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            categories=["biometrics"],
        )
        assert "registration_id" in result

    def test_ce_eligible_with_complete_state(self) -> None:
        engine = EUAIComplianceEngineV2("complete-test", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            categories=["biometrics"],
        )
        pre_check = result["ce_pre_check"]
        assert isinstance(pre_check, dict)
        assert "ce_eligible" in pre_check
        assert isinstance(pre_check["ce_eligible"], bool)

    def test_third_party_route_biometrics_no_standards(self) -> None:
        engine_prefilled = EUAIComplianceEngineV2("bio-system", "1.0.0")
        result = engine_prefilled.generate_declaration_of_conformity(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert result["risk_level"] == "high"


# ------------------------------------------------------------------ #
# CE pre-check independent tests
# ------------------------------------------------------------------ #

class TestCEPreCheck:
    def test_ce_pre_check_returns_dict(self) -> None:
        engine = EUAIComplianceEngineV2("precheck-test", "1.0.0")
        result = engine.generate_declaration_of_conformity(
            categories=["biometrics"],
        )
        pre_check = result["ce_pre_check"]
        for key in (
            "technical_documentation_complete",
            "risk_management_established",
            "quality_management_established",
            "post_market_monitoring_established",
            "ce_eligible",
        ):
            assert key in pre_check, f"Missing key: {key}"
            assert isinstance(pre_check[key], bool)


# ------------------------------------------------------------------ #
# ConformityAssessmentManager standalone lifecycle
# ------------------------------------------------------------------ #

class TestConformityAssessmentLifecycle:
    def test_full_lifecycle(self) -> None:
        mgr = ConformityAssessmentManager()
        route = mgr.determine_route(risk_level=RiskLevel.HIGH)
        assert route == ConformityRoute.INTERNAL_CONTROL

        record = mgr.initiate_assessment("sys", route)
        assert record.status == DeclarationStatus.IN_PROGRESS

        completed = mgr.complete_assessment(record.assessment_id, ["OK"])
        assert completed is not None
        assert completed.status == DeclarationStatus.COMPLETED

        declaration = mgr.generate_declaration(
            record.assessment_id, issuer="ME"
        )
        assert declaration is not None
        assert len(declaration.declaration_id) > 0

        ce = mgr.issue_ce_marking(declaration.declaration_id)
        assert ce is not None
        assert ce.affixed is True
        assert ce.marking_id.startswith("CE-")

        reg = mgr.register_in_eu_database("sys", "high")
        assert reg is not None
        assert len(reg.registration_id) > 0


# ------------------------------------------------------------------ #
# Substantial modification detection
# ------------------------------------------------------------------ #

class TestSubstantialModification:
    def test_no_modifications(self) -> None:
        mgr = ConformityAssessmentManager()
        current = {
            "risk_scope": "a",
            "datasets": "b",
            "intended_purpose": "c",
            "architecture_summary": "d",
            "cybersecurity_measures": "e",
        }
        previous = dict(current)
        mods = mgr.detect_substantial_modification(current, previous)
        assert mods == []

    def test_all_modifications(self) -> None:
        mgr = ConformityAssessmentManager()
        current = {k: str(i) for i, k in enumerate([
            "risk_scope", "datasets", "intended_purpose",
            "architecture_summary", "cybersecurity_measures",
        ])}
        previous = dict.fromkeys(current, "old")
        mods = mgr.detect_substantial_modification(current, previous)
        assert len(mods) == 5
        types = [m.value for m in mods]
        assert "risk_scope_change" in types
        assert "dataset_change" in types
        assert "intended_purpose_change" in types
        assert "architecture_change" in types
        assert "cybersecurity_revision" in types

    def test_single_modification(self) -> None:
        mgr = ConformityAssessmentManager()
        current = {
            "risk_scope": "new",
            "datasets": "same",
            "intended_purpose": "same",
            "architecture_summary": "same",
            "cybersecurity_measures": "same",
        }
        previous = dict.fromkeys(current, "same")
        previous["risk_scope"] = "old"
        mods = mgr.detect_substantial_modification(current, previous)
        assert len(mods) == 1
        assert mods[0] == SubstantialModificationType.RISK_SCOPE_CHANGE


# ------------------------------------------------------------------ #
# Assessment history and report
# ------------------------------------------------------------------ #

class TestAssessmentHistory:
    def test_history_empty(self) -> None:
        mgr = ConformityAssessmentManager()
        assert mgr.get_assessment_history("nonexistent") == []

    def test_history_returns_records(self) -> None:
        mgr = ConformityAssessmentManager()
        route = mgr.determine_route(RiskLevel.HIGH)
        mgr.initiate_assessment("sys", route)
        mgr.initiate_assessment("sys", route)
        history = mgr.get_assessment_history("sys")
        assert len(history) == 2

    def test_generate_report(self) -> None:
        mgr = ConformityAssessmentManager()
        route = mgr.determine_route(RiskLevel.HIGH)
        record = mgr.initiate_assessment("report-sys", route)
        mgr.complete_assessment(record.assessment_id, ["all good"])
        declaration = mgr.generate_declaration(record.assessment_id, "ME")
        assert declaration is not None
        mgr.issue_ce_marking(declaration.declaration_id)
        mgr.register_in_eu_database("report-sys", "high")
        report = mgr.generate_conformity_report(record.assessment_id)
        assert "Conformity Assessment Report" in report
        assert "EU Declaration of Conformity" in report
        assert "CE Marking" in report
        assert "EU Database Registration" in report

    def test_report_unknown_assessment(self) -> None:
        mgr = ConformityAssessmentManager()
        report = mgr.generate_conformity_report("nonexistent")
        assert "ERROR" in report
