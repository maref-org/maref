from __future__ import annotations

from datetime import datetime

from maref.compliance.registry import (
    ComplianceCheckResult,
    ComplianceEngine,
    ComplianceRegistry,
    ComplianceRequirement,
    ComplianceStatus,
    Jurisdiction,
    Regulation,
    RegulationType,
    create_compliance_system,
)


class TestComplianceStatus:
    def test_values(self) -> None:
        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"
        assert ComplianceStatus.PENDING_REVIEW.value == "pending_review"


class TestComplianceRegistry:
    def test_init_creates_default_regulations(self) -> None:
        reg = ComplianceRegistry()
        assert len(reg.regulations) >= 6
        assert "gdpr" in reg.regulations
        assert "ccpa" in reg.regulations
        assert "csl" in reg.regulations
        assert "eu-ai-act" in reg.regulations

    def test_init_creates_jurisdiction_rules(self) -> None:
        reg = ComplianceRegistry()
        assert Jurisdiction.EU in reg.jurisdiction_rules
        assert Jurisdiction.CHINA in reg.jurisdiction_rules
        assert reg.jurisdiction_rules[Jurisdiction.EU]["breach_notification_hours"] == 72
        assert reg.jurisdiction_rules[Jurisdiction.CHINA]["breach_notification_hours"] == 24

    def test_register_requirement(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-test-1",
            regulation_id="gdpr",
            name="Test Requirement",
            description="Test description",
            jurisdiction=Jurisdiction.EU,
        )
        rid = reg.register_requirement(req)
        assert rid == "req-test-1"
        assert reg.requirements["req-test-1"] == req

    def test_record_check_result_updates_requirement(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-test-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
        )
        reg.register_requirement(req)

        result = ComplianceCheckResult(
            result_id="res-1",
            requirement_id="req-test-1",
            status=ComplianceStatus.COMPLIANT,
            checked_at=datetime.now(),
            checked_by="tester",
            score=100.0,
        )
        reg.record_check_result(result)
        assert reg.requirements["req-test-1"].status == ComplianceStatus.COMPLIANT
        assert reg.requirements["req-test-1"].checked_at is not None

    def test_get_jurisdiction_compliance_status_no_requirements(self) -> None:
        reg = ComplianceRegistry()
        status = reg.get_jurisdiction_compliance_status(Jurisdiction.EU)
        assert status["compliance_rate"] == 0.0
        assert status["status"] == ComplianceStatus.PENDING_REVIEW.value
        assert status["active_regulations"] > 0

    def test_get_jurisdiction_compliance_status_with_data(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
            status=ComplianceStatus.COMPLIANT,
        )
        reg.register_requirement(req)
        status = reg.get_jurisdiction_compliance_status(Jurisdiction.EU)
        assert status["compliance_rate"] == 100.0
        assert status["compliant_count"] == 1
        assert status["status"] == ComplianceStatus.COMPLIANT.value

    def test_generate_compliance_report(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
            status=ComplianceStatus.COMPLIANT,
        )
        reg.register_requirement(req)
        report = reg.generate_compliance_report()
        assert report["total_regulations"] == len(reg.regulations)
        assert report["jurisdiction_count"] > 0
        assert "recommendations" in report
        assert "generated_at" in report

    def test_generate_compliance_report_with_specific_jurisdictions(self) -> None:
        reg = ComplianceRegistry()
        report = reg.generate_compliance_report(jurisdictions=[Jurisdiction.EU])
        assert report["jurisdiction_count"] == 1
        assert "eu" in report["jurisdictions"]

    def test_regulation_has_penalties(self) -> None:
        reg = ComplianceRegistry()
        assert "turnover" in reg.regulations["gdpr"].penalty.lower()
        assert "rmb" in reg.regulations["csl"].penalty.lower()

    def test_ccpa_has_consumer_rights(self) -> None:
        reg = ComplianceRegistry()
        assert "consumer_rights" in reg.regulations["ccpa"].requirements


class TestComplianceEngine:
    def test_evaluate_existing_requirement_with_evidence(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
        )
        reg.register_requirement(req)
        engine = ComplianceEngine(reg)
        result = engine.evaluate_compliance("req-1", ["evidence-1", "evidence-2"])
        assert result.status == ComplianceStatus.COMPLIANT
        assert result.score == 100.0
        assert result.checked_by == "system"

    def test_evaluate_existing_requirement_without_evidence(self) -> None:
        reg = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
        )
        reg.register_requirement(req)
        engine = ComplianceEngine(reg)
        result = engine.evaluate_compliance("req-1", [])
        assert result.status == ComplianceStatus.NON_COMPLIANT
        assert result.score == 0.0

    def test_evaluate_nonexistent_requirement(self) -> None:
        reg = ComplianceRegistry()
        engine = ComplianceEngine(reg)
        result = engine.evaluate_compliance("nonexistent", ["evidence"])
        assert result.status == ComplianceStatus.NOT_APPLICABLE
        assert "not found" in result.findings[0].lower()

    def test_batch_evaluate(self) -> None:
        reg = ComplianceRegistry()
        for i in range(3):
            req = ComplianceRequirement(
                requirement_id=f"req-{i}",
                regulation_id="gdpr",
                name=f"Test {i}",
                description="Test",
                jurisdiction=Jurisdiction.EU,
                evidence=[f"ev-{i}"],
            )
            reg.register_requirement(req)
        engine = ComplianceEngine(reg)
        results = engine.batch_evaluate(Jurisdiction.EU)
        assert len(results) == 3
        assert all(r.status == ComplianceStatus.COMPLIANT for r in results)

    def test_batch_evaluate_all_jurisdictions(self) -> None:
        reg = ComplianceRegistry()
        engine = ComplianceEngine(reg)
        results = engine.batch_evaluate()
        assert len(results) == 0


class TestCreateComplianceSystem:
    def test_returns_registry_and_engine(self) -> None:
        registry, engine = create_compliance_system()
        assert isinstance(registry, ComplianceRegistry)
        assert isinstance(engine, ComplianceEngine)
        assert engine.registry is registry
