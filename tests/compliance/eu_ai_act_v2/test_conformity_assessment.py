"""Tests for EU AI Act conformity assessment (Art.43 + Annex VI/VII + Art.47-49)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.conformity_assessment import (
    CEMarking,
    ConformityAssessmentManager,
    ConformityAssessmentRecord,
    ConformityRoute,
    DeclarationStatus,
    EUDatabaseRegistration,
    EUDeclarationOfConformity,
    SubstantialModificationType,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    RiskLevel,
)


class TestConformityRoute:
    def test_internal_control_value(self) -> None:
        assert ConformityRoute.INTERNAL_CONTROL.value == "internal_control"

    def test_third_party_value(self) -> None:
        assert ConformityRoute.THIRD_PARTY.value == "third_party"

    def test_routes_distinct(self) -> None:
        assert ConformityRoute.INTERNAL_CONTROL is not ConformityRoute.THIRD_PARTY

    def test_all_routes_defined(self) -> None:
        assert len(ConformityRoute) == 2


class TestDeclarationStatus:
    def test_not_started_value(self) -> None:
        assert DeclarationStatus.NOT_STARTED.value == "not_started"

    def test_in_progress_value(self) -> None:
        assert DeclarationStatus.IN_PROGRESS.value == "in_progress"

    def test_completed_value(self) -> None:
        assert DeclarationStatus.COMPLETED.value == "completed"

    def test_all_statuses_defined(self) -> None:
        assert len(DeclarationStatus) == 3


class TestSubstantialModificationType:
    def test_all_types_defined(self) -> None:
        assert len(SubstantialModificationType) == 5

    def test_type_values_unique(self) -> None:
        values = [t.value for t in SubstantialModificationType]
        assert len(values) == len(set(values))

    def test_risk_scope_change(self) -> None:
        assert (
            SubstantialModificationType.RISK_SCOPE_CHANGE.value
            == "risk_scope_change"
        )

    def test_dataset_change(self) -> None:
        assert (
            SubstantialModificationType.DATASET_CHANGE.value == "dataset_change"
        )

    def test_intended_purpose_change(self) -> None:
        assert (
            SubstantialModificationType.INTENDED_PURPOSE_CHANGE.value
            == "intended_purpose_change"
        )

    def test_architecture_change(self) -> None:
        assert (
            SubstantialModificationType.ARCHITECTURE_CHANGE.value
            == "architecture_change"
        )

    def test_cybersecurity_revision(self) -> None:
        assert (
            SubstantialModificationType.CYBERSECURITY_REVISION.value
            == "cybersecurity_revision"
        )


class TestConformityAssessmentRecord:
    def test_default_construction(self) -> None:
        rec = ConformityAssessmentRecord()
        assert rec.system_name == ""
        assert rec.route == ConformityRoute.INTERNAL_CONTROL
        assert rec.status == DeclarationStatus.NOT_STARTED
        assert rec.assessed_at == ""
        assert rec.findings == []
        assert rec.certificate_id == ""

    def test_has_unique_assessment_id(self) -> None:
        rec1 = ConformityAssessmentRecord()
        rec2 = ConformityAssessmentRecord()
        assert rec1.assessment_id != rec2.assessment_id

    def test_full_construction(self) -> None:
        rec = ConformityAssessmentRecord(
            assessment_id="test-id",
            system_name="TestAI",
            route=ConformityRoute.THIRD_PARTY,
            status=DeclarationStatus.COMPLETED,
            assessed_at="2026-07-11T00:00:00Z",
            findings=["All clear"],
            certificate_id="decl-001",
        )
        assert rec.assessment_id == "test-id"
        assert rec.system_name == "TestAI"
        assert rec.route == ConformityRoute.THIRD_PARTY
        assert rec.status == DeclarationStatus.COMPLETED
        assert rec.findings == ["All clear"]
        assert rec.certificate_id == "decl-001"


class TestEUDeclarationOfConformity:
    def test_default_construction(self) -> None:
        decl = EUDeclarationOfConformity()
        assert decl.system_name == ""
        assert decl.ai_act_articles == []
        assert decl.harmonized_standards == []
        assert decl.issuer == ""
        assert decl.issued_at == ""
        assert decl.valid_until == ""

    def test_has_unique_declaration_id(self) -> None:
        d1 = EUDeclarationOfConformity()
        d2 = EUDeclarationOfConformity()
        assert d1.declaration_id != d2.declaration_id

    def test_full_construction(self) -> None:
        decl = EUDeclarationOfConformity(
            declaration_id="decl-001",
            system_name="TestAI",
            ai_act_articles=["Art.6", "Art.43"],
            harmonized_standards=["EN 12345"],
            issuer="TestAI Inc.",
            issued_at="2026-01-01T00:00:00Z",
            valid_until="2031-01-01T00:00:00Z",
        )
        assert decl.declaration_id == "decl-001"
        assert decl.system_name == "TestAI"
        assert "Art.6" in decl.ai_act_articles
        assert "EN 12345" in decl.harmonized_standards
        assert decl.issuer == "TestAI Inc."


class TestCEMarking:
    def test_default_construction(self) -> None:
        ce = CEMarking()
        assert ce.affixed is False
        assert ce.marking_id == ""
        assert ce.affixed_at == ""
        assert ce.assessment_id == ""

    def test_full_construction(self) -> None:
        ce = CEMarking(
            affixed=True,
            marking_id="CE-A1B2C3D4",
            affixed_at="2026-07-11T00:00:00Z",
            assessment_id="assess-001",
        )
        assert ce.affixed is True
        assert ce.marking_id == "CE-A1B2C3D4"
        assert ce.assessment_id == "assess-001"

    def test_issue_ce_marking(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="CEAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(record.assessment_id)
        assert declaration is not None
        ce = manager.issue_ce_marking(declaration.declaration_id)
        assert ce is not None
        assert ce.affixed is True
        assert ce.marking_id.startswith("CE-")
        assert ce.affixed_at != ""

    def test_issue_ce_marking_not_found(self) -> None:
        manager = ConformityAssessmentManager()
        ce = manager.issue_ce_marking("nonexistent")
        assert ce is None

    def test_ce_marking_links_to_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="LinkCE",
            route=ConformityRoute.THIRD_PARTY,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(record.assessment_id)
        assert declaration is not None
        ce = manager.issue_ce_marking(declaration.declaration_id)
        assert ce is not None
        assert ce.assessment_id == record.assessment_id


class TestEUDatabaseRegistration:
    def test_default_construction(self) -> None:
        reg = EUDatabaseRegistration()
        assert reg.system_name == ""
        assert reg.risk_level == ""
        assert reg.registration_date == ""
        assert reg.expiry_date == ""

    def test_has_unique_registration_id(self) -> None:
        r1 = EUDatabaseRegistration()
        r2 = EUDatabaseRegistration()
        assert r1.registration_id != r2.registration_id

    def test_full_construction(self) -> None:
        reg = EUDatabaseRegistration(
            registration_id="reg-001",
            system_name="TestAI",
            risk_level="high",
            registration_date="2026-01-01T00:00:00Z",
            expiry_date="2031-01-01T00:00:00Z",
        )
        assert reg.registration_id == "reg-001"
        assert reg.system_name == "TestAI"
        assert reg.risk_level == "high"

    def test_register_system(self) -> None:
        manager = ConformityAssessmentManager()
        reg = manager.register_in_eu_database(
            system_name="RegAI",
            risk_level="high",
        )
        assert reg.system_name == "RegAI"
        assert reg.risk_level == "high"
        assert reg.registration_date != ""
        assert reg.expiry_date != ""

    def test_register_duplicate_returns_existing(self) -> None:
        manager = ConformityAssessmentManager()
        reg1 = manager.register_in_eu_database(
            system_name="DupAI",
            risk_level="high",
        )
        reg2 = manager.register_in_eu_database(
            system_name="DupAI",
            risk_level="high",
        )
        assert reg1.registration_id == reg2.registration_id
        assert reg1 is reg2

    def test_register_multiple_systems(self) -> None:
        manager = ConformityAssessmentManager()
        reg1 = manager.register_in_eu_database(
            system_name="SystemA",
            risk_level="high",
        )
        reg2 = manager.register_in_eu_database(
            system_name="SystemB",
            risk_level="limited",
        )
        assert reg1.registration_id != reg2.registration_id


class TestRouteDetermination:
    def test_biometrics_no_standards_third_party(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
            categories=[AnnexIIICategory.BIOMETRICS],
            has_harmonized_standards=False,
        )
        assert route == ConformityRoute.THIRD_PARTY

    def test_biometrics_with_standards_internal(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
            categories=[AnnexIIICategory.BIOMETRICS],
            has_harmonized_standards=True,
        )
        assert route == ConformityRoute.INTERNAL_CONTROL

    def test_non_biometrics_high_risk_internal(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert route == ConformityRoute.INTERNAL_CONTROL

    def test_multiple_categories_biometrics_third_party(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
            categories=[
                AnnexIIICategory.BIOMETRICS,
                AnnexIIICategory.EDUCATION,
            ],
            has_harmonized_standards=False,
        )
        assert route == ConformityRoute.THIRD_PARTY

    def test_gpai_no_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(risk_level=RiskLevel.GPAI)
        assert route is None

    def test_gpai_systemic_no_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
        )
        assert route is None

    def test_unacceptable_no_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.UNACCEPTABLE,
        )
        assert route is None

    def test_limited_no_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(risk_level=RiskLevel.LIMITED)
        assert route is None

    def test_minimal_no_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(risk_level=RiskLevel.MINIMAL)
        assert route is None

    def test_force_third_party_voluntary(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
            categories=[AnnexIIICategory.EMPLOYMENT],
            force_third_party=True,
        )
        assert route == ConformityRoute.THIRD_PARTY

    def test_high_risk_no_categories_default_internal(self) -> None:
        manager = ConformityAssessmentManager()
        route = manager.determine_route(
            risk_level=RiskLevel.HIGH,
        )
        assert route == ConformityRoute.INTERNAL_CONTROL


class TestAssessmentLifecycle:
    def test_initiate_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="TestAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        assert record.system_name == "TestAI"
        assert record.route == ConformityRoute.INTERNAL_CONTROL
        assert record.status == DeclarationStatus.IN_PROGRESS
        assert record.assessment_id in manager._assessments  # type: ignore[attr-defined]

    def test_complete_assessment(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="TestAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        completed = manager.complete_assessment(
            record.assessment_id,
            findings=["System compliant", "No issues found"],
        )
        assert completed is not None
        assert completed.status == DeclarationStatus.COMPLETED
        assert "System compliant" in completed.findings
        assert completed.assessed_at != ""

    def test_complete_assessment_not_found(self) -> None:
        manager = ConformityAssessmentManager()
        result = manager.complete_assessment(
            assessment_id="nonexistent",
            findings=["test"],
        )
        assert result is None

    def test_complete_assessment_without_findings(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="TestAI",
            route=ConformityRoute.THIRD_PARTY,
        )
        completed = manager.complete_assessment(record.assessment_id)
        assert completed is not None
        assert completed.status == DeclarationStatus.COMPLETED
        assert completed.findings == []

    def test_full_lifecycle(self) -> None:
        """Initiate -> complete -> declare -> CE mark -> register."""
        manager = ConformityAssessmentManager()
        # Initiate
        record = manager.initiate_assessment(
            system_name="LifecycleAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        assert record.status == DeclarationStatus.IN_PROGRESS
        # Complete
        completed = manager.complete_assessment(
            record.assessment_id,
            findings=["All Art.9 requirements met"],
        )
        assert completed is not None
        assert completed.status == DeclarationStatus.COMPLETED
        # Declare
        declaration = manager.generate_declaration(
            record.assessment_id,
            issuer="LifecycleAI Inc.",
            harmonized_standards=["EN 12345"],
        )
        assert declaration is not None
        assert declaration.system_name == "LifecycleAI"
        assert "Art.47" in declaration.ai_act_articles
        assert declaration.issuer == "LifecycleAI Inc."
        # CE mark
        ce = manager.issue_ce_marking(declaration.declaration_id)
        assert ce is not None
        assert ce.affixed is True
        assert ce.marking_id.startswith("CE-")
        # Register
        reg = manager.register_in_eu_database(
            system_name="LifecycleAI",
            risk_level="high",
        )
        assert reg is not None
        assert reg.system_name == "LifecycleAI"
        assert reg.risk_level == "high"


class TestDeclaration:
    def test_generate_declaration(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="DeclAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(
            record.assessment_id,
            issuer="DeclAI Corp",
            harmonized_standards=["EN 12345", "EN 67890"],
        )
        assert declaration is not None
        assert declaration.system_name == "DeclAI"
        assert declaration.issuer == "DeclAI Corp"
        assert "EN 12345" in declaration.harmonized_standards
        assert declaration.issued_at != ""
        assert declaration.valid_until != ""

    def test_generate_declaration_before_complete(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="DeclAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        declaration = manager.generate_declaration(record.assessment_id)
        assert declaration is None

    def test_generate_declaration_not_found(self) -> None:
        manager = ConformityAssessmentManager()
        declaration = manager.generate_declaration("nonexistent")
        assert declaration is None

    def test_declaration_links_to_record(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="LinkAI",
            route=ConformityRoute.THIRD_PARTY,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(record.assessment_id)
        assert declaration is not None
        assert record.certificate_id == declaration.declaration_id


class TestSubstantialModification:
    def test_no_modification_returns_empty(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {
            "risk_scope": "high",
            "datasets": ["train_v1"],
            "intended_purpose": "screening",
            "architecture_summary": "transformer",
            "cybersecurity_measures": ["encryption"],
        }
        current = dict(previous)
        mods = manager.detect_substantial_modification(current, previous)
        assert mods == []

    def test_risk_scope_change(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {"risk_scope": "high"}
        current = {"risk_scope": "unacceptable"}
        mods = manager.detect_substantial_modification(current, previous)
        assert SubstantialModificationType.RISK_SCOPE_CHANGE in mods
        assert len(mods) == 1

    def test_dataset_change(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {"datasets": ["train_v1"]}
        current = {"datasets": ["train_v2"]}
        mods = manager.detect_substantial_modification(current, previous)
        assert SubstantialModificationType.DATASET_CHANGE in mods

    def test_intended_purpose_change(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {"intended_purpose": "screening"}
        current = {"intended_purpose": "scoring"}
        mods = manager.detect_substantial_modification(current, previous)
        assert SubstantialModificationType.INTENDED_PURPOSE_CHANGE in mods

    def test_architecture_change(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {"architecture_summary": "transformer"}
        current = {"architecture_summary": "cnn"}
        mods = manager.detect_substantial_modification(current, previous)
        assert SubstantialModificationType.ARCHITECTURE_CHANGE in mods

    def test_cybersecurity_revision(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {"cybersecurity_measures": ["encryption"]}
        current = {"cybersecurity_measures": ["encryption", "mfa"]}
        mods = manager.detect_substantial_modification(current, previous)
        assert SubstantialModificationType.CYBERSECURITY_REVISION in mods

    def test_multiple_changes_detected(self) -> None:
        manager = ConformityAssessmentManager()
        previous = {
            "risk_scope": "high",
            "intended_purpose": "screening",
            "architecture_summary": "transformer",
        }
        current = {
            "risk_scope": "unacceptable",
            "intended_purpose": "scoring",
            "architecture_summary": "transformer",
        }
        mods = manager.detect_substantial_modification(current, previous)
        assert len(mods) == 2
        assert SubstantialModificationType.RISK_SCOPE_CHANGE in mods
        assert SubstantialModificationType.INTENDED_PURPOSE_CHANGE in mods

    def test_missing_keys_treated_as_no_change(self) -> None:
        manager = ConformityAssessmentManager()
        previous: dict = {}
        current: dict = {}
        mods = manager.detect_substantial_modification(current, previous)
        assert mods == []


class TestConformityReport:
    def test_generate_report(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="ReportAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.complete_assessment(
            record.assessment_id,
            findings=["Compliant"],
        )
        report = manager.generate_conformity_report(record.assessment_id)
        assert "Conformity Assessment Report" in report
        assert "ReportAI" in report
        assert "Assessment ID" in report
        assert "Findings" in report
        assert "Compliant" in report

    def test_generate_report_not_found(self) -> None:
        manager = ConformityAssessmentManager()
        report = manager.generate_conformity_report("nonexistent")
        assert "ERROR" in report
        assert "not found" in report

    def test_report_includes_declaration_and_ce(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="FullReportAI",
            route=ConformityRoute.THIRD_PARTY,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(
            record.assessment_id,
            issuer="FullReport Inc.",
        )
        assert declaration is not None
        manager.issue_ce_marking(declaration.declaration_id)
        manager.register_in_eu_database("FullReportAI", "high")
        report = manager.generate_conformity_report(record.assessment_id)
        assert "EU Declaration of Conformity" in report
        assert "CE Marking" in report
        assert "EU Database Registration" in report
        assert "FullReport Inc." in report


class TestAssessmentHistory:
    def test_get_assessment_history(self) -> None:
        manager = ConformityAssessmentManager()
        manager.initiate_assessment(
            system_name="HistAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.initiate_assessment(
            system_name="HistAI",
            route=ConformityRoute.THIRD_PARTY,
        )
        history = manager.get_assessment_history("HistAI")
        assert len(history) == 2

    def test_get_assessment_history_empty(self) -> None:
        manager = ConformityAssessmentManager()
        history = manager.get_assessment_history("NonexistentAI")
        assert history == []

    def test_assessment_history_filters_by_name(self) -> None:
        manager = ConformityAssessmentManager()
        manager.initiate_assessment(
            system_name="SystemA",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.initiate_assessment(
            system_name="SystemB",
            route=ConformityRoute.THIRD_PARTY,
        )
        history = manager.get_assessment_history("SystemA")
        assert len(history) == 1
        assert history[0].system_name == "SystemA"


class TestEdgeCases:
    def test_empty_findings_accepted(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="EmptyFindingsAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        completed = manager.complete_assessment(record.assessment_id, [])
        assert completed is not None
        assert completed.findings == []

    def test_generate_declaration_without_standards(self) -> None:
        manager = ConformityAssessmentManager()
        record = manager.initiate_assessment(
            system_name="NoStdAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        manager.complete_assessment(record.assessment_id)
        declaration = manager.generate_declaration(
            record.assessment_id,
            issuer="NoStd Corp",
        )
        assert declaration is not None
        assert declaration.harmonized_standards == []

    def test_assessment_history_ordered_by_initiation(self) -> None:
        manager = ConformityAssessmentManager()
        r1 = manager.initiate_assessment(
            system_name="OrderAI",
            route=ConformityRoute.INTERNAL_CONTROL,
        )
        r2 = manager.initiate_assessment(
            system_name="OrderAI",
            route=ConformityRoute.THIRD_PARTY,
        )
        history = manager.get_assessment_history("OrderAI")
        assert len(history) == 2
        assert history[0].assessment_id == r1.assessment_id
        assert history[1].assessment_id == r2.assessment_id

    def test_ce_marking_without_declaration(self) -> None:
        manager = ConformityAssessmentManager()
        ce = manager.issue_ce_marking("nonexistent-declaration")
        assert ce is None
