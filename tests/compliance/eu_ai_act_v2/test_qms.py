"""Tests for EU AI Act quality management system module (Art.17)."""

from __future__ import annotations

import pytest

from maref.compliance.eu_ai_act_v2.qms import (
    QMSAuditRecord,
    QMSDocument,
    QMSManager,
    QMSSection,
    QualityPolicy,
)


class TestQMSSection:
    def test_all_10_sections_defined(self) -> None:
        expected = [
            "compliance_strategy",
            "design_procedures",
            "review_validation",
            "testing",
            "data_governance",
            "risk_management",
            "post_market_monitoring",
            "incident_reporting",
            "record_keeping",
            "deployment_controls",
        ]
        values = [s.value for s in QMSSection]
        assert len(values) == 10
        for exp in expected:
            assert exp in values

    def test_section_value_returns_string(self) -> None:
        assert QMSSection.COMPLIANCE_STRATEGY.value == "compliance_strategy"
        assert QMSSection.DEPLOYMENT_CONTROLS.value == "deployment_controls"


class TestQMSDocument:
    def test_create_with_all_fields(self) -> None:
        doc = QMSDocument(
            doc_id="doc-001",
            title="Compliance Strategy v1",
            version="1.0.0",
            section=QMSSection.COMPLIANCE_STRATEGY.value,
            content="Our compliance strategy...",
            approved_by="alice",
            approved_at="2026-07-01T00:00:00",
            next_review_at="2027-07-01T00:00:00",
        )
        assert doc.doc_id == "doc-001"
        assert doc.title == "Compliance Strategy v1"
        assert doc.version == "1.0.0"
        assert doc.section == "compliance_strategy"
        assert doc.content == "Our compliance strategy..."
        assert doc.approved_by == "alice"
        assert doc.approved_at == "2026-07-01T00:00:00"
        assert doc.next_review_at == "2027-07-01T00:00:00"

    def test_default_fields(self) -> None:
        doc = QMSDocument(
            doc_id="doc-002",
            title="Test Document",
            version="1.0.0",
            section=QMSSection.TESTING.value,
            content="Test content",
        )
        assert doc.approved_by == ""
        assert doc.approved_at == ""
        assert doc.next_review_at == ""
        assert doc.superseded_by == ""

    def test_documents_with_all_10_sections(self) -> None:
        """Create documents covering all 10 Art.17(1) sections."""
        docs = []
        for section in QMSSection:
            doc = QMSDocument(
                doc_id=f"doc-{section.value}",
                title=f"{section.value} Document",
                version="1.0.0",
                section=section.value,
                content=f"Content for {section.value}",
            )
            docs.append(doc)
        assert len(docs) == 10
        sections = {d.section for d in docs}
        assert sections == {s.value for s in QMSSection}

    def test_document_without_approval(self) -> None:
        """Edge case: document without approval should have empty approval fields."""
        doc = QMSDocument(
            doc_id="doc-no-approval",
            title="Unapproved Doc",
            version="0.1.0",
            section=QMSSection.RISK_MANAGEMENT.value,
            content="Draft content",
        )
        assert doc.approved_by == ""
        assert doc.approved_at == ""


class TestQMSAuditRecord:
    def test_create_audit_record(self) -> None:
        audit = QMSAuditRecord(
            audit_id="audit-001",
            audit_date="2026-07-01",
            auditor="external-auditor-1",
            scope=["compliance_strategy", "risk_management"],
        )
        assert audit.audit_id == "audit-001"
        assert audit.audit_date == "2026-07-01"
        assert audit.auditor == "external-auditor-1"
        assert audit.scope == ["compliance_strategy", "risk_management"]
        assert audit.findings == []
        assert audit.overall_verdict == "conditional"

    def test_audit_with_findings(self) -> None:
        audit = QMSAuditRecord(
            audit_id="audit-002",
            audit_date="2026-07-01",
            auditor="internal-auditor",
            scope=["testing", "data_governance"],
            findings=[
                {
                    "area": "testing",
                    "severity": "medium",
                    "description": "Test coverage insufficient",
                    "corrective_action": "",
                    "status": "open",
                },
                {
                    "area": "data_governance",
                    "severity": "high",
                    "description": "Missing data provenance records",
                    "corrective_action": "",
                    "status": "open",
                },
            ],
            overall_verdict="non_compliant",
        )
        assert len(audit.findings) == 2
        assert audit.findings[0]["area"] == "testing"
        assert audit.findings[0]["status"] == "open"
        assert audit.overall_verdict == "non_compliant"

    def test_audit_full_lifecycle(self) -> None:
        """Create audit → add findings → close findings."""
        audit = QMSAuditRecord(
            audit_id="audit-003",
            audit_date="2026-06-15",
            auditor="qa-team",
            scope=["incident_reporting"],
            findings=[
                {
                    "area": "incident_reporting",
                    "severity": "low",
                    "description": "Template missing",
                    "corrective_action": "",
                    "status": "open",
                },
            ],
            overall_verdict="conditional",
        )
        assert audit.findings[0]["status"] == "open"

        # Close the finding
        audit.findings[0]["status"] = "closed"
        audit.findings[0]["corrective_action"] = "Template created and approved"
        assert audit.findings[0]["status"] == "closed"
        assert audit.findings[0]["corrective_action"] == "Template created and approved"

    def test_audit_with_zero_scope(self) -> None:
        """Edge case: audit with empty scope should still be valid."""
        audit = QMSAuditRecord(
            audit_id="audit-empty-scope",
            audit_date="2026-07-01",
            auditor="auditor",
            scope=[],
        )
        assert audit.scope == []
        assert audit.overall_verdict == "conditional"

    def test_audit_all_verdicts(self) -> None:
        for verdict in ("compliant", "non_compliant", "conditional"):
            audit = QMSAuditRecord(
                audit_id=f"audit-{verdict}",
                audit_date="2026-07-01",
                auditor="auditor",
                scope=["testing"],
                overall_verdict=verdict,
            )
            assert audit.overall_verdict == verdict


class TestQualityPolicy:
    def test_create_policy(self) -> None:
        policy = QualityPolicy(
            policy_id="pol-001",
            statements=["We commit to quality", "We follow Art.17"],
            review_cycle_days=365,
            last_reviewed_at="2026-01-01T00:00:00",
            next_review_at="2027-01-01T00:00:00",
        )
        assert policy.policy_id == "pol-001"
        assert len(policy.statements) == 2
        assert policy.review_cycle_days == 365
        assert policy.last_reviewed_at == "2026-01-01T00:00:00"
        assert policy.next_review_at == "2027-01-01T00:00:00"

    def test_default_review_cycle(self) -> None:
        policy = QualityPolicy(
            policy_id="pol-default",
            statements=["Quality first"],
        )
        assert policy.review_cycle_days == 365
        assert policy.last_reviewed_at == ""
        assert policy.next_review_at == ""

    def test_different_review_cycle(self) -> None:
        policy = QualityPolicy(
            policy_id="pol-180",
            statements=["Test"],
            review_cycle_days=180,
        )
        assert policy.review_cycle_days == 180

    def test_review_cycle_enforcement(self) -> None:
        """QualityPolicy should have review dates set when created via manager."""
        manager = QMSManager()
        policy = manager.set_quality_policy(
            statements=["Commitment to Art.17 compliance"],
            review_cycle_days=365,
        )
        assert policy.last_reviewed_at != ""
        assert policy.next_review_at != ""
        assert policy.review_cycle_days == 365


class TestQMSManager:
    def test_instantiate(self) -> None:
        manager = QMSManager()
        assert isinstance(manager, QMSManager)

    def test_create_document_returns_doc(self) -> None:
        manager = QMSManager()
        doc = manager.create_document(
            title="Risk Management Plan",
            section=QMSSection.RISK_MANAGEMENT.value,
            content="Risk management procedures...",
        )
        assert isinstance(doc, QMSDocument)
        assert doc.title == "Risk Management Plan"
        assert doc.section == "risk_management"
        assert doc.content == "Risk management procedures..."
        assert doc.doc_id != ""
        assert doc.version == "1.0.0"

    def test_create_document_with_kwargs(self) -> None:
        manager = QMSManager()
        doc = manager.create_document(
            title="Data Governance Policy",
            section=QMSSection.DATA_GOVERNANCE.value,
            content="Data governance procedures...",
            approved_by="alice",
            next_review_at="2027-01-01T00:00:00",
        )
        assert doc.approved_by == "alice"
        assert doc.next_review_at == "2027-01-01T00:00:00"

    def test_version_control_new_supersedes_old(self) -> None:
        """Creating a doc with same title creates new version, old is superseded."""
        manager = QMSManager()
        v1 = manager.create_document(
            title="Compliance Manual",
            section=QMSSection.COMPLIANCE_STRATEGY.value,
            content="Version 1 content",
        )
        assert v1.version == "1.0.0"
        assert v1.superseded_by == ""

        v2 = manager.create_document(
            title="Compliance Manual",
            section=QMSSection.COMPLIANCE_STRATEGY.value,
            content="Version 2 content",
        )
        assert v2.version == "2.0.0"
        assert v2.superseded_by == ""

        # v1 should now be superseded by v2
        assert v1.superseded_by == v2.doc_id

    def test_review_document_approve(self) -> None:
        manager = QMSManager()
        doc = manager.create_document(
            title="Testing Protocol",
            section=QMSSection.TESTING.value,
            content="Test procedures...",
        )
        result = manager.review_document(doc.doc_id, "alice", "approved")
        assert result.approved_by == "alice"
        assert result.approved_at != ""

    def test_review_document_missing_doc_raises(self) -> None:
        manager = QMSManager()
        with pytest.raises(KeyError, match="not found"):
            manager.review_document("nonexistent", "alice", "approved")

    def test_conduct_audit_returns_record(self) -> None:
        manager = QMSManager()
        audit = manager.conduct_audit(
            auditor="qa-team",
            scope=["compliance_strategy", "risk_management"],
        )
        assert isinstance(audit, QMSAuditRecord)
        assert audit.auditor == "qa-team"
        assert audit.scope == ["compliance_strategy", "risk_management"]
        assert audit.audit_id != ""
        assert audit.audit_date != ""

    def test_conduct_audit_with_findings(self) -> None:
        manager = QMSManager()
        audit = manager.conduct_audit(
            auditor="qa-team",
            scope=["testing"],
        )
        # Initially no findings
        assert audit.findings == []

        # Manually add findings via the record
        audit.findings.append({
            "area": "testing",
            "severity": "high",
            "description": "Missing test cases",
            "corrective_action": "",
            "status": "open",
        })
        assert len(audit.findings) == 1

    def test_close_finding(self) -> None:
        manager = QMSManager()
        audit = manager.conduct_audit(
            auditor="qa-team",
            scope=["data_governance"],
        )
        audit.findings.append({
            "area": "data_governance",
            "severity": "medium",
            "description": "Missing labels",
            "corrective_action": "",
            "status": "open",
        })

        result = manager.close_finding(audit.audit_id, 0, "Labels added and reviewed")
        assert result.findings[0]["status"] == "closed"
        assert result.findings[0]["corrective_action"] == "Labels added and reviewed"

    def test_close_finding_invalid_audit_raises(self) -> None:
        manager = QMSManager()
        with pytest.raises(KeyError, match="not found"):
            manager.close_finding("nonexistent", 0, "Closure note")

    def test_close_finding_invalid_index_raises(self) -> None:
        manager = QMSManager()
        audit = manager.conduct_audit(auditor="auditor", scope=["testing"])
        with pytest.raises(IndexError):
            manager.close_finding(audit.audit_id, 0, "Closure note")

    def test_set_quality_policy(self) -> None:
        manager = QMSManager()
        policy = manager.set_quality_policy(
            statements=["Commit to quality", "Continuous improvement"],
            review_cycle_days=180,
        )
        assert isinstance(policy, QualityPolicy)
        assert policy.policy_id != ""
        assert policy.statements == ["Commit to quality", "Continuous improvement"]
        assert policy.review_cycle_days == 180
        assert policy.last_reviewed_at != ""
        assert policy.next_review_at != ""

    def test_set_quality_policy_default_review_cycle(self) -> None:
        manager = QMSManager()
        policy = manager.set_quality_policy(
            statements=["Quality first"],
        )
        assert policy.review_cycle_days == 365

    def test_assess_supplier_low_risk(self) -> None:
        manager = QMSManager()
        result = manager.assess_supplier(
            supplier_name="DataLabeler Inc",
            capabilities={"data_annotation": True, "quality_check": True},
        )
        assert result["supplier_name"] == "DataLabeler Inc"
        assert result["substantial_modification_risk"] == "low"
        assert result["high_risk_capabilities_detected"] == []
        assert result["recommended_actions"] == []

    def test_assess_supplier_medium_risk(self) -> None:
        manager = QMSManager()
        result = manager.assess_supplier(
            supplier_name="ModelTuner Co",
            capabilities={"model_retraining": True, "data_annotation": True},
        )
        assert result["substantial_modification_risk"] == "medium"
        assert result["high_risk_capabilities_detected"] == ["model_retraining"]

    def test_assess_supplier_high_risk(self) -> None:
        """Substantial modification risk detected."""
        manager = QMSManager()
        result = manager.assess_supplier(
            supplier_name="FullStack AI",
            capabilities={
                "model_retraining": True,
                "algorithm_change": True,
                "deployment_config_change": True,
            },
        )
        assert result["substantial_modification_risk"] == "high"
        assert len(result["high_risk_capabilities_detected"]) >= 2
        assert "enhanced_monitoring" in result["recommended_actions"]

    def test_assess_supplier_no_capabilities(self) -> None:
        manager = QMSManager()
        result = manager.assess_supplier(
            supplier_name="Minimal Supplier",
            capabilities={},
        )
        assert result["substantial_modification_risk"] == "low"
        assert result["capabilities_assessed"] == []

    def test_get_qms_summary_empty(self) -> None:
        manager = QMSManager()
        summary = manager.get_qms_summary()
        assert summary["document_count"] == 0
        assert summary["audit_count"] == 0
        assert not summary["has_quality_policy"]
        assert summary["total_findings"] == 0
        assert summary["open_findings"] == 0

    def test_get_qms_summary_with_data(self) -> None:
        manager = QMSManager()
        manager.create_document(
            title="Strategy",
            section=QMSSection.COMPLIANCE_STRATEGY.value,
            content="...",
        )
        manager.create_document(
            title="Testing",
            section=QMSSection.TESTING.value,
            content="...",
        )
        audit = manager.conduct_audit(auditor="auditor", scope=["testing"])
        audit.findings.append({
            "area": "testing",
            "severity": "low",
            "description": "Minor issue",
            "corrective_action": "",
            "status": "open",
        })
        manager.set_quality_policy(statements=["Quality first"])

        summary = manager.get_qms_summary()
        assert summary["document_count"] == 2
        assert summary["audit_count"] == 1
        assert summary["has_quality_policy"]
        assert summary["total_findings"] == 1
        assert summary["open_findings"] == 1

    def test_get_kpi_dashboard_returns_dict(self) -> None:
        manager = QMSManager()
        dashboard = manager.get_kpi_dashboard()
        assert isinstance(dashboard, dict)

    def test_get_kpi_dashboard_empty(self) -> None:
        manager = QMSManager()
        dashboard = manager.get_kpi_dashboard()
        assert dashboard["total_documents"] == 0
        assert dashboard["approved_documents"] == 0
        assert dashboard["sections_covered"] == []
        assert dashboard["sections_coverage"] == "0/10"
        assert dashboard["total_audits"] == 0
        assert dashboard["total_findings"] == 0
        assert dashboard["open_findings"] == 0
        assert dashboard["closed_findings"] == 0
        assert not dashboard["has_quality_policy"]

    def test_get_kpi_dashboard_with_data(self) -> None:
        manager = QMSManager()
        doc = manager.create_document(
            title="Strategy",
            section=QMSSection.COMPLIANCE_STRATEGY.value,
            content="...",
        )
        manager.review_document(doc.doc_id, "alice", "approved")
        manager.create_document(
            title="Testing",
            section=QMSSection.TESTING.value,
            content="...",
        )
        audit = manager.conduct_audit(auditor="auditor", scope=["testing"])
        audit.findings.append({
            "area": "testing",
            "severity": "high",
            "description": "Critical issue",
            "corrective_action": "",
            "status": "open",
        })
        audit2 = manager.conduct_audit(auditor="auditor", scope=["strategy"])
        audit2.findings.append({
            "area": "strategy",
            "severity": "low",
            "description": "Minor",
            "corrective_action": "Fixed",
            "status": "closed",
        })
        manager.set_quality_policy(statements=["Quality"])

        dashboard = manager.get_kpi_dashboard()
        assert dashboard["total_documents"] == 2
        assert dashboard["approved_documents"] == 1
        assert set(dashboard["sections_covered"]) == {"compliance_strategy", "testing"}
        assert dashboard["sections_coverage"] == "2/10"
        assert dashboard["total_audits"] == 2
        assert dashboard["total_findings"] == 2
        assert dashboard["open_findings"] == 1
        assert dashboard["closed_findings"] == 1
        assert dashboard["has_quality_policy"]


class TestQMSEdgeCases:
    def test_section_without_documents(self) -> None:
        """No documents means empty QMS summary."""
        manager = QMSManager()
        assert manager.get_qms_summary()["document_count"] == 0

    def test_audit_with_zero_scope_via_manager(self) -> None:
        """Edge case: audit with empty scope via manager."""
        manager = QMSManager()
        audit = manager.conduct_audit(auditor="auditor", scope=[])
        assert audit.scope == []
        assert audit.overall_verdict == "conditional"

    def test_document_without_approval_via_manager(self) -> None:
        """Edge case: document without approval maintains default fields."""
        manager = QMSManager()
        doc = manager.create_document(
            title="Draft Doc",
            section=QMSSection.POST_MARKET_MONITORING.value,
            content="Draft",
        )
        assert doc.approved_by == ""
        assert doc.approved_at == ""

    def test_multiple_audits_multiple_findings(self) -> None:
        manager = QMSManager()
        a1 = manager.conduct_audit(auditor="a1", scope=["s1"])
        a1.findings.append({
            "area": "s1",
            "severity": "high",
            "description": "Issue 1",
            "corrective_action": "",
            "status": "open",
        })
        a2 = manager.conduct_audit(auditor="a2", scope=["s2"])
        a2.findings.append({
            "area": "s2",
            "severity": "medium",
            "description": "Issue 2",
            "corrective_action": "",
            "status": "open",
        })
        a2.findings.append({
            "area": "s2",
            "severity": "low",
            "description": "Issue 3",
            "corrective_action": "Fixed",
            "status": "closed",
        })

        summary = manager.get_qms_summary()
        assert summary["total_findings"] == 3
        assert summary["open_findings"] == 2

    def test_duplicate_doc_title_multiple_versions(self) -> None:
        """Multiple versions of same title, only last is active."""
        manager = QMSManager()
        v1 = manager.create_document(
            title="Manual",
            section=QMSSection.DEPLOYMENT_CONTROLS.value,
            content="v1",
        )
        v2 = manager.create_document(
            title="Manual",
            section=QMSSection.DEPLOYMENT_CONTROLS.value,
            content="v2",
        )
        v3 = manager.create_document(
            title="Manual",
            section=QMSSection.DEPLOYMENT_CONTROLS.value,
            content="v3",
        )
        assert v1.superseded_by == v2.doc_id
        assert v2.superseded_by == v3.doc_id
        assert v3.superseded_by == ""
        assert v1.version == "1.0.0"
        assert v2.version == "2.0.0"
        assert v3.version == "3.0.0"
