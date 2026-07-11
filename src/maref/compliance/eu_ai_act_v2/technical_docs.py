"""
Technical Documentation Generator — EU AI Act Art.11 + Annex IV.

Generates complete technical documentation for high-risk AI systems,
covering all 10 Annex IV requirements as mandated by Article 11.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from maref.compliance.eu_ai_act_v2.risk_classifier import RiskLevel


@dataclass
class DevelopmentMethodology:
    framework: str
    training_approach: str
    evaluation_methods: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


@dataclass
class SystemArchitecture:
    components: list[dict[str, str]] = field(default_factory=list)
    data_flows: list[dict[str, str]] = field(default_factory=list)
    external_interfaces: list[dict[str, str]] = field(default_factory=list)


@dataclass
class DataGovernance:
    datasets: list[dict[str, Any]] = field(default_factory=list)
    preprocessing_steps: list[str] = field(default_factory=list)
    bias_mitigation: list[str] = field(default_factory=list)


@dataclass
class ValidationProcedure:
    test_cases: list[dict[str, str]] = field(default_factory=list)
    metrics: list[dict[str, float | str]] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class PostMarketMonitoringPlan:
    monitoring_frequency: str = ""
    data_collection_methods: list[str] = field(default_factory=list)
    incident_reporting_protocol: str = ""


class TechnicalDocumentation:
    """Annex IV technical documentation generator per EU AI Act Art.11.

    Constructs and validates the full set of technical documentation required
    for high-risk AI systems, covering all 10 sections of Annex IV.
    """

    def __init__(
        self,
        system_name: str,
        version: str,
        intended_purpose: str,
        deployer: str,
    ) -> None:
        self.system_name = system_name
        self.version = version
        self.intended_purpose = intended_purpose
        self.deployer = deployer
        self.created_at: datetime = datetime.now()
        self.last_updated: datetime = datetime.now()

        self._general_description: dict[str, str] = {}
        self._development_methodology: DevelopmentMethodology | None = None
        self._system_architecture: SystemArchitecture | None = None
        self._data_governance: DataGovernance | None = None
        self._human_oversight: dict[str, Any] = {}
        self._validation_procedure: ValidationProcedure | None = None
        self._cybersecurity_measures: list[str] = []
        self._risk_management_summary: dict[str, Any] = {}
        self._post_market_monitoring: PostMarketMonitoringPlan | None = None
        self._performance_metrics: dict[str, float | str] = {}

        self._risk_level: RiskLevel | None = None

    # ------------------------------------------------------------------ #
    # Section setters
    # ------------------------------------------------------------------ #

    def set_general_description(self, description: dict[str, str]) -> None:
        self._general_description = description

    def set_development_methodology(
        self, methodology: DevelopmentMethodology
    ) -> None:
        self._development_methodology = methodology

    def set_system_architecture(self, architecture: SystemArchitecture) -> None:
        self._system_architecture = architecture

    def set_data_governance(self, governance: DataGovernance) -> None:
        self._data_governance = governance

    def set_human_oversight(self, oversight: dict[str, Any]) -> None:
        self._human_oversight = oversight

    def set_validation_procedure(
        self, procedure: ValidationProcedure
    ) -> None:
        self._validation_procedure = procedure

    def set_cybersecurity_measures(self, measures: list[str]) -> None:
        self._cybersecurity_measures = measures

    def set_risk_management_summary(
        self, summary: dict[str, Any]
    ) -> None:
        self._risk_management_summary = summary

    def set_post_market_monitoring(
        self, plan: PostMarketMonitoringPlan
    ) -> None:
        self._post_market_monitoring = plan

    def set_performance_metrics(
        self, metrics: dict[str, float | str]
    ) -> None:
        self._performance_metrics = metrics

    # ------------------------------------------------------------------ #
    # Risk classification
    # ------------------------------------------------------------------ #

    def set_risk_classification(self, risk_level: RiskLevel) -> None:
        self._risk_level = risk_level

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #

    def generate(self) -> dict[str, Any]:
        """Generate the full Annex IV technical documentation as a dict."""
        return {
            "document_metadata": {
                "title": f"Technical Documentation — {self.system_name} v{self.version}",
                "regulation": "Regulation (EU) 2024/1689 — Artificial Intelligence Act",
                "article": "Art.11 — Technical Documentation",
                "annex": "Annex IV",
                "generated_at": self.created_at.isoformat(),
                "last_updated": self.last_updated.isoformat(),
            },
            "system_information": {
                "system_name": self.system_name,
                "version": self.version,
                "intended_purpose": self.intended_purpose,
                "deployer": self.deployer,
                "risk_classification": (
                    self._risk_level.value if self._risk_level else "not_classified"
                ),
            },
            "section_1_general_description": self._build_section_1(),
            "section_2_development_methodology": self._build_section_2(),
            "section_3_system_architecture": self._build_section_3(),
            "section_4_data_governance": self._build_section_4(),
            "section_5_human_oversight": self._build_section_5(),
            "section_6_validation_and_testing": self._build_section_6(),
            "section_7_cybersecurity_measures": self._build_section_7(),
            "section_8_risk_management_system": self._build_section_8(),
            "section_9_post_market_monitoring": self._build_section_9(),
            "section_10_accuracy_robustness_cybersecurity": self._build_section_10(),
        }

    def generate_markdown(self) -> str:
        """Generate the technical documentation in markdown format."""
        data = self.generate()
        lines: list[str] = []

        md = data["document_metadata"]
        lines.append(f"# {md['title']}")
        lines.append("")
        lines.append(f"**Regulation:** {md['regulation']}")
        lines.append(f"**Article:** {md['article']} — {md['annex']}")
        lines.append(f"**Generated:** {md['generated_at']}")
        lines.append("")

        si = data["system_information"]
        lines.append("## System Information")
        lines.append("")
        lines.append(f"- **Name:** {si['system_name']}")
        lines.append(f"- **Version:** {si['version']}")
        lines.append(f"- **Intended Purpose:** {si['intended_purpose']}")
        lines.append(f"- **Deployer:** {si['deployer']}")
        lines.append(f"- **Risk Classification:** {si['risk_classification']}")
        lines.append("")

        sections = [
            ("1. General Description of the AI System", "section_1_general_description"),
            ("2. Development Methodology", "section_2_development_methodology"),
            ("3. System Architecture", "section_3_system_architecture"),
            ("4. Data Governance", "section_4_data_governance"),
            ("5. Human Oversight", "section_5_human_oversight"),
            ("6. Validation and Testing", "section_6_validation_and_testing"),
            ("7. Cybersecurity Measures", "section_7_cybersecurity_measures"),
            ("8. Risk Management System", "section_8_risk_management_system"),
            ("9. Post-Market Monitoring Plan", "section_9_post_market_monitoring"),
            (
                "10. Accuracy, Robustness, and Cybersecurity Metrics",
                "section_10_accuracy_robustness_cybersecurity",
            ),
        ]

        for title, key in sections:
            lines.append(f"## {title}")
            lines.append("")
            section_data = data[key]
            if isinstance(section_data, dict):
                for k, v in section_data.items():
                    key_str = k.replace("_", " ").title()
                    if isinstance(v, list):
                        lines.append(f"- **{key_str}:**")
                        for item in v:
                            lines.append(f"  - {item}")
                    elif isinstance(v, dict):
                        lines.append(f"- **{key_str}:**")
                        for sk, sv in v.items():
                            sk_str = sk.replace("_", " ").title()
                            lines.append(f"  - **{sk_str}:** {sv}")
                    else:
                        lines.append(f"- **{key_str}:** {v}")
            elif isinstance(section_data, list):
                for item in section_data:
                    lines.append(f"- {item}")
            else:
                lines.append(f"- {section_data}")
            lines.append("")

        return "\n".join(lines)

    def validate_completeness(self) -> dict[str, list[str]]:
        """Validate that all required sections are populated.

        Returns a dict of section names mapped to lists of missing fields.
        """
        missing: dict[str, list[str]] = {}

        if not self._general_description:
            missing["general_description"] = [
                "No general description provided (Annex IV §1)"
            ]
        if self._development_methodology is None:
            missing["development_methodology"] = [
                "No development methodology provided (Annex IV §2)"
            ]
        if self._system_architecture is None:
            missing["system_architecture"] = [
                "No system architecture provided (Annex IV §3)"
            ]
        if self._data_governance is None:
            missing["data_governance"] = [
                "No data governance provided (Annex IV §4)"
            ]
        if not self._human_oversight:
            missing["human_oversight"] = [
                "No human oversight assessment provided (Annex IV §5)"
            ]
        if self._validation_procedure is None:
            missing["validation_procedure"] = [
                "No validation procedure provided (Annex IV §6)"
            ]
        if not self._cybersecurity_measures:
            missing["cybersecurity_measures"] = [
                "No cybersecurity measures provided (Annex IV §7)"
            ]
        if not self._risk_management_summary:
            missing["risk_management_summary"] = [
                "No risk management summary provided (Annex IV §8)"
            ]
        if self._post_market_monitoring is None:
            missing["post_market_monitoring"] = [
                "No post-market monitoring plan provided (Annex IV §9)"
            ]
        if not self._performance_metrics:
            missing["performance_metrics"] = [
                "No performance metrics provided (Annex IV §10)"
            ]

        return missing

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full state to a JSON-compatible dict."""
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "__dataclass_fields__"):
                return asdict(obj)
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(v) for v in obj]
            return obj

        return {
            "system_name": self.system_name,
            "version": self.version,
            "intended_purpose": self.intended_purpose,
            "deployer": self.deployer,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "general_description": self._general_description,
            "development_methodology": _serialize(self._development_methodology),
            "system_architecture": _serialize(self._system_architecture),
            "data_governance": _serialize(self._data_governance),
            "human_oversight": self._human_oversight,
            "validation_procedure": _serialize(self._validation_procedure),
            "cybersecurity_measures": self._cybersecurity_measures,
            "risk_management_summary": self._risk_management_summary,
            "post_market_monitoring": _serialize(self._post_market_monitoring),
            "performance_metrics": self._performance_metrics,
            "risk_level": (
                self._risk_level.value if self._risk_level else None
            ),
        }

    # ------------------------------------------------------------------ #
    # Internal builders
    # ------------------------------------------------------------------ #

    def _build_section_1(self) -> dict[str, str]:
        base = {
            "system_name": self.system_name,
            "version": self.version,
            "intended_purpose": self.intended_purpose,
            "deployer": self.deployer,
        }
        base.update(self._general_description)
        return base

    def _build_section_2(self) -> dict[str, Any]:
        if self._development_methodology is None:
            return {"status": "not_provided"}
        return asdict(self._development_methodology)

    def _build_section_3(self) -> dict[str, Any]:
        if self._system_architecture is None:
            return {"status": "not_provided"}
        return asdict(self._system_architecture)

    def _build_section_4(self) -> dict[str, Any]:
        if self._data_governance is None:
            return {"status": "not_provided"}
        return asdict(self._data_governance)

    def _build_section_5(self) -> dict[str, Any]:
        if not self._human_oversight:
            return {"status": "not_assessed"}
        return self._human_oversight

    def _build_section_6(self) -> dict[str, Any]:
        if self._validation_procedure is None:
            return {"status": "not_provided"}
        return asdict(self._validation_procedure)

    def _build_section_7(self) -> list[str]:
        if not self._cybersecurity_measures:
            return ["not_provided"]
        return self._cybersecurity_measures

    def _build_section_8(self) -> dict[str, Any]:
        if not self._risk_management_summary:
            return {"status": "not_provided"}
        return self._risk_management_summary

    def _build_section_9(self) -> dict[str, Any]:
        if self._post_market_monitoring is None:
            return {"status": "not_provided"}
        return asdict(self._post_market_monitoring)

    def _build_section_10(self) -> dict[str, float | str]:
        if not self._performance_metrics:
            return {"status": "not_provided"}
        return self._performance_metrics
