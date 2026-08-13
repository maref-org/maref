"""
EU AI Act Conformity Assessment — Art.43 + Annex VI/VII + Art.47-49.

Art.43: Two conformity assessment routes:
  - Route A — Internal Control (Annex VI): Self-assessment for Annex III pts.2-8
  - Route B — Third-Party (Annex VII): Notified body assessment for biometrics
    (Annex III pt.1) or when no harmonized standards exist.
Art.47: EU Declaration of Conformity — document certifying compliance.
Art.48: CE Marking — affix CE mark after conformity assessment.
Art.49: EU Database Registration — register high-risk AI system.
Art.43(4): Substantial Modification triggers new conformity assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    RiskLevel,
)


class ConformityRoute(str, Enum):
    """Conformity assessment routes defined in Art.43.

    INTERNAL_CONTROL: Self-assessment per Annex VI (Route A).
    THIRD_PARTY: Notified body assessment per Annex VII (Route B).
    """

    INTERNAL_CONTROL = "internal_control"
    THIRD_PARTY = "third_party"


class DeclarationStatus(str, Enum):
    """Status of a conformity assessment."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SubstantialModificationType(str, Enum):
    """Types of substantial modification (Art.43(4))."""

    RISK_SCOPE_CHANGE = "risk_scope_change"
    DATASET_CHANGE = "dataset_change"
    INTENDED_PURPOSE_CHANGE = "intended_purpose_change"
    ARCHITECTURE_CHANGE = "architecture_change"
    CYBERSECURITY_REVISION = "cybersecurity_revision"


@dataclass
class ConformityAssessmentRecord:
    """Record of a single conformity assessment (Art.43 + Annex VI/VII)."""

    assessment_id: str = field(default_factory=lambda: uuid4().hex)
    system_name: str = ""
    route: ConformityRoute = ConformityRoute.INTERNAL_CONTROL
    status: DeclarationStatus = DeclarationStatus.NOT_STARTED
    assessed_at: str = ""
    findings: list[str] = field(default_factory=list)
    certificate_id: str = ""


@dataclass
class EUDeclarationOfConformity:
    """EU Declaration of Conformity (Art.47)."""

    declaration_id: str = field(default_factory=lambda: uuid4().hex)
    system_name: str = ""
    ai_act_articles: list[str] = field(default_factory=list)
    harmonized_standards: list[str] = field(default_factory=list)
    issuer: str = ""
    issued_at: str = ""
    valid_until: str = ""


@dataclass
class CEMarking:
    """CE Marking record (Art.48)."""

    affixed: bool = False
    marking_id: str = ""
    affixed_at: str = ""
    assessment_id: str = ""


@dataclass
class EUDatabaseRegistration:
    """EU Database registration record (Art.49)."""

    registration_id: str = field(default_factory=lambda: uuid4().hex)
    system_name: str = ""
    risk_level: str = ""
    registration_date: str = ""
    expiry_date: str = ""


class ConformityAssessmentManager:
    """Manages conformity assessment lifecycle per Art.43-49.

    Handles route determination, assessment initiation/completion,
    EU declaration of conformity (Art.47), CE marking (Art.48),
    EU database registration (Art.49), and substantial modification
    detection (Art.43(4)).
    """

    _DECLARATION_VALID_YEARS = 5
    _REGISTRATION_VALID_YEARS = 5

    def __init__(self) -> None:
        self._assessments: dict[str, ConformityAssessmentRecord] = {}
        self._declarations: dict[str, EUDeclarationOfConformity] = {}
        self._ce_markings: dict[str, CEMarking] = {}
        self._registrations: dict[str, EUDatabaseRegistration] = {}

    def determine_route(
        self,
        risk_level: RiskLevel,
        categories: list[AnnexIIICategory | str] | None = None,
        has_harmonized_standards: bool = False,
        force_third_party: bool = False,
    ) -> ConformityRoute | None:
        """Determine the appropriate conformity assessment route (Art.43).

        Args:
            risk_level: The risk level of the AI system.
            categories: Applicable Annex III categories.
            has_harmonized_standards: Whether harmonized standards exist.
            force_third_party: Force third-party assessment (voluntary).

        Returns:
            The ConformityRoute, or None if no assessment is needed.
        """
        if risk_level in (RiskLevel.GPAI, RiskLevel.GPAI_WITH_SYSTEMIC_RISK):
            return None
        if risk_level not in (RiskLevel.HIGH,):
            return None
        if force_third_party:
            return ConformityRoute.THIRD_PARTY
        cats = [c.value if isinstance(c, AnnexIIICategory) else c for c in (categories or [])]
        is_biometrics = AnnexIIICategory.BIOMETRICS.value in cats
        if is_biometrics and not has_harmonized_standards:
            return ConformityRoute.THIRD_PARTY
        return ConformityRoute.INTERNAL_CONTROL

    def initiate_assessment(
        self,
        system_name: str,
        route: ConformityRoute,
    ) -> ConformityAssessmentRecord:
        """Initiate a new conformity assessment (start of Art.43 process)."""
        record = ConformityAssessmentRecord(
            system_name=system_name,
            route=route,
            status=DeclarationStatus.IN_PROGRESS,
        )
        self._assessments[record.assessment_id] = record
        return record

    def complete_assessment(
        self,
        assessment_id: str,
        findings: list[str] | None = None,
    ) -> ConformityAssessmentRecord | None:
        """Complete an in-progress conformity assessment.

        Returns None if the assessment_id does not exist.
        """
        record = self._assessments.get(assessment_id)
        if record is None:
            return None
        record.status = DeclarationStatus.COMPLETED
        record.findings = findings or []
        record.assessed_at = datetime.now(timezone.utc).isoformat()
        return record

    def generate_declaration(
        self,
        assessment_id: str,
        issuer: str = "",
        harmonized_standards: list[str] | None = None,
    ) -> EUDeclarationOfConformity | None:
        """Generate EU Declaration of Conformity (Art.47).

        The assessment must be COMPLETED. Returns None if the assessment
        does not exist or is not yet complete.
        """
        record = self._assessments.get(assessment_id)
        if record is None or record.status != DeclarationStatus.COMPLETED:
            return None
        now = datetime.now(timezone.utc)
        declaration = EUDeclarationOfConformity(
            system_name=record.system_name,
            ai_act_articles=["Art.6", "Art.43", "Art.47", "Art.48"],
            harmonized_standards=harmonized_standards or [],
            issuer=issuer or record.system_name,
            issued_at=now.isoformat(),
            valid_until=(now + timedelta(days=365 * self._DECLARATION_VALID_YEARS)).isoformat(),
        )
        self._declarations[declaration.declaration_id] = declaration
        record.certificate_id = declaration.declaration_id
        return declaration

    def issue_ce_marking(
        self,
        declaration_id: str,
    ) -> CEMarking | None:
        """Issue CE marking (Art.48) based on an EU Declaration of Conformity.

        Returns None if the declaration_id does not exist.
        """
        declaration = self._declarations.get(declaration_id)
        if declaration is None:
            return None
        assessment_id = ""
        for aid, rec in self._assessments.items():
            if rec.certificate_id == declaration_id:
                assessment_id = aid
                break
        marking = CEMarking(
            affixed=True,
            marking_id=f"CE-{uuid4().hex[:8].upper()}",
            affixed_at=datetime.now(timezone.utc).isoformat(),
            assessment_id=assessment_id,
        )
        self._ce_markings[marking.marking_id] = marking
        return marking

    def register_in_eu_database(
        self,
        system_name: str,
        risk_level: str,
    ) -> EUDatabaseRegistration:
        """Register a high-risk AI system in the EU database (Art.49).

        If the system is already registered, returns the existing registration.
        """
        for reg in self._registrations.values():
            if reg.system_name == system_name:
                return reg
        now = datetime.now(timezone.utc)
        registration = EUDatabaseRegistration(
            system_name=system_name,
            risk_level=risk_level,
            registration_date=now.isoformat(),
            expiry_date=(now + timedelta(days=365 * self._REGISTRATION_VALID_YEARS)).isoformat(),
        )
        self._registrations[registration.registration_id] = registration
        return registration

    def detect_substantial_modification(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> list[SubstantialModificationType]:
        """Detect substantial modifications (Art.43(4)).

        Compares two system state snapshots and returns a list of detected
        modification types. An empty list means no substantial modification.

        Expected keys in the snapshot dicts:
            risk_scope, datasets, intended_purpose, architecture_summary,
            cybersecurity_measures
        """
        modifications: list[SubstantialModificationType] = []
        if current.get("risk_scope") != previous.get("risk_scope"):
            modifications.append(SubstantialModificationType.RISK_SCOPE_CHANGE)
        if current.get("datasets") != previous.get("datasets"):
            modifications.append(SubstantialModificationType.DATASET_CHANGE)
        if current.get("intended_purpose") != previous.get("intended_purpose"):
            modifications.append(SubstantialModificationType.INTENDED_PURPOSE_CHANGE)
        if current.get("architecture_summary") != previous.get("architecture_summary"):
            modifications.append(SubstantialModificationType.ARCHITECTURE_CHANGE)
        if current.get("cybersecurity_measures") != previous.get("cybersecurity_measures"):
            modifications.append(SubstantialModificationType.CYBERSECURITY_REVISION)
        return modifications

    def get_assessment_history(
        self,
        system_name: str,
    ) -> list[ConformityAssessmentRecord]:
        """Return all conformity assessments for a given system."""
        return [rec for rec in self._assessments.values() if rec.system_name == system_name]

    def generate_conformity_report(
        self,
        assessment_id: str,
    ) -> str:
        """Generate a comprehensive conformity assessment report.

        Returns a markdown-formatted string covering the assessment,
        declaration, CE marking, and EU database registration status.
        """
        record = self._assessments.get(assessment_id)
        if record is None:
            return "ERROR: Conformity assessment not found."

        declaration = next(
            (d for d in self._declarations.values() if d.declaration_id == record.certificate_id),
            None,
        )
        ce_marking = next(
            (m for m in self._ce_markings.values() if m.assessment_id == assessment_id),
            None,
        )
        registration = next(
            (r for r in self._registrations.values() if r.system_name == record.system_name),
            None,
        )

        lines: list[str] = [
            f"# Conformity Assessment Report — {record.system_name}",
            "",
            f"**Assessment ID:** {record.assessment_id}",
            f"**Route:** {record.route.value}",
            f"**Status:** {record.status.value}",
            f"**Assessed At:** {record.assessed_at or 'N/A'}",
            f"**Certificate ID:** {record.certificate_id or 'N/A'}",
            "",
            "## Findings",
        ]
        if record.findings:
            for finding in record.findings:
                lines.append(f"- {finding}")
        else:
            lines.append("No findings recorded.")
        lines.append("")

        if declaration:
            lines.extend(
                [
                    "## EU Declaration of Conformity (Art.47)",
                    f"**Declaration ID:** {declaration.declaration_id}",
                    f"**Issuer:** {declaration.issuer}",
                    f"**Issued At:** {declaration.issued_at}",
                    f"**Valid Until:** {declaration.valid_until}",
                    "**Applicable Articles:**",
                ]
            )
            for article in declaration.ai_act_articles:
                lines.append(f"- {article}")
            if declaration.harmonized_standards:
                lines.append("**Harmonized Standards:**")
                for std in declaration.harmonized_standards:
                    lines.append(f"- {std}")
            lines.append("")

        if ce_marking:
            lines.extend(
                [
                    "## CE Marking (Art.48)",
                    f"**Marking ID:** {ce_marking.marking_id}",
                    f"**Affixed At:** {ce_marking.affixed_at}",
                    f"**Affixed:** {'Yes' if ce_marking.affixed else 'No'}",
                    "",
                ]
            )

        if registration:
            lines.extend(
                [
                    "## EU Database Registration (Art.49)",
                    f"**Registration ID:** {registration.registration_id}",
                    f"**Risk Level:** {registration.risk_level}",
                    f"**Registered At:** {registration.registration_date}",
                    f"**Expiry Date:** {registration.expiry_date}",
                    "",
                ]
            )

        lines.append("---")
        lines.append(f"*Report generated at: {datetime.now(timezone.utc).isoformat()}*")
        return "\n".join(lines)
