"""Tests for C1 bridge: auto-populate + exporter + audit evidence."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.annex_iv_exporter import AnnexIVExporter
from maref.compliance.eu_ai_act_v2.engine import EUAIComplianceEngineV2
from maref.compliance.eu_ai_act_v2.risk_classifier import AnnexIIICategory
from maref.compliance.eu_ai_act_v2.technical_docs import TechnicalDocumentation


class TestAutoPopulate:
    def test_auto_populate_fills_all_10_sections(self) -> None:
        engine = EUAIComplianceEngineV2(system_name="test", version="1.0.0")
        engine.auto_populate_documentation()
        validation = engine.technical_docs.validate_completeness()
        assert len(validation) == 0, f"Missing sections: {validation}"

    def test_auto_populate_section_1_general_description(self) -> None:
        engine = EUAIComplianceEngineV2(system_name="test", version="1.0.0")
        engine.auto_populate_documentation()
        doc = engine.technical_docs.generate()
        s1 = doc["section_1_general_description"]
        assert "system_type" in s1
        assert "risk_level" in s1
        assert s1["system_name"] == "test"

    def test_auto_populate_section_8_from_risk_mgmt(self) -> None:
        engine = EUAIComplianceEngineV2(system_name="test", version="1.0.0")
        engine.auto_populate_documentation()
        doc = engine.technical_docs.generate()
        s8 = doc["section_8_risk_management_system"]
        assert "state" in s8
        assert "risk_count" in s8

    def test_auto_populate_risk_level_matches_classifier(self) -> None:
        engine = EUAIComplianceEngineV2(system_name="test", version="1.0.0")
        engine.auto_populate_documentation(categories=["biometrics"])
        doc = engine.technical_docs.generate()
        assert doc["system_information"]["risk_classification"] != "not_classified"

    def test_engine_generate_summary_triggers_auto_populate(self) -> None:
        engine = EUAIComplianceEngineV2(system_name="test", version="1.0.0")
        summary = engine.generate_summary(categories=[])
        assert summary.documentation_complete
        assert len(summary.documentation_missing_fields) == 0


class TestAnnexIVExporter:
    def test_pdf_ready_html_has_title(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        exporter = AnnexIVExporter(doc)
        html = exporter.to_pdf_ready_html()
        assert "test" in html
        assert "Annex IV" in html
        assert "<!DOCTYPE html>" in html

    def test_regulatory_xml_has_schema(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        exporter = AnnexIVExporter(doc)
        xml = exporter.to_regulatory_xml()
        assert "<?xml" in xml
        assert "annex-iv" in xml
        assert "technical_documentation" in xml

    def test_docx_ready_xml_has_paragraphs(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        exporter = AnnexIVExporter(doc)
        docx = exporter.to_docx_ready_xml()
        assert "w:document" in docx
        assert "w:p" in docx

    def test_multi_format_has_all_keys(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        exporter = AnnexIVExporter(doc)
        result = exporter.export_multi_format()
        assert "json" in result
        assert "markdown" in result
        assert "pdf_ready_html" in result
        assert "regulatory_xml" in result
        assert "docx_ready_xml" in result

    def test_multi_format_includes_metadata(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        exporter = AnnexIVExporter(doc)
        result = exporter.export_multi_format()
        assert "test" in result["json"]


class TestAuditEvidence:
    def test_set_audit_evidence_appears_in_generate(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        doc.set_audit_evidence(
            merkle_root="abc123def456",
            evidence_ids=["ev-001", "ev-002"],
        )
        result = doc.generate()
        assert "audit_evidence" in result
        assert result["audit_evidence"]["merkle_root"] == "abc123def456"
        assert "ev-001" in result["audit_evidence"]["evidence_ids"]

    def test_audit_evidence_omitted_when_not_set(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        result = doc.generate()
        assert "audit_evidence" not in result

    def test_audit_evidence_in_markdown(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        doc.set_audit_evidence(merkle_root="abc123")
        md = doc.generate_markdown()
        assert "Merkle Anchor" in md
        assert "abc123" in md

    def test_audit_evidence_in_to_dict(self) -> None:
        doc = TechnicalDocumentation("test", "1.0", "purpose", "deployer")
        doc.set_audit_evidence(merkle_root="abc123", evidence_ids=["e1"])
        serialized = doc.to_dict()
        assert serialized["merkle_anchor"] == "abc123"
        assert serialized["evidence_ids"] == ["e1"]


class TestVersionInfo:
    def test_default_version_is_1(self) -> None:
        doc = TechnicalDocumentation("t", "1", "p", "d")
        assert doc.to_dict()["doc_version"] == 1

    def test_set_version(self) -> None:
        doc = TechnicalDocumentation("t", "1", "p", "d")
        doc.set_version_info(3)
        assert doc.to_dict()["doc_version"] == 3

    def test_version_in_metadata(self) -> None:
        doc = TechnicalDocumentation("t", "1", "p", "d")
        result = doc.generate()
        assert "doc_version" in result["document_metadata"]
