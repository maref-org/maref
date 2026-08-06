from __future__ import annotations

from maref.compliance.registry import ComplianceRegistry, ComplianceRequirement, ComplianceStatus, Jurisdiction
from maref.compliance.report_generator import (
    ComplianceReport,
    ReportFormat,
    ReportGenerator,
    ReportSection,
    ReportType,
    create_report_generator,
)


class TestReportSection:
    def test_to_markdown(self) -> None:
        section = ReportSection(title="Test Section", content="Test content")
        md = section.to_markdown(level=2)
        assert "## Test Section" in md
        assert "Test content" in md

    def test_to_markdown_with_subsections(self) -> None:
        sub = ReportSection(title="Sub Section", content="Sub content")
        section = ReportSection(title="Main", content="Main content", subsections=[sub])
        md = section.to_markdown()
        assert "### Sub Section" in md


class TestComplianceReport:
    def test_to_dict(self) -> None:
        report = ComplianceReport(
            report_id="report-1",
            report_type=ReportType.COMPLIANCE_STATUS,
            title="Test Report",
            generated_at=__import__("datetime").datetime.now(),
            jurisdiction=Jurisdiction.EU,
            metrics={"rate": 85.0},
        )
        d = report.to_dict()
        assert d["report_id"] == "report-1"
        assert d["type"] == "compliance_status"
        assert d["jurisdiction"] == "eu"

    def test_to_markdown(self) -> None:
        report = ComplianceReport(
            report_id="report-1",
            report_type=ReportType.COMPLIANCE_STATUS,
            title="Test Report",
            generated_at=__import__("datetime").datetime.now(),
            jurisdiction=Jurisdiction.EU,
            recommendations=[{"action": "Fix issue", "details": "Details here"}],
        )
        md = report.to_markdown()
        assert "# Test Report" in md
        assert "Recommendations" in md
        assert "Fix issue" in md


class TestReportGenerator:
    def setup_registry(self) -> ComplianceRegistry:
        registry = ComplianceRegistry()
        req = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Test",
            description="Test",
            jurisdiction=Jurisdiction.EU,
            status=ComplianceStatus.COMPLIANT,
        )
        registry.register_requirement(req)
        return registry

    def test_generate_compliance_status_report_all(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_compliance_status_report()
        assert report.report_type == ReportType.COMPLIANCE_STATUS
        assert report.jurisdiction is None
        assert report.metrics["total_jurisdictions"] > 0

    def test_generate_compliance_status_report_specific(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_compliance_status_report(Jurisdiction.EU)
        assert report.jurisdiction == Jurisdiction.EU

    def test_generate_audit_readiness_report(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_audit_readiness_report()
        assert report.report_type == ReportType.AUDIT_READINESS
        assert "SOC 2" in report.sections[0].title

    def test_generate_regulatory_submission(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_regulatory_submission("gdpr")
        assert report.report_type == ReportType.REGULATORY_SUBMISSION
        assert report.jurisdiction == Jurisdiction.EU
        assert report.metrics["regulation_id"] == "gdpr"

    def test_generate_regulatory_submission_unknown(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        import pytest
        with pytest.raises(ValueError):
            gen.generate_regulatory_submission("unknown_regulation")

    def test_generate_risk_assessment_report(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_risk_assessment_report()
        assert report.report_type == ReportType.RISK_ASSESSMENT
        assert report.metrics["total_risks_identified"] > 0

    def test_generate_executive_summary(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_executive_summary()
        assert report.report_type == ReportType.EXECUTIVE_SUMMARY
        assert "overall_compliance_rate" in report.metrics

    def test_export_report_markdown(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_compliance_status_report()
        output = gen.export_report(report, ReportFormat.MARKDOWN)
        assert report.title in output

    def test_export_report_json(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_compliance_status_report()
        output = gen.export_report(report, ReportFormat.JSON)
        assert isinstance(output, str)

    def test_export_report_html(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        report = gen.generate_compliance_status_report()
        output = gen.export_report(report, ReportFormat.HTML)
        assert "<html>" in output

    def test_get_report_history(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        gen.generate_compliance_status_report()
        gen.generate_audit_readiness_report()
        history = gen.get_report_history()
        assert len(history) == 2

    def test_batch_generate_all_reports(self) -> None:
        registry = self.setup_registry()
        gen = ReportGenerator(registry)
        reports = gen.batch_generate_all_reports()
        assert len(reports) >= 4


class TestCreateReportGenerator:
    def test_create(self) -> None:
        registry = ComplianceRegistry()
        gen = create_report_generator(registry)
        assert isinstance(gen, ReportGenerator)
