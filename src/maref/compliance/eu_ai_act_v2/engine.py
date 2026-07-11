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

from maref.compliance.eu_ai_act_v2.accuracy_robustness import (
    AccuracyManager,
    CybersecurityManager,
    RobustnessManager,
)
from maref.compliance.eu_ai_act_v2.conformity_assessment import (
    ConformityAssessmentManager,
    ConformityRoute,
    DeclarationStatus,
)
from maref.compliance.eu_ai_act_v2.data_governance import (
    DataGovernanceManager,
)
from maref.compliance.eu_ai_act_v2.fria import (
    FRIAManager,
)
from maref.compliance.eu_ai_act_v2.gpai import (
    GPAIComplianceManager,
    GPAIStatus,
)
from maref.compliance.eu_ai_act_v2.human_oversight import (
    HumanOversightAssessment,
    HumanOversightBridge,
)
from maref.compliance.eu_ai_act_v2.incident_reporting import (
    IncidentManager,
)
from maref.compliance.eu_ai_act_v2.post_market_monitoring import (
    PMMManager,
)
from maref.compliance.eu_ai_act_v2.qms import (
    QMSManager,
)
from maref.compliance.eu_ai_act_v2.record_keeping import (
    AIActLogger,
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
    data_governance_complete: bool = False
    data_governance_gaps: list[str] = field(default_factory=list)
    record_keeping_enabled: bool = False
    record_keeping_count: int = 0
    accuracy_robustness_complete: bool = False
    accuracy_robustness_gaps: list[str] = field(default_factory=list)
    qms_established: bool = False
    qms_doc_count: int = 0
    qms_audit_status: str = ""
    incidents_open: int = 0
    incidents_total: int = 0
    fria_complete: bool = False
    fria_high_risk_rights: list[str] = field(default_factory=list)
    pmm_active: bool = False
    pmm_observations: int = 0
    pmm_review_due: bool = False
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
        self.data_gov = DataGovernanceManager()
        self.recorder = AIActLogger(system_name, version)
        self.accuracy = AccuracyManager()
        self.robustness = RobustnessManager()
        self.cybersecurity = CybersecurityManager()
        self.qms = QMSManager()
        self.incident_mgr = IncidentManager()
        self.fria = FRIAManager()
        self.pmm = PMMManager()

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
            "risk_classification": 0.06,
            "risk_management": 0.12,
            "documentation": 0.08,
            "transparency": 0.06,
            "human_oversight": 0.12,
            "conformity": 0.10,
            "gpai": 0.06,
            "data_governance": 0.06,
            "record_keeping": 0.04,
            "accuracy_robustness": 0.10,
            "qms": 0.06,
            "incident_reporting": 0.04,
            "fria": 0.04,
            "pmm": 0.06,
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

        # Data Governance (Art.10)
        if summary.data_governance_complete:
            score += weights["data_governance"] * 100.0
        elif summary.data_governance_gaps:
            ratio = 1.0 - (len(summary.data_governance_gaps) / 8.0)
            score += weights["data_governance"] * max(0, ratio * 100)

        # Record-Keeping (Art.12)
        if summary.record_keeping_enabled and summary.record_keeping_count > 0:
            score += weights["record_keeping"] * 100.0

        # Accuracy & Robustness (Art.15)
        if summary.accuracy_robustness_complete:
            score += weights["accuracy_robustness"] * 100.0
        elif summary.accuracy_robustness_gaps:
            ratio = 1.0 - (len(summary.accuracy_robustness_gaps) / 5.0)
            score += weights["accuracy_robustness"] * max(0, ratio * 100)

        # QMS (Art.17)
        if summary.qms_established and summary.qms_audit_status == "compliant":
            score += weights["qms"] * 100.0
        elif summary.qms_established:
            score += weights["qms"] * 50.0

        # Incident Reporting (Art.20 + Art.73)
        if summary.incidents_total > 0 and summary.incidents_open == 0:
            score += weights["incident_reporting"] * 100.0
        elif summary.incidents_open > 0:
            ratio = 1.0 - (summary.incidents_open / max(summary.incidents_total, 1))
            score += weights["incident_reporting"] * max(0, ratio * 100)

        # FRIA (Art.27)
        if summary.fria_complete and not summary.fria_high_risk_rights:
            score += weights["fria"] * 100.0
        elif summary.fria_complete:
            ratio = 1.0 - (len(summary.fria_high_risk_rights) / 12.0)
            score += weights["fria"] * max(0, ratio * 100)

        # Post-Market Monitoring (Art.61)
        if summary.pmm_active and not summary.pmm_review_due:
            score += weights["pmm"] * 100.0
        elif summary.pmm_active:
            score += weights["pmm"] * 50.0

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

        # M2: Data Governance (Art.10)
        gov_summary = self.data_gov.get_governance_summary()
        data_gov_complete = gov_summary["dataset_count"] > 0 and (
            gov_summary["bias_risk_level"] in ("low", "none")
        )
        data_gov_gaps: list[str] = []
        if gov_summary["dataset_count"] == 0:
            data_gov_gaps.append("No datasets registered for governance review")
        if gov_summary["bias_risk_level"] == "high":
            data_gov_gaps.append("High bias risk detected in datasets")
        if gov_summary.get("quality_metrics_count", 0) == 0:
            data_gov_gaps.append("No datasets have completed quality assessment")
        elif gov_summary["quality_passed_count"] < gov_summary["quality_metrics_count"]:
            data_gov_gaps.append("Some datasets failed quality assessment")

        # M2: Record-Keeping (Art.12)
        record_count = self.recorder.count_events()

        # M2: Accuracy & Robustness (Art.15)
        accuracy_decls = self.accuracy.get_declarations()
        all_accuracy_passed = all(d.passed for d in accuracy_decls)
        robustness_report = self.robustness.run_all()
        cyber_gaps = self.cybersecurity.gap_analysis()
        high_risk_cyber = any(
            a.risk_score > 0.7
            for a in self.cybersecurity.assess_all()
        )
        accuracy_robustness_complete = (
            len(accuracy_decls) > 0
            and all_accuracy_passed
            and robustness_report.overall_robust
            and not high_risk_cyber
        )
        ar_gaps: list[str] = []
        if not accuracy_decls:
            ar_gaps.append("No accuracy metrics declared")
        elif not all_accuracy_passed:
            ar_gaps.append("Some accuracy metrics below threshold")
        if not robustness_report.overall_robust:
            ar_gaps.append("Robustness tests not all passing")
        if high_risk_cyber:
            ar_gaps.append(f"High-risk cybersecurity gaps: {list(cyber_gaps.keys())}")

        if data_gov_gaps:
            gaps.extend(f"Data governance: {g}" for g in data_gov_gaps)
        if ar_gaps:
            gaps.extend(f"Art.15: {g}" for g in ar_gaps)

        if not all_accuracy_passed:
            recommendations.append("Improve accuracy metrics or raise thresholds")
        if not robustness_report.overall_robust:
            recommendations.append("Address robustness gaps (reproducibility/OOD/PSI/failsafe)")
        if high_risk_cyber:
            recommendations.append("Close high-risk cybersecurity gaps")

        # M3: QMS (Art.17)
        qms_summary = self.qms.get_qms_summary()
        qms_established = qms_summary["document_count"] > 0
        qms_doc_count = qms_summary["document_count"]
        audits = self.qms.get_kpi_dashboard()
        qms_audit_status = "compliant"
        if audits.get("open_findings", 0) > 0:
            qms_audit_status = "non_compliant" if audits["open_findings"] > 3 else "conditional"

        # M3: Incident Reporting (Art.20 + Art.73)
        inc_summary = self.incident_mgr.get_incident_summary()
        incidents_open = inc_summary.get("open_count", 0)
        incidents_total = inc_summary.get("total", 0)

        # M3: FRIA (Art.27)
        fria_summary = self.fria.get_fria_summary()
        fria_complete = fria_summary.get("generated_at", "") != "" and fria_summary.get("total_assessments", 0) > 0
        high_risk_assessments = self.fria.get_high_risk_rights()
        fria_high_risk_rights = [a.right.value for a in high_risk_assessments]

        # M3: PMM (Art.61)
        pmm_summary = self.pmm.get_pmm_summary()
        pmm_active = pmm_summary.get("total_plans", 0) > 0
        pmm_observations = pmm_summary.get("total_observations", 0)
        pmm_review_due = any(
            self.pmm.check_review_due(p["plan_id"])
            for p in pmm_summary.get("plans", [])
        )

        if not qms_established:
            gaps.append("QMS: No quality management documents established")
            recommendations.append("Establish Art.17 quality management system")
        if qms_audit_status == "non_compliant":
            gaps.append("QMS: Audit findings unresolved, quality system non-compliant")
        if incidents_open > 0:
            gaps.append(f"Incident reporting: {incidents_open} open incidents require correction")
        if not fria_complete:
            gaps.append("FRIA: No Fundamental Rights Impact Assessment completed")
            recommendations.append("Complete Art.27 Fundamental Rights Impact Assessment")
        elif fria_high_risk_rights:
            gaps.append(f"FRIA: High risk to rights: {fria_high_risk_rights}")
        if not pmm_active:
            gaps.append("PMM: No post-market monitoring plan established")
            recommendations.append("Establish Art.61 post-market monitoring plan")

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
            data_governance_complete=data_gov_complete,
            data_governance_gaps=data_gov_gaps,
            record_keeping_enabled=True,
            record_keeping_count=record_count,
            accuracy_robustness_complete=accuracy_robustness_complete,
            accuracy_robustness_gaps=ar_gaps,
            qms_established=qms_established,
            qms_doc_count=qms_doc_count,
            qms_audit_status=qms_audit_status,
            incidents_open=incidents_open,
            incidents_total=incidents_total,
            fria_complete=fria_complete,
            fria_high_risk_rights=fria_high_risk_rights,
            pmm_active=pmm_active,
            pmm_observations=pmm_observations,
            pmm_review_due=pmm_review_due,
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
            "data_governance": {
                "complete": summary.data_governance_complete,
                "gaps": summary.data_governance_gaps,
            },
            "record_keeping": {
                "enabled": summary.record_keeping_enabled,
                "event_count": summary.record_keeping_count,
            },
            "accuracy_robustness": {
                "complete": summary.accuracy_robustness_complete,
                "gaps": summary.accuracy_robustness_gaps,
            },
            "qms": {
                "established": summary.qms_established,
                "doc_count": summary.qms_doc_count,
                "audit_status": summary.qms_audit_status,
            },
            "incident_reporting": {
                "open_incidents": summary.incidents_open,
                "total_incidents": summary.incidents_total,
            },
            "fria": {
                "complete": summary.fria_complete,
                "high_risk_rights": summary.fria_high_risk_rights,
            },
            "post_market_monitoring": {
                "active": summary.pmm_active,
                "observations": summary.pmm_observations,
                "review_due": summary.pmm_review_due,
            },
            "overall": {
                "compliant": summary.overall_compliant,
                "score": summary.overall_score,
            },
            "gaps": summary.gaps,
            "recommendations": summary.recommendations,
        }
        return report
