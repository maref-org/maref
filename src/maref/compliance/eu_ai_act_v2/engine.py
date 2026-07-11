"""
EU AI Act Compliance Engine V2 — Integration Hub

Bridges all V2 modules into a unified compliance engine and connects
to the existing ComplianceRegistry for cross-jurisdiction reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from maref.compliance.eu_ai_act_v2.conformity_assessment import (
    ConformityAssessmentManager,
    ConformityRoute,
    DeclarationStatus,
)
from maref.compliance.eu_ai_act_v2.gpai import (
    GPAIComplianceManager,
    GPAIStatus,
)
from maref.compliance.eu_ai_act_v2.human_oversight import (
    HumanOversightAssessment,
    HumanOversightBridge,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    ClassificationDetail,
    GPAIThreshold,
    RiskClassifier,
    RiskLevel,
)
from maref.compliance.eu_ai_act_v2.risk_management import (
    RiskManagementLifecycleState,
    RiskManagementSystem,
)
from maref.compliance.eu_ai_act_v2.technical_docs import (
    TechnicalDocumentation,
)
from maref.compliance.eu_ai_act_v2.transparency import (
    TransparencyManager,
)
from maref.compliance.registry import (
    ComplianceCheckResult,
    ComplianceRegistry,
    ComplianceRequirement,
    ComplianceStatus,
    Jurisdiction,
)


@dataclass
class EUAIComplianceSummary:
    """Complete compliance summary for an AI system under EU AI Act."""

    system_name: str
    version: str
    risk_level: RiskLevel
    classification_detail: ClassificationDetail
    risk_management_complete: bool
    risk_management_score: float
    documentation_complete: bool
    documentation_missing_fields: list[str]
    transparency_complete: bool
    transparency_missing_obligations: list[str]
    oversight_assessment: HumanOversightAssessment | None
    conformity_route: ConformityRoute | None
    conformity_status: DeclarationStatus
    gpai_status: GPAIStatus | None
    gpai_missing_obligations: list[str]
    overall_compliant: bool
    overall_score: float
    gaps: list[str]
    recommendations: list[str]
    assessed_at: str = field(default_factory=lambda: datetime.now().isoformat())


class EUAIComplianceEngineV2:
    """Unified EU AI Act compliance engine (V2).

    Orchestrates all V2 modules and bridges to ComplianceRegistry.
    """

    def __init__(
        self,
        system_name: str = "MAREF-Agent",
        version: str = "1.0.0",
        registry: ComplianceRegistry | None = None,
    ):
        self.system_name = system_name
        self.version = version
        self.registry = registry

        self.classifier = RiskClassifier()
        self.risk_mgmt = RiskManagementSystem()
        self.technical_docs = TechnicalDocumentation(
            system_name=system_name,
            version=version,
            intended_purpose="Multi-agent governance system",
            deployer="MAREF Operator",
        )
        self.transparency_mgr = TransparencyManager()
        self.oversight: HumanOversightBridge | None = None
        self.conformity = ConformityAssessmentManager()
        self.gpai_mgr = GPAIComplianceManager()

    def classify(self, **kwargs: Any) -> ClassificationDetail:
        """Classify the AI system risk level.

        Pass kwargs matching RiskClassifier.classify_with_details parameters.
        """
        detail = self.classifier.classify_with_details(**kwargs)
        return detail

    def assess_risk_management(self) -> dict[str, Any]:
        """Run the full risk management lifecycle."""
        self.risk_mgmt.identify_risks()
        evaluation = self.risk_mgmt.evaluate_risks()
        return evaluation

    def setup_technical_documentation(self, **kwargs: Any) -> dict[str, Any]:
        """Configure and generate technical documentation."""
        if "development_methodology" in kwargs:
            self.technical_docs.set_development_methodology(
                kwargs["development_methodology"]
            )
        if "system_architecture" in kwargs:
            self.technical_docs.set_system_architecture(kwargs["system_architecture"])
        if "data_governance" in kwargs:
            self.technical_docs.set_data_governance(kwargs["data_governance"])
        if "validation_procedure" in kwargs:
            self.technical_docs.set_validation_procedure(kwargs["validation_procedure"])
        return self.technical_docs.generate()

    def setup_human_oversight(self, risk_level: RiskLevel) -> HumanOversightAssessment:
        """Configure human oversight based on risk level."""
        self.oversight = HumanOversightBridge(
            system_name=self.system_name,
            risk_level=risk_level,
        )
        assessment = self.oversight.assess_capabilities()
        mode = self.oversight.recommend_oversight_mode(risk_level)
        if mode:
            self.oversight.set_oversight_config(
                mode=mode,
                capabilities=[c.capability for c in assessment.capabilities],
            )
        return assessment

    def run_conformity_assessment(
        self,
        risk_level: RiskLevel,
        categories: list[AnnexIIICategory] | None = None,
    ) -> dict[str, Any]:
        """Run the conformity assessment pipeline."""
        route = self.conformity.determine_route(
            risk_level=risk_level,
            has_harmonized_standards=False,
        )
        if route is None:
            return {"route": None, "message": "No conformity assessment required"}
        assessment = self.conformity.initiate_assessment(
            system_name=self.system_name,
            route=route,
        )
        return {
            "route": route.value if route else None,
            "assessment_id": assessment.assessment_id,
            "status": assessment.status.value,
        }

    def setup_gpai(
        self,
        training_compute: float = 0.0,
        is_generative: bool = False,
    ) -> dict[str, Any]:
        """Configure GPAI compliance if applicable."""
        gpai_status = self.gpai_mgr.determine_gpai_status(
            training_compute=training_compute,
            is_generative=is_generative,
        )
        missing = self.gpai_mgr.get_missing_obligations(gpai_status)
        return {
            "gpai_status": gpai_status.value,
            "missing_obligations": missing,
        }

    def _compute_score(self, summary: EUAIComplianceSummary) -> float:
        """Compute overall compliance score (0-100)."""

        # Base weight by compliance areas
        weights = {
            "risk_classification": 0.10,
            "risk_management": 0.20,
            "documentation": 0.15,
            "transparency": 0.10,
            "human_oversight": 0.20,
            "conformity": 0.15,
            "gpai": 0.10,
        }
        score = 0.0

        # Risk classification — always available
        score += weights["risk_classification"] * 100.0

        # Risk management
        if summary.risk_management_complete:
            score += weights["risk_management"] * 100.0
        elif summary.risk_management_score > 0:
            score += weights["risk_management"] * summary.risk_management_score

        # Documentation
        if summary.documentation_complete:
            score += weights["documentation"] * 100.0
        elif summary.documentation_missing_fields:
            ratio = 1.0 - (len(summary.documentation_missing_fields) / 10.0)
            score += weights["documentation"] * max(0, ratio * 100)

        # Transparency
        if summary.transparency_complete:
            score += weights["transparency"] * 100.0
        elif summary.transparency_missing_obligations:
            ratio = 1.0 - (
                len(summary.transparency_missing_obligations) / 5.0
            )
            score += weights["transparency"] * max(0, ratio * 100)

        # Human oversight
        if summary.oversight_assessment is not None:
            score += weights["human_oversight"] * summary.oversight_assessment.overall_score

        # Conformity
        if summary.conformity_status == DeclarationStatus.COMPLETED:
            score += weights["conformity"] * 100.0
        elif summary.conformity_status == DeclarationStatus.IN_PROGRESS:
            score += weights["conformity"] * 50.0

        # GPAI
        if summary.gpai_status in (None, GPAIStatus.BELOW_THRESHOLD) or not summary.gpai_missing_obligations:
            score += weights["gpai"] * 100.0
        else:
            ratio = 1.0 - (len(summary.gpai_missing_obligations) / 6.0)
            score += weights["gpai"] * max(0, ratio * 100)

        return round(score, 1)

    def generate_summary(
        self,
        **classify_kwargs: Any,
    ) -> EUAIComplianceSummary:
        """Generate a complete EU AI Act compliance summary.

        Args:
            **classify_kwargs: Keyword arguments for RiskClassifier.classify_with_details.
                              Defaults to empty categories if not provided.

        Returns:
            EUAIComplianceSummary with full compliance posture.
        """
        if "categories" not in classify_kwargs:
            classify_kwargs["categories"] = []
        detail = self.classify(**classify_kwargs)

        risk_mgmt_result = self.assess_risk_management()
        risk_mgmt_complete = self.risk_mgmt.state == RiskManagementLifecycleState.REVIEW
        risk_mgmt_score = float(
            risk_mgmt_result.get("average_score", risk_mgmt_result.get("overall_score", 0.0))
        )

        doc_validation = self.technical_docs.validate_completeness()
        doc_complete = len(doc_validation.get("missing_fields", [])) == 0

        trans_validation = self.transparency_mgr.validate_all()
        trans_complete = trans_validation.get("compliant", False)
        trans_missing = trans_validation.get("missing_obligations", [])

        risk_level = detail.risk_level
        oversight_assessment = self.setup_human_oversight(risk_level)

        conformity_result = self.run_conformity_assessment(
            risk_level=risk_level,
        )
        conformity_status = DeclarationStatus.IN_PROGRESS
        conformity_route = None
        if conformity_result.get("route"):
            conformity_route = ConformityRoute(conformity_result["route"])
            if conformity_result.get("assessment_id"):
                self.conformity.complete_assessment(
                    conformity_result["assessment_id"],
                    findings=["Assessment completed by engine"],
                )
                conformity_status = DeclarationStatus.COMPLETED

        # Determine GPAI status from classification detail or explicit params
        training_compute = classify_kwargs.get("training_compute", 0.0)
        is_generative = classify_kwargs.get("is_generative", False)
        compute_threshold = classify_kwargs.get("compute_threshold", GPAIThreshold.BELOW_THRESHOLD)

        if training_compute == 0.0 and compute_threshold != GPAIThreshold.BELOW_THRESHOLD:
            training_compute = 10 ** (
                26 if compute_threshold == GPAIThreshold.ABOVE_10_25 else 24
            )

        gpai_result = self.setup_gpai(
            training_compute=training_compute,
            is_generative=is_generative,
        )
        gpai_status_enum = GPAIStatus(gpai_result["gpai_status"])

        gaps: list[str] = []
        recommendations: list[str] = []

        if not doc_complete:
            gaps.append(
                f"Technical documentation incomplete: {doc_validation['missing_fields']}"
            )
            recommendations.append("Complete Annex IV technical documentation")

        if not trans_complete:
            gaps.append(f"Transparency obligations missing: {trans_missing}")
            recommendations.append("Fulfill Art.50 transparency obligations")

        if gpai_result["missing_obligations"]:
            gaps.append(
                f"GPAI obligations missing: {gpai_result['missing_obligations']}"
            )
            recommendations.append("Complete GPAI compliance obligations")

        summary = EUAIComplianceSummary(
            system_name=self.system_name,
            version=self.version,
            risk_level=risk_level,
            classification_detail=detail,
            risk_management_complete=risk_mgmt_complete,
            risk_management_score=float(risk_mgmt_score),
            documentation_complete=doc_complete,
            documentation_missing_fields=doc_validation.get("missing_fields", []),
            transparency_complete=trans_complete,
            transparency_missing_obligations=trans_missing,
            oversight_assessment=oversight_assessment,
            conformity_route=conformity_route,
            conformity_status=conformity_status,
            gpai_status=gpai_status_enum,
            gpai_missing_obligations=gpai_result["missing_obligations"],
            overall_compliant=False,
            overall_score=0.0,
            gaps=gaps,
            recommendations=recommendations,
        )

        summary.overall_score = self._compute_score(summary)
        summary.overall_compliant = summary.overall_score >= 80.0

        self._sync_to_registry(summary)
        return summary

    def _sync_to_registry(self, summary: EUAIComplianceSummary) -> None:
        """Sync compliance results to ComplianceRegistry if available."""
        if self.registry is None:
            return

        regulation = self.registry.regulations.get("eu-ai-act")
        if not regulation:
            return

        for req_id in regulation.requirements:
            status = ComplianceStatus.PARTIAL
            if summary.overall_compliant:
                status = ComplianceStatus.COMPLIANT
            elif summary.overall_score < 30:
                status = ComplianceStatus.NON_COMPLIANT

            req_key = f"eu-ai-act-{req_id}"
            requirement = self.registry.requirements.get(req_key)
            if not requirement:
                requirement = ComplianceRequirement(
                    requirement_id=req_key,
                    regulation_id="eu-ai-act",
                    name=req_id.replace("_", " ").title(),
                    description=f"EU AI Act {req_id} compliance",
                    jurisdiction=Jurisdiction.EU,
                )
                self.registry.register_requirement(requirement)
            requirement.status = status
            requirement.checked_at = datetime.now()

        # Record check result
        result = ComplianceCheckResult(
            result_id=f"eu-ai-act-v2-{uuid4().hex[:8]}",
            requirement_id="eu-ai-act-overall",
            status=(
                ComplianceStatus.COMPLIANT
                if summary.overall_compliant
                else ComplianceStatus.PARTIAL
            ),
            checked_at=datetime.now(),
            checked_by="EUAIComplianceEngineV2",
            findings=summary.gaps,
            recommendations=summary.recommendations,
            score=summary.overall_score,
        )
        self.registry.record_check_result(result)

    def generate_report(self, **classify_kwargs: Any) -> dict[str, Any]:
        """Generate a comprehensive EU AI Act compliance report."""
        summary = self.generate_summary(**classify_kwargs)
        detail = summary.classification_detail
        docs = self.technical_docs.generate()

        report: dict[str, Any] = {
            "report_title": f"EU AI Act Compliance Report — {self.system_name} v{self.version}",
            "generated_at": summary.assessed_at,
            "system": {
                "name": self.system_name,
                "version": self.version,
            },
            "risk_classification": {
                "risk_level": summary.risk_level.value,
                "is_prohibited": detail.is_prohibited,
                "is_gpai": detail.is_gpai,
                "has_systemic_risk": detail.has_systemic_risk,
                "matched_categories": detail.matched_categories,
                "applied_exemptions": detail.applied_exemptions,
                "reasons": detail.reasons,
            },
            "risk_management": {
                "lifecycle_state": self.risk_mgmt.state.value,
                "risk_count": len(self.risk_mgmt.catalog),
                "mitigated_count": sum(
                    1 for r in self.risk_mgmt.catalog.values() if r.mitigated
                ),
            },
            "technical_documentation": {
                "sections": list(docs.keys()) if isinstance(docs, dict) else [],
                "complete": summary.documentation_complete,
                "missing_fields": summary.documentation_missing_fields,
            },
            "transparency": {
                "complete": summary.transparency_complete,
                "missing_obligations": summary.transparency_missing_obligations,
            },
            "human_oversight": {
                "mode": (
                    summary.oversight_assessment.recommended_mode.value
                    if summary.oversight_assessment
                    and summary.oversight_assessment.recommended_mode
                    else None
                ),
                "score": (
                    summary.oversight_assessment.overall_score
                    if summary.oversight_assessment
                    else 0.0
                ),
            },
            "conformity_assessment": {
                "route": summary.conformity_route.value if summary.conformity_route else None,
                "status": summary.conformity_status.value,
            },
            "gpai": {
                "status": summary.gpai_status.value if summary.gpai_status else None,
                "missing_obligations": summary.gpai_missing_obligations,
            },
            "overall": {
                "compliant": summary.overall_compliant,
                "score": summary.overall_score,
            },
            "gaps": summary.gaps,
            "recommendations": summary.recommendations,
        }
        return report
