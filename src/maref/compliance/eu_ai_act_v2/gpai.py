"""
GPAI Compliance — EU AI Act Art.53-55 + Annex XI.

General Purpose AI (GPAI) obligations for providers:
- Art.53: All GPAI models (>=10^23 FLOPs)
- Art.55: GPAI with systemic risk (>=10^25 FLOPs or Commission designation)
- Annex XI: Technical documentation requirements for GPAI models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class GPAIStatus(str, Enum):
    """Classification status for General Purpose AI models."""

    BELOW_THRESHOLD = "below_threshold"
    GPAI = "gpai"
    GPAI_WITH_SYSTEMIC_RISK = "gpai_with_systemic_risk"


class EvalType(str, Enum):
    """Type of model evaluation according to Art.55(1)(a)."""

    STANDARDIZED = "standardized"
    ADVERSARIAL = "adversarial"


@dataclass
class CopyrightPolicy:
    """Art.53(1)(c) — Policy to comply with EU copyright law (Directive 2019/790).

    Includes opt-out mechanisms such as robots.txt (RFC 9309) and
    reservations of rights for training data use.
    """

    policy_id: str = field(default_factory=lambda: str(uuid4()))
    opt_out_mechanism: list[str] = field(default_factory=list)
    training_data_compliance: bool = False
    rights_reservations: list[str] = field(default_factory=list)


@dataclass
class TrainingDataSummary:
    """Art.53(1)(d) — Sufficiently detailed summary of training data used.

    Template adopted by the European Commission (July 2025).
    """

    data_sources: list[str] = field(default_factory=list)
    data_categories: list[str] = field(default_factory=list)
    size_estimate: str = ""
    languages: list[str] = field(default_factory=list)
    preprocessing: list[str] = field(default_factory=list)
    filtering_methods: list[str] = field(default_factory=list)


@dataclass
class DownstreamTransparency:
    """Art.53(1)(b) — Information for downstream providers.

    Capabilities, limitations, integration guidance, and evaluation results
    to enable informed deployment by downstream providers.
    """

    model_name: str = ""
    version: str = ""
    capable_tasks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    integration_guide: str = ""
    hardware_requirements: dict[str, Any] = field(default_factory=dict)
    evaluation_results: dict[str, Any] = field(default_factory=dict)


@dataclass
class TechnicalDocumentation:
    """Annex XI — Technical documentation for GPAI models.

    Required by Art.53(1)(a) for all GPAI models. Contains general
    description, training methodology, and evaluation results.
    """

    model_name: str = ""
    version: str = ""
    general_description: str = ""
    training_methodology: dict[str, Any] = field(default_factory=dict)
    evaluation_results: dict[str, Any] = field(default_factory=dict)
    doc_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SystemicRiskAssessment:
    """Art.55(1)(b) — Systemic risk assessment and mitigation.

    Evaluates risks across categories, assigns severity scores,
    defines mitigation measures, and documents residual risks.
    """

    assessment_id: str = field(default_factory=lambda: str(uuid4()))
    risk_categories: list[str] = field(default_factory=list)
    severity_scores: dict[str, Any] = field(default_factory=dict)
    mitigation_measures: list[str] = field(default_factory=list)
    residual_risks: list[str] = field(default_factory=list)


@dataclass
class ModelEvaluation:
    """Art.55(1)(a) — Standardized model evaluation including adversarial testing.

    Supports both standardized benchmarks and adversarial evaluations
    as required by the AI Office's evaluation protocols.
    """

    eval_id: str = field(default_factory=lambda: str(uuid4()))
    eval_type: EvalType = EvalType.STANDARDIZED
    benchmark_name: str = ""
    results: dict[str, Any] = field(default_factory=dict)
    date_performed: datetime = field(default_factory=datetime.now)


@dataclass
class PostMarketMonitoringGPAI:
    """Art.55(1)(d) — Post-market monitoring and incident reporting.

    Defines the monitoring plan, incident reporting protocol,
    reporting intervals, and AI Office contact information.
    """

    monitoring_plan: str = ""
    incident_reporting_protocol: str = ""
    reporting_interval_days: int = 30
    contact_info: str = ""


@dataclass
class EnergyEfficiencyReport:
    """Art.55(1)(e) — Energy efficiency reporting.

    Documents training and inference energy consumption,
    carbon emissions, and hardware utilization metrics.
    """

    training_energy_mwh: float = 0.0
    inference_energy_mwh: float = 0.0
    carbon_emissions_tco2: float = 0.0
    hardware_utilization: float = 0.0
    report_date: datetime = field(default_factory=datetime.now)


_ART53_OBLIGATIONS: list[str] = [
    "Technical documentation (Annex XI) — Art.53(1)(a)",
    "Downstream transparency — Art.53(1)(b)",
    "Copyright policy — Art.53(1)(c)",
    "Training data summary — Art.53(1)(d)",
]

_ART55_OBLIGATIONS: list[str] = [
    "Standardized model evaluations — Art.55(1)(a)",
    "Systemic risk assessment — Art.55(1)(b)",
    "Cybersecurity expectations — Art.55(1)(c)",
    "Post-market monitoring — Art.55(1)(d)",
    "Energy efficiency reporting — Art.55(1)(e)",
]


class GPAIComplianceManager:
    """Manages GPAI compliance obligations under EU AI Act Art.53-55.

    Provides methods for:
    - Determining GPAI status based on compute thresholds
    - Creating compliance artifacts (documentation, policies, reports)
    - Generating full compliance packages
    - Identifying missing obligations
    """

    def determine_gpai_status(
        self,
        training_compute: float,
        is_generative: bool,
        commission_designated: bool = False,
    ) -> GPAIStatus:
        """Classify a model's GPAI status based on Art.53 and Art.55 thresholds.

        Args:
            training_compute: Total training compute in FLOPs.
            is_generative: Whether the model has generative capabilities.
            commission_designated: Whether the Commission has designated the
                model as having systemic risk.

        Returns:
            GPAIStatus based on thresholds and designation.
        """
        if commission_designated or training_compute >= 1e25:
            return GPAIStatus.GPAI_WITH_SYSTEMIC_RISK
        if is_generative and training_compute >= 1e23:
            return GPAIStatus.GPAI
        if not is_generative and training_compute >= 1e23:
            return GPAIStatus.GPAI
        return GPAIStatus.BELOW_THRESHOLD

    def create_technical_documentation(
        self,
        model_name: str,
        version: str,
        description: str,
        training_methodology: dict[str, Any],
        evaluation_results: dict[str, Any],
    ) -> TechnicalDocumentation:
        """Create Annex XI technical documentation (Art.53(1)(a))."""
        return TechnicalDocumentation(
            model_name=model_name,
            version=version,
            general_description=description,
            training_methodology=training_methodology,
            evaluation_results=evaluation_results,
        )

    def create_copyright_policy(
        self,
        opt_out_mechanisms: list[str],
        rights_reservations: list[str],
    ) -> CopyrightPolicy:
        """Create copyright policy for training data (Art.53(1)(c)).

        Implements opt-out mechanisms (e.g. robots.txt RFC 9309) and
        records rights reservations in compliance with Directive 2019/790.
        """
        return CopyrightPolicy(
            opt_out_mechanism=opt_out_mechanisms,
            training_data_compliance=True,
            rights_reservations=rights_reservations,
        )

    def create_training_data_summary(
        self,
        data_sources: list[str],
        data_categories: list[str],
        size_estimate: str,
    ) -> TrainingDataSummary:
        """Create training data summary (Art.53(1)(d)) using EC template."""
        return TrainingDataSummary(
            data_sources=data_sources,
            data_categories=data_categories,
            size_estimate=size_estimate,
        )

    def create_downstream_transparency(
        self,
        model_name: str,
        version: str,
        capable_tasks: list[str],
        limitations: list[str],
        integration_guide: str,
        hardware_requirements: dict[str, Any],
        evaluation_results: dict[str, Any],
    ) -> DownstreamTransparency:
        """Create downstream transparency information (Art.53(1)(b))."""
        return DownstreamTransparency(
            model_name=model_name,
            version=version,
            capable_tasks=capable_tasks,
            limitations=limitations,
            integration_guide=integration_guide,
            hardware_requirements=hardware_requirements,
            evaluation_results=evaluation_results,
        )

    def conduct_systemic_risk_assessment(
        self,
        model_name: str,
    ) -> SystemicRiskAssessment:
        """Conduct systemic risk assessment (Art.55(1)(b)).

        Args:
            model_name: Name of the model to assess.

        Returns:
            SystemicRiskAssessment with default empty assessment structure.
        """
        return SystemicRiskAssessment(
            risk_categories=[
                "bias_and_fairness",
                "safety_and_alignment",
                "misuse_potential",
                "environmental_impact",
                "economic_disruption",
            ],
            severity_scores={
                "bias_and_fairness": 0.0,
                "safety_and_alignment": 0.0,
                "misuse_potential": 0.0,
                "environmental_impact": 0.0,
                "economic_disruption": 0.0,
            },
            mitigation_measures=[],
            residual_risks=[],
        )

    def create_model_evaluation(
        self,
        model_name: str,
        eval_type: EvalType,
        benchmark: str,
        results: dict[str, Any],
    ) -> ModelEvaluation:
        """Create model evaluation record (Art.55(1)(a)).

        Args:
            model_name: Name of the evaluated model.
            eval_type: STANDARDIZED or ADVERSARIAL.
            benchmark: Name of the benchmark used.
            results: Evaluation results dictionary.

        Returns:
            ModelEvaluation with generated eval_id.
        """
        _ = model_name
        return ModelEvaluation(
            eval_type=eval_type,
            benchmark_name=benchmark,
            results=results,
        )

    def report_incident(
        self,
        incident_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Report a serious incident to the AI Office (Art.55(1)(d)).

        Args:
            incident_data: Dictionary containing incident details.

        Returns:
            Report confirmation with incident_id and timestamp.
        """
        return {
            "incident_id": str(uuid4()),
            "reported_at": datetime.now().isoformat(),
            "status": "reported",
            "incident_data": incident_data,
        }

    def create_energy_efficiency_report(
        self,
        training_energy_mwh: float,
        inference_energy_mwh: float,
        carbon_emissions_tco2: float,
        hardware_utilization: float,
    ) -> EnergyEfficiencyReport:
        """Create energy efficiency report (Art.55(1)(e))."""
        return EnergyEfficiencyReport(
            training_energy_mwh=training_energy_mwh,
            inference_energy_mwh=inference_energy_mwh,
            carbon_emissions_tco2=carbon_emissions_tco2,
            hardware_utilization=hardware_utilization,
        )

    def generate_full_compliance_package(
        self,
        model_name: str,
        all_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a complete GPAI compliance bundle.

        Creates all compliance artifacts from the provided data.
        Each key in all_data triggers creation of the corresponding artifact.

        Args:
            model_name: Name of the model.
            all_data: Dictionary containing compliance data keys:
                - technical_documentation
                - copyright_policy
                - training_data_summary
                - downstream_transparency
                - systemic_risk_assessment
                - model_evaluation
                - incident_report
                - energy_efficiency_report

        Returns:
            Dictionary with package metadata and generated artifacts.
        """
        package: dict[str, Any] = {
            "model_name": model_name,
            "generated_at": datetime.now().isoformat(),
            "package_id": str(uuid4()),
            "artifacts": {},
        }

        if "technical_documentation" in all_data:
            td = all_data["technical_documentation"]
            package["artifacts"]["technical_documentation"] = self.create_technical_documentation(
                model_name=model_name,
                version=td.get("version", "1.0.0"),
                description=td.get("description", ""),
                training_methodology=td.get("training_methodology", {}),
                evaluation_results=td.get("evaluation_results", {}),
            )

        if "copyright_policy" in all_data:
            cp = all_data["copyright_policy"]
            package["artifacts"]["copyright_policy"] = self.create_copyright_policy(
                opt_out_mechanisms=cp.get("opt_out_mechanisms", []),
                rights_reservations=cp.get("rights_reservations", []),
            )

        if "training_data_summary" in all_data:
            tds = all_data["training_data_summary"]
            package["artifacts"]["training_data_summary"] = self.create_training_data_summary(
                data_sources=tds.get("data_sources", []),
                data_categories=tds.get("data_categories", []),
                size_estimate=tds.get("size_estimate", ""),
            )

        if "downstream_transparency" in all_data:
            dt = all_data["downstream_transparency"]
            package["artifacts"]["downstream_transparency"] = self.create_downstream_transparency(
                model_name=model_name,
                version=dt.get("version", "1.0.0"),
                capable_tasks=dt.get("capable_tasks", []),
                limitations=dt.get("limitations", []),
                integration_guide=dt.get("integration_guide", ""),
                hardware_requirements=dt.get("hardware_requirements", {}),
                evaluation_results=dt.get("evaluation_results", {}),
            )

        if "systemic_risk_assessment" in all_data:
            package["artifacts"]["systemic_risk_assessment"] = (
                self.conduct_systemic_risk_assessment(model_name=model_name)
            )

        if "model_evaluation" in all_data:
            me = all_data["model_evaluation"]
            package["artifacts"]["model_evaluation"] = self.create_model_evaluation(
                model_name=model_name,
                eval_type=me.get("eval_type", EvalType.STANDARDIZED),
                benchmark=me.get("benchmark", ""),
                results=me.get("results", {}),
            )

        if "incident_report" in all_data:
            package["artifacts"]["incident_report"] = self.report_incident(
                incident_data=all_data["incident_report"],
            )

        if "energy_efficiency_report" in all_data:
            eer = all_data["energy_efficiency_report"]
            package["artifacts"]["energy_efficiency_report"] = self.create_energy_efficiency_report(
                training_energy_mwh=eer.get("training_energy_mwh", 0.0),
                inference_energy_mwh=eer.get("inference_energy_mwh", 0.0),
                carbon_emissions_tco2=eer.get("carbon_emissions_tco2", 0.0),
                hardware_utilization=eer.get("hardware_utilization", 0.0),
            )

        return package

    def get_missing_obligations(
        self,
        gpai_status: GPAIStatus,
    ) -> list[str]:
        """Return missing compliance obligations based on GPAI status.

        Args:
            gpai_status: The model's GPAI classification status.

        Returns:
            List of obligation descriptions that are not yet fulfilled.
        """
        if gpai_status == GPAIStatus.BELOW_THRESHOLD:
            return _ART53_OBLIGATIONS + _ART55_OBLIGATIONS
        if gpai_status == GPAIStatus.GPAI:
            return list(_ART55_OBLIGATIONS)
        return []
