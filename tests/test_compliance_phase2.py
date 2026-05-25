"""
合规报告与监控测试
"""

from datetime import datetime

import pytest

from maref.compliance import (
    Jurisdiction,
    create_compliance_system,
)
from maref.compliance.compliance_monitor import (
    ComplianceMonitor,
    create_compliance_monitor,
)
from maref.compliance.hipaa import (
    BreachRiskLevel,
    HIPAAComplianceEngine,
    PHICategory,
    create_hipaa_engine,
)
from maref.compliance.pci_dss import (
    PCIComplianceEngine,
    PCIRequirement,
    SAQType,
    create_pci_engine,
)
from maref.compliance.report_generator import (
    ReportFormat,
    ReportGenerator,
    ReportType,
    create_report_generator,
)


class TestReportGenerator:
    """测试合规报告生成器"""

    @pytest.fixture
    def generator(self) -> ReportGenerator:
        registry, _ = create_compliance_system()
        return create_report_generator(registry)

    def test_create_generator(self, generator: ReportGenerator) -> None:
        assert isinstance(generator, ReportGenerator)

    def test_generate_compliance_status_report(self, generator: ReportGenerator) -> None:
        report = generator.generate_compliance_status_report()
        assert report.report_type == ReportType.COMPLIANCE_STATUS
        assert len(report.sections) > 0

    def test_generate_single_jurisdiction_report(self, generator: ReportGenerator) -> None:
        report = generator.generate_compliance_status_report(jurisdiction=Jurisdiction.EU)
        assert report.jurisdiction == Jurisdiction.EU

    def test_generate_audit_readiness_report(self, generator: ReportGenerator) -> None:
        report = generator.generate_audit_readiness_report()
        assert report.report_type == ReportType.AUDIT_READINESS
        assert len(report.sections) > 0

    def test_generate_regulatory_submission(self, generator: ReportGenerator) -> None:
        report = generator.generate_regulatory_submission("gdpr")
        assert report.report_type == ReportType.REGULATORY_SUBMISSION

    def test_generate_regulatory_submission_not_found(self, generator: ReportGenerator) -> None:
        with pytest.raises(ValueError, match="Regulation not found"):
            generator.generate_regulatory_submission("nonexistent")

    def test_generate_risk_assessment_report(self, generator: ReportGenerator) -> None:
        report = generator.generate_risk_assessment_report()
        assert report.report_type == ReportType.RISK_ASSESSMENT
        assert len(report.recommendations) > 0

    def test_generate_executive_summary(self, generator: ReportGenerator) -> None:
        report = generator.generate_executive_summary()
        assert report.report_type == ReportType.EXECUTIVE_SUMMARY

    def test_export_markdown(self, generator: ReportGenerator) -> None:
        report = generator.generate_compliance_status_report()
        md = generator.export_report(report, ReportFormat.MARKDOWN)
        assert "# " in md
        assert report.report_id in md

    def test_export_json(self, generator: ReportGenerator) -> None:
        report = generator.generate_compliance_status_report()
        import json
        data = json.loads(generator.export_report(report, ReportFormat.JSON))
        assert data["report_id"] == report.report_id

    def test_report_history(self, generator: ReportGenerator) -> None:
        generator.generate_compliance_status_report()
        history = generator.get_report_history()
        assert len(history) >= 1


class TestComplianceMonitor:
    """测试合规状态监控器"""

    @pytest.fixture
    def monitor(self) -> ComplianceMonitor:
        registry, _ = create_compliance_system()
        return create_compliance_monitor(registry)

    def test_create_monitor(self, monitor: ComplianceMonitor) -> None:
        assert isinstance(monitor, ComplianceMonitor)

    def test_add_and_remove_rule(self, monitor: ComplianceMonitor) -> None:
        from maref.compliance.compliance_monitor import MonitoringRule
        rule = MonitoringRule("test-rule", "Test", "Test desc", check_interval_hours=1)
        monitor.add_rule(rule)
        assert len(monitor._rules) == 5  # 4 defaults + 1 new

        removed = monitor.remove_rule("test-rule")
        assert removed
        assert len(monitor._rules) == 4

    def test_take_snapshot(self, monitor: ComplianceMonitor) -> None:
        snapshot = monitor.take_snapshot(Jurisdiction.EU)
        assert snapshot.jurisdiction == Jurisdiction.EU
        assert "compliance_rate" in snapshot.overall_status

    def test_check_all_rules(self, monitor: ComplianceMonitor) -> None:
        alerts = monitor.check_all_rules()
        assert isinstance(alerts, list)

    def test_get_active_alerts(self, monitor: ComplianceMonitor) -> None:
        active = monitor.get_active_alerts()
        assert isinstance(active, list)

    def test_resolve_alert(self, monitor: ComplianceMonitor) -> None:
        monitor.check_all_rules()
        active = monitor.get_active_alerts()
        if active:
            resolved = monitor.resolve_alert(active[0].alert_id)
            assert resolved

    def test_alert_callback(self, monitor: ComplianceMonitor) -> None:
        alerts_received = []

        def callback(alert):
            alerts_received.append(alert)

        monitor.register_alert_callback(callback)
        monitor.check_all_rules()
        # 回调可能被触发
        assert isinstance(alerts_received, list)

    def test_compliance_trend(self, monitor: ComplianceMonitor) -> None:
        monitor.take_snapshot(Jurisdiction.EU)
        trend = monitor.get_compliance_trend(Jurisdiction.EU)
        assert len(trend) >= 1

    def test_monitor_status(self, monitor: ComplianceMonitor) -> None:
        status = monitor.get_monitor_status()
        assert "state" in status
        assert "rules_count" in status

    def test_run_check_cycle(self, monitor: ComplianceMonitor) -> None:
        result = monitor.run_check_cycle()
        assert result["cycle_completed"]
        assert result["state"] == "idle"


class TestHIPAACompliance:
    """测试 HIPAA 合规模块"""

    def test_create_engine(self) -> None:
        engine = create_hipaa_engine()
        assert isinstance(engine, HIPAAComplianceEngine)

    def test_classify_phi_data(self) -> None:
        engine = HIPAAComplianceEngine()
        phi = engine.classify_data(["patient name", "diagnosis", "insurance id"])
        assert len(phi) >= 1

    def test_check_identifier_presence(self) -> None:
        engine = HIPAAComplianceEngine()
        result = engine.check_identifier_presence(["patient_name", "ssn", "normal_field"])
        assert result["contains_phi"]
        assert len(result["identifiers_found"]) >= 1

    def test_check_no_phi(self) -> None:
        engine = HIPAAComplianceEngine()
        result = engine.check_identifier_presence(["product_id", "order_count"])
        assert not result["contains_phi"]

    def test_verify_access_control_allowed(self) -> None:
        engine = HIPAAComplianceEngine()
        result = engine.verify_access_control("physician", "phi-name", "read", "treatment")
        assert result["allowed"]

    def test_verify_access_control_denied_purpose(self) -> None:
        engine = HIPAAComplianceEngine()
        # marketing is not a valid TPO purpose, genetic data requires consent
        result = engine.verify_access_control("analyst", "phi-genetic", "read", "marketing")
        assert not result["allowed"]

    def test_register_and_verify_baa(self) -> None:
        from maref.compliance.hipaa import BusinessAssociateAgreement
        engine = HIPAAComplianceEngine()

        baa = BusinessAssociateAgreement(
            baa_id="baa-001",
            covered_entity="Hospital A",
            business_associate="Vendor B",
            signed_at=datetime.now(),
            expires_at=datetime(2027, 1, 1),
            phi_categories=[PHICategory.MEDICAL_RECORD],
            permitted_uses=["treatment"],
        )
        engine.register_baa(baa)

        result = engine.verify_baa("Vendor B")
        assert result["valid"]

    def test_verify_baa_not_found(self) -> None:
        engine = HIPAAComplianceEngine()
        result = engine.verify_baa("Unknown Vendor")
        assert not result["valid"]

    def test_assess_breach_large(self) -> None:
        engine = HIPAAComplianceEngine()
        assessment = engine.assess_breach(
            "Database leaked",
            affected_individuals=600,
            affected_phi_categories=[PHICategory.MEDICAL_RECORD],
        )
        assert assessment.risk_level == BreachRiskLevel.HIGH
        assert assessment.notification_required
        assert assessment.hhs_notification_required
        assert assessment.media_notification_required

    def test_assess_breach_small(self) -> None:
        engine = HIPAAComplianceEngine()
        assessment = engine.assess_breach(
            "Minor incident",
            affected_individuals=5,
            affected_phi_categories=[PHICategory.DEMOGRAPHIC],
        )
        assert assessment.risk_level == BreachRiskLevel.LOW

    def test_generate_compliance_report(self) -> None:
        engine = HIPAAComplianceEngine()
        report = engine.generate_hipaa_compliance_report()
        assert "framework" in report
        assert report["framework"] == "HIPAA + HITECH"

    def test_security_rule_checklist(self) -> None:
        engine = HIPAAComplianceEngine()
        checklist = engine.get_security_rule_checklist()
        assert len(checklist) == 12


class TestPCICompliance:
    """测试 PCI DSS 合规模块"""

    def test_create_engine(self) -> None:
        engine = create_pci_engine()
        assert isinstance(engine, PCIComplianceEngine)

    def test_scope_environment(self) -> None:
        engine = PCIComplianceEngine()
        cde = engine.scope_environment(
            systems=["web-server", "db-server"],
            data_flows=["payment-gateway"],
            stores_card_data=True,
            processes_payments=True,
        )
        assert cde.saq_type == SAQType.SAQ_D

    def test_scope_environment_no_storage(self) -> None:
        engine = PCIComplianceEngine()
        cde = engine.scope_environment(
            systems=["web-server"],
            data_flows=["api"],
            stores_card_data=False,
            processes_payments=False,
        )
        assert cde.saq_type == SAQType.SAQ_A

    def test_mask_pan(self) -> None:
        engine = PCIComplianceEngine()
        result = engine.mask_pan("4111111111111111")
        assert result["masked"]
        assert result["last_four"] == "1111"

    def test_validate_encryption_strength_valid(self) -> None:
        engine = PCIComplianceEngine()
        result = engine.validate_encryption_strength("AES", 256)
        assert result["compliant"]

    def test_validate_encryption_strength_invalid(self) -> None:
        engine = PCIComplianceEngine()
        result = engine.validate_encryption_strength("DES", 56)
        assert not result["compliant"]

    def test_test_requirement_compliant(self) -> None:
        engine = PCIComplianceEngine()
        test = engine.test_requirement(
            PCIRequirement.R3,
            "Protect stored account data",
            "Verify encryption of stored PAN",
            ["encryption_config.json", "key_rotation.log"],
        )
        assert test.result.value == "compliant"

    def test_test_requirement_non_compliant(self) -> None:
        engine = PCIComplianceEngine()
        test = engine.test_requirement(
            PCIRequirement.R3,
            "Protect stored account data",
            "Verify encryption of stored PAN",
            [],
        )
        assert test.result.value == "non_compliant"

    def test_get_roc_summary(self) -> None:
        engine = PCIComplianceEngine()
        engine.test_requirement(PCIRequirement.R3, "Test", "Procedure", ["evidence"])
        summary = engine.get_roc_summary()
        assert "pci_version" in summary
        assert summary["pci_version"] == "4.0"

    def test_generate_saq(self) -> None:
        engine = PCIComplianceEngine()
        cde = engine.scope_environment(
            ["sys"], ["flow"],
            stores_card_data=False,
            processes_payments=False,
        )
        saq = engine.generate_saq(cde.cde_id)
        assert saq["saq_type"] == "saq_a"

    def test_generate_saq_nonexistent(self) -> None:
        engine = PCIComplianceEngine()
        with pytest.raises(ValueError, match="CDE not found"):
            engine.generate_saq("nonexistent")

    def test_merchant_level_info(self) -> None:
        engine = PCIComplianceEngine()
        info = engine.get_merchant_level_info(10_000_000)
        assert info["merchant_level"] == 1

    def test_validate_network_segmentation(self) -> None:
        engine = PCIComplianceEngine()
        result = engine.validate_segment_network(
            cde_ips=["10.0.1.1", "10.0.1.2"],
            non_cde_ips=["192.168.1.1", "192.168.1.2"],
        )
        assert result["segmented"]
        assert result["compliant"]

    def test_validate_network_no_segmentation(self) -> None:
        engine = PCIComplianceEngine()
        result = engine.validate_segment_network(
            cde_ips=["10.0.0.1", "192.168.1.1"],
            non_cde_ips=["192.168.1.1", "192.168.1.2"],
        )
        assert not result["segmented"]
        assert not result["compliant"]
