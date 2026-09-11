"""EU AI Act Quality Management System — Article 17.

Implements Art.17 requirements for a quality management system
covering all 10 mandated sections for high-risk AI providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4


class QMSSection(str, Enum):
    """Art.17(1) a-j: 10 required QMS sections."""

    COMPLIANCE_STRATEGY = "compliance_strategy"
    DESIGN_PROCEDURES = "design_procedures"
    REVIEW_VALIDATION = "review_validation"
    TESTING = "testing"
    DATA_GOVERNANCE = "data_governance"
    RISK_MANAGEMENT = "risk_management"
    POST_MARKET_MONITORING = "post_market_monitoring"
    INCIDENT_REPORTING = "incident_reporting"
    RECORD_KEEPING = "record_keeping"
    DEPLOYMENT_CONTROLS = "deployment_controls"


@dataclass
class QMSDocument:
    """Art.17(1): A single QMS document covering one of 10 mandated sections."""

    doc_id: str
    title: str
    version: str
    section: str
    content: str
    approved_by: str = ""
    approved_at: str = ""
    next_review_at: str = ""
    superseded_by: str = ""


@dataclass
class QMSAuditRecord:
    """Art.17(1)(e): Internal audit record with findings tracking."""

    audit_id: str
    audit_date: str
    auditor: str
    scope: list[str]
    findings: list[dict[str, str]] = field(default_factory=list)
    overall_verdict: str = "conditional"


@dataclass
class QualityPolicy:
    """Art.17(1)(a): Quality policy statement with review cycle."""

    policy_id: str
    statements: list[str]
    review_cycle_days: int = 365
    last_reviewed_at: str = ""
    next_review_at: str = ""


class QMSManager:
    """Orchestrates all Art.17 QMS operations."""

    def __init__(self) -> None:
        self._documents: dict[str, QMSDocument] = {}
        self._audits: dict[str, QMSAuditRecord] = {}
        self._quality_policy: QualityPolicy | None = None

    def create_document(
        self,
        title: str,
        section: str,
        content: str,
        **kwargs: Any,
    ) -> QMSDocument:
        """Create a new QMS document.

        If a document with the same title already exists and is not superseded,
        the new version supersedes the old one (auto-increment major version).
        """
        existing = [d for d in self._documents.values() if d.title == title and not d.superseded_by]
        if existing:
            old = existing[0]
            parts = old.version.split(".")
            new_major = int(parts[0]) + 1
            version = f"{new_major}.0.0"
        else:
            version = "1.0.0"

        doc_id = kwargs.pop("doc_id", uuid4().hex[:8])
        doc = QMSDocument(
            doc_id=doc_id,
            title=title,
            version=version,
            section=section,
            content=content,
            **kwargs,
        )
        self._documents[doc.doc_id] = doc

        if existing:
            existing[0].superseded_by = doc.doc_id

        return doc

    def review_document(
        self,
        doc_id: str,
        reviewer: str,
        verdict: str,
    ) -> QMSDocument:
        """Review and approve/reject a QMS document."""
        if doc_id not in self._documents:
            raise KeyError(f"Document not found: {doc_id}")

        doc = self._documents[doc_id]
        if verdict == "approved":
            doc.approved_by = reviewer
            doc.approved_at = datetime.now().isoformat()
        return doc

    def conduct_audit(
        self,
        auditor: str,
        scope: list[str],
    ) -> QMSAuditRecord:
        """Conduct a QMS internal audit."""
        audit = QMSAuditRecord(
            audit_id=uuid4().hex[:8],
            audit_date=datetime.now().isoformat(),
            auditor=auditor,
            scope=scope,
        )
        self._audits[audit.audit_id] = audit
        return audit

    def close_finding(
        self,
        audit_id: str,
        finding_idx: int,
        closure_note: str,
    ) -> QMSAuditRecord:
        """Close a finding in an audit record."""
        if audit_id not in self._audits:
            raise KeyError(f"Audit not found: {audit_id}")

        audit = self._audits[audit_id]
        if finding_idx < 0 or finding_idx >= len(audit.findings):
            raise IndexError(f"Finding index out of range: {finding_idx}")

        audit.findings[finding_idx]["status"] = "closed"
        audit.findings[finding_idx]["corrective_action"] = closure_note
        return audit

    def set_quality_policy(
        self,
        statements: list[str],
        review_cycle_days: int = 365,
    ) -> QualityPolicy:
        """Set or update the quality policy."""
        now = datetime.now()
        next_review = now + timedelta(days=review_cycle_days)
        policy = QualityPolicy(
            policy_id=uuid4().hex[:8],
            statements=statements,
            review_cycle_days=review_cycle_days,
            last_reviewed_at=now.isoformat(),
            next_review_at=next_review.isoformat(),
        )
        self._quality_policy = policy
        return policy

    def assess_supplier(
        self,
        supplier_name: str,
        capabilities: dict[str, Any],
    ) -> dict[str, Any]:
        """Assess supplier for substantial modification risk (Art.43(4))."""
        high_risk_capabilities = [
            "model_retraining",
            "model_architecture_change",
            "algorithm_change",
            "training_data_injection",
            "deployment_config_change",
        ]
        detected = [c for c in high_risk_capabilities if capabilities.get(c, False)]
        risk_level = "high" if len(detected) >= 2 else "medium" if len(detected) == 1 else "low"

        recommended_actions: list[str] = []
        if risk_level == "high":
            recommended_actions = ["enhanced_monitoring", "regular_audits"]
        elif risk_level == "medium":
            recommended_actions = ["routine_monitoring"]

        return {
            "supplier_name": supplier_name,
            "capabilities_assessed": list(capabilities.keys()),
            "high_risk_capabilities_detected": detected,
            "substantial_modification_risk": risk_level,
            "recommended_actions": recommended_actions,
        }

    def get_qms_summary(self) -> dict[str, Any]:
        """Generate an overall QMS summary."""
        total_findings = sum(len(a.findings) for a in self._audits.values())
        open_findings = sum(
            1
            for a in self._audits.values()
            for f in a.findings
            if f.get("status", "open") != "closed"
        )

        return {
            "document_count": len(self._documents),
            "audit_count": len(self._audits),
            "has_quality_policy": self._quality_policy is not None,
            "total_findings": total_findings,
            "open_findings": open_findings,
        }

    def get_kpi_dashboard(self) -> dict[str, Any]:
        """Return KPI dashboard metrics."""
        total_docs = len(self._documents)
        approved_docs = sum(1 for d in self._documents.values() if d.approved_by)

        total_audits = len(self._audits)
        total_findings = sum(len(a.findings) for a in self._audits.values())
        open_findings = sum(
            1
            for a in self._audits.values()
            for f in a.findings
            if f.get("status", "open") != "closed"
        )
        closed_findings = total_findings - open_findings

        sections_covered = sorted({d.section for d in self._documents.values()})

        return {
            "total_documents": total_docs,
            "approved_documents": approved_docs,
            "sections_covered": sections_covered,
            "sections_coverage": f"{len(sections_covered)}/10",
            "total_audits": total_audits,
            "total_findings": total_findings,
            "open_findings": open_findings,
            "closed_findings": closed_findings,
            "has_quality_policy": self._quality_policy is not None,
        }
