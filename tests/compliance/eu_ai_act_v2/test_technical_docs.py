"""Tests for EU AI Act Annex IV technical documentation generator (Art.11)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.risk_classifier import RiskLevel
from maref.compliance.eu_ai_act_v2.technical_docs import (
    DataGovernance,
    DevelopmentMethodology,
    PostMarketMonitoringPlan,
    SystemArchitecture,
    TechnicalDocumentation,
    ValidationProcedure,
)


class TestDevelopmentMethodology:
    def test_minimal_creation(self) -> None:
        dm = DevelopmentMethodology(
            framework="PyTorch",
            training_approach="supervised_fine_tuning",
        )
        assert dm.framework == "PyTorch"
        assert dm.training_approach == "supervised_fine_tuning"
        assert dm.evaluation_methods == []
        assert dm.tools == []

    def test_full_creation(self) -> None:
        dm = DevelopmentMethodology(
            framework="Transformers",
            training_approach="RLHF",
            evaluation_methods=["bleu", "rouge"],
            tools=["weave", "langfuse"],
        )
        assert len(dm.evaluation_methods) == 2
        assert len(dm.tools) == 2

    def test_defaults_are_empty_lists(self) -> None:
        dm = DevelopmentMethodology(
            framework="sklearn",
            training_approach="logistic_regression",
        )
        assert dm.evaluation_methods == []
        assert dm.tools == []


class TestSystemArchitecture:
    def test_minimal_creation(self) -> None:
        sa = SystemArchitecture()
        assert sa.components == []
        assert sa.data_flows == []
        assert sa.external_interfaces == []

    def test_with_components(self) -> None:
        sa = SystemArchitecture(
            components=[
                {"name": "inference_engine", "type": "llm"},
                {"name": "guardrails", "type": "filter"},
            ],
            data_flows=[
                {"from": "input", "to": "inference_engine", "protocol": "grpc"},
            ],
            external_interfaces=[
                {"name": "api_gateway", "protocol": "rest"},
            ],
        )
        assert len(sa.components) == 2
        assert len(sa.data_flows) == 1
        assert len(sa.external_interfaces) == 1


class TestDataGovernance:
    def test_minimal_creation(self) -> None:
        dg = DataGovernance()
        assert dg.datasets == []
        assert dg.preprocessing_steps == []
        assert dg.bias_mitigation == []

    def test_with_datasets(self) -> None:
        dg = DataGovernance(
            datasets=[
                {"name": "training_v1", "size": 100000, "format": "parquet"},
                {"name": "validation_v1", "size": 10000, "format": "parquet"},
            ],
            preprocessing_steps=["tokenization", "deduplication"],
            bias_mitigation=["reweighting", "adversarial_debiasing"],
        )
        assert len(dg.datasets) == 2
        assert len(dg.preprocessing_steps) == 2
        assert len(dg.bias_mitigation) == 2


class TestValidationProcedure:
    def test_minimal_creation(self) -> None:
        vp = ValidationProcedure()
        assert vp.test_cases == []
        assert vp.metrics == []
        assert vp.acceptance_criteria == []

    def test_full_creation(self) -> None:
        vp = ValidationProcedure(
            test_cases=[
                {"id": "TC-001", "description": "verify_output_format"},
                {"id": "TC-002", "description": "verify_accuracy_threshold"},
            ],
            metrics=[
                {"name": "accuracy", "value": 0.95},
                {"name": "f1_score", "value": 0.92},
            ],
            acceptance_criteria=["accuracy >= 0.90", "f1 >= 0.85"],
        )
        assert len(vp.test_cases) == 2
        assert len(vp.metrics) == 2
        assert len(vp.acceptance_criteria) == 2


class TestPostMarketMonitoringPlan:
    def test_default_creation(self) -> None:
        pmm = PostMarketMonitoringPlan()
        assert pmm.monitoring_frequency == ""

    def test_full_creation(self) -> None:
        pmm = PostMarketMonitoringPlan(
            monitoring_frequency="monthly",
            data_collection_methods=["user_feedback", "telemetry"],
            incident_reporting_protocol="notify_within_24h",
        )
        assert pmm.monitoring_frequency == "monthly"
        assert len(pmm.data_collection_methods) == 2


class TestTechnicalDocumentationCreation:
    def test_minimal_creation(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test-ai",
            version="1.0.0",
            intended_purpose="testing",
            deployer="test-deployer",
        )
        assert doc.system_name == "test-ai"
        assert doc.version == "1.0.0"
        assert doc.intended_purpose == "testing"
        assert doc.deployer == "test-deployer"

    def test_generate_without_sections(self) -> None:
        doc = TechnicalDocumentation(
            system_name="empty", version="0.1", intended_purpose="p", deployer="d"
        )
        result = doc.generate()
        assert "document_metadata" in result
        assert "system_information" in result
        assert result["section_1_general_description"]["system_name"] == "empty"
        assert result["section_1_general_description"]["intended_purpose"] == "p"
        assert result["section_2_development_methodology"] == {"status": "not_provided"}

    def test_generate_with_all_sections(self) -> None:
        doc = _make_full_documentation()
        result = doc.generate()
        assert result["section_1_general_description"]["system_name"] == "full-ai"
        assert result["section_2_development_methodology"]["framework"] == "PyTorch"
        assert len(result["section_3_system_architecture"]["components"]) == 2
        assert len(result["section_4_data_governance"]["datasets"]) == 1
        assert result["section_5_human_oversight"]["status"] == "reviewed"
        assert len(result["section_6_validation_and_testing"]["test_cases"]) == 2
        assert len(result["section_7_cybersecurity_measures"]) == 2
        assert "risk_owner" in result["section_8_risk_management_system"]
        assert result["section_9_post_market_monitoring"]["monitoring_frequency"] == "weekly"
        assert result["section_10_accuracy_robustness_cybersecurity"]["accuracy"] == 0.97

    def test_system_information_includes_risk_level(self) -> None:
        doc = _make_full_documentation()
        result = doc.generate()
        assert result["system_information"]["risk_classification"] == "high"

    def test_default_risk_classification(self) -> None:
        doc = TechnicalDocumentation(
            system_name="x", version="1", intended_purpose="p", deployer="d"
        )
        result = doc.generate()
        assert result["system_information"]["risk_classification"] == "not_classified"


class TestMarkdownGeneration:
    def test_generate_markdown_returns_string(self) -> None:
        doc = _make_full_documentation()
        md = doc.generate_markdown()
        assert isinstance(md, str)
        assert len(md) > 100

    def test_markdown_contains_system_name(self) -> None:
        doc = _make_full_documentation()
        md = doc.generate_markdown()
        assert "full-ai" in md

    def test_markdown_contains_all_section_headers(self) -> None:
        doc = _make_full_documentation()
        md = doc.generate_markdown()
        assert "## 1. General Description" in md
        assert "## 2. Development Methodology" in md
        assert "## 3. System Architecture" in md
        assert "## 4. Data Governance" in md
        assert "## 5. Human Oversight" in md
        assert "## 6. Validation and Testing" in md
        assert "## 7. Cybersecurity Measures" in md
        assert "## 8. Risk Management System" in md
        assert "## 9. Post-Market Monitoring Plan" in md
        assert "## 10. Accuracy" in md

    def test_markdown_empty_document(self) -> None:
        doc = TechnicalDocumentation(
            system_name="empty", version="0", intended_purpose="none", deployer="none"
        )
        md = doc.generate_markdown()
        assert md.startswith("#")
        assert "empty" in md


class TestCompletenessValidation:
    def test_all_sections_missing_on_empty_doc(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test", version="1", intended_purpose="p", deployer="d"
        )
        missing = doc.validate_completeness()
        assert "general_description" in missing
        assert "development_methodology" in missing
        assert "system_architecture" in missing
        assert "data_governance" in missing
        assert "human_oversight" in missing
        assert "validation_procedure" in missing
        assert "cybersecurity_measures" in missing
        assert "risk_management_summary" in missing
        assert "post_market_monitoring" in missing
        assert "performance_metrics" in missing

    def test_no_missing_sections_on_full_doc(self) -> None:
        doc = _make_full_documentation()
        missing = doc.validate_completeness()
        assert missing == {}

    def test_partial_sections_detected(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test", version="1", intended_purpose="p", deployer="d"
        )
        doc.set_general_description({"location": "EU"})
        doc.set_cybersecurity_measures(["encryption"])
        missing = doc.validate_completeness()
        assert "general_description" not in missing
        assert "cybersecurity_measures" not in missing
        assert "development_methodology" in missing
        assert "system_architecture" in missing


class TestRiskClassification:
    def test_set_risk_classification(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test", version="1", intended_purpose="p", deployer="d"
        )
        doc.set_risk_classification(RiskLevel.UNACCEPTABLE)
        result = doc.generate()
        assert result["system_information"]["risk_classification"] == "unacceptable"

    def test_set_risk_classification_gpai(self) -> None:
        doc = TechnicalDocumentation(
            system_name="gpai-model",
            version="2.0",
            intended_purpose="content_gen",
            deployer="acme",
        )
        doc.set_risk_classification(RiskLevel.GPAI)
        result = doc.generate()
        assert result["system_information"]["risk_classification"] == "gpai"

    def test_set_risk_classification_high(self) -> None:
        doc = TechnicalDocumentation(
            system_name="hrmodel",
            version="1",
            intended_purpose="recruitment",
            deployer="hr-corp",
        )
        doc.set_risk_classification(RiskLevel.HIGH)
        result = doc.generate()
        assert result["system_information"]["risk_classification"] == "high"


class TestSerialization:
    def test_to_dict_round_trip(self) -> None:
        doc = _make_full_documentation()
        d = doc.to_dict()
        assert d["system_name"] == "full-ai"
        assert d["version"] == "2.0.0"
        assert d["risk_level"] == "high"
        assert "general_description" in d
        assert "development_methodology" in d
        assert "system_architecture" in d
        assert "data_governance" in d
        assert "human_oversight" in d
        assert "validation_procedure" in d
        assert "cybersecurity_measures" in d
        assert "risk_management_summary" in d
        assert "post_market_monitoring" in d
        assert "performance_metrics" in d

    def test_to_dict_no_risk_level(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test",
            version="1",
            intended_purpose="p",
            deployer="d",
        )
        d = doc.to_dict()
        assert d["risk_level"] is None

    def test_to_dict_datetime_serialized(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test",
            version="1",
            intended_purpose="p",
            deployer="d",
        )
        d = doc.to_dict()
        assert isinstance(d["created_at"], str)
        assert "T" in d["created_at"]

    def test_to_dict_dataclass_serialized(self) -> None:
        doc = _make_full_documentation()
        d = doc.to_dict()
        assert isinstance(d["development_methodology"], dict)
        assert d["development_methodology"]["framework"] == "PyTorch"
        assert isinstance(d["system_architecture"], dict)
        assert isinstance(d["post_market_monitoring"], dict)


class TestEdgeCases:
    def test_very_long_descriptions(self) -> None:
        long_text = "A" * 10000
        doc = TechnicalDocumentation(
            system_name=long_text,
            version="1",
            intended_purpose=long_text,
            deployer=long_text,
        )
        result = doc.generate()
        assert result["system_information"]["system_name"] == long_text

    def test_empty_cybersecurity_measures(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test", version="1", intended_purpose="p", deployer="d"
        )
        doc.set_cybersecurity_measures([])
        result = doc.generate()
        assert result["section_7_cybersecurity_measures"] == ["not_provided"]

    def test_empty_performance_metrics(self) -> None:
        doc = TechnicalDocumentation(
            system_name="test", version="1", intended_purpose="p", deployer="d"
        )
        doc.set_performance_metrics({})
        result = doc.generate()
        assert result["section_10_accuracy_robustness_cybersecurity"] == {
            "status": "not_provided"
        }

    def test_general_description_extends_base(self) -> None:
        doc = TechnicalDocumentation(
            system_name="ext-test",
            version="3.0",
            intended_purpose="extension check",
            deployer="ext-deployer",
        )
        doc.set_general_description({"location": "EU/DE", "system_type": "nlp"})
        result = doc.generate()
        sec1 = result["section_1_general_description"]
        assert sec1["system_name"] == "ext-test"
        assert sec1["location"] == "EU/DE"

    def test_set_risk_management_summary(self) -> None:
        doc = TechnicalDocumentation(
            system_name="rms-test",
            version="1",
            intended_purpose="risk test",
            deployer="rms-corp",
        )
        doc.set_risk_management_summary(
            {
                "risk_owner": "security-team",
                "risk_level_assessment": "medium",
                "mitigations": ["access_control", "audit_logging"],
            }
        )
        result = doc.generate()
        assert result["section_8_risk_management_system"]["risk_owner"] == "security-team"

    def test_created_at_and_updated_at(self) -> None:
        doc = TechnicalDocumentation(
            system_name="time-test",
            version="1",
            intended_purpose="time",
            deployer="time-corp",
        )
        assert doc.created_at is not None
        assert doc.last_updated is not None

    def test_validate_completeness_returns_correct_count(self) -> None:
        doc = TechnicalDocumentation(
            system_name="t", version="1", intended_purpose="p", deployer="d"
        )
        missing = doc.validate_completeness()
        assert len(missing) == 10

    def test_markdown_header_format(self) -> None:
        doc = TechnicalDocumentation(
            system_name="hdr-test",
            version="1.0",
            intended_purpose="header test",
            deployer="hdr-corp",
        )
        md = doc.generate_markdown()
        lines = md.split("\n")
        assert lines[0].startswith("# ")


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_full_documentation() -> TechnicalDocumentation:
    """Create a TechnicalDocumentation instance with all sections populated."""
    doc = TechnicalDocumentation(
        system_name="full-ai",
        version="2.0.0",
        intended_purpose="full compliance testing",
        deployer="compliance-corp",
    )

    doc.set_general_description(
        {
            "location": "EU/DE",
            "system_type": "nlp",
            "deployment_model": "cloud",
        }
    )

    doc.set_development_methodology(
        DevelopmentMethodology(
            framework="PyTorch",
            training_approach="supervised_fine_tuning",
            evaluation_methods=["accuracy", "f1", "latency_p95"],
            tools=["wandb", "langfuse"],
        )
    )

    doc.set_system_architecture(
        SystemArchitecture(
            components=[
                {"name": "inference_engine", "type": "llm", "version": "7b"},
                {"name": "content_filter", "type": "guardrails", "version": "2.0"},
            ],
            data_flows=[
                {
                    "from": "user_request",
                    "to": "inference_engine",
                    "protocol": "grpc",
                    "description": "user input to inference",
                },
                {
                    "from": "inference_engine",
                    "to": "content_filter",
                    "protocol": "in_process",
                    "description": "output filtering",
                },
            ],
            external_interfaces=[
                {"name": "rest_api", "protocol": "https", "port": "443"},
            ],
        )
    )

    doc.set_data_governance(
        DataGovernance(
            datasets=[
                {
                    "name": "training_data_v2",
                    "size": 500000,
                    "format": "parquet",
                    "source": "internal",
                }
            ],
            preprocessing_steps=["tokenization", "deduplication", "normalization"],
            bias_mitigation=["dataset_rebalancing", "fairness_constraints"],
        )
    )

    doc.set_human_oversight(
        {
            "status": "reviewed",
            "oversight_measures": ["human_in_the_loop", "approval_required"],
            "art_14_assessment": "full_oversight_implemented",
        }
    )

    doc.set_validation_procedure(
        ValidationProcedure(
            test_cases=[
                {"id": "TC-001", "description": "output_format_validation"},
                {"id": "TC-002", "description": "content_safety_check"},
            ],
            metrics=[
                {"name": "accuracy", "value": 0.95},
                {"name": "f1_score", "value": 0.92},
            ],
            acceptance_criteria=["accuracy >= 0.90", "f1 >= 0.85"],
        )
    )

    doc.set_cybersecurity_measures(
        [
            "tls_encryption_in_transit",
            "access_control_rbac",
        ]
    )

    doc.set_risk_management_summary(
        {
            "risk_owner": "security-team",
            "risk_level_assessment": "medium",
            "mitigations": ["access_control", "audit_logging"],
        }
    )

    doc.set_post_market_monitoring(
        PostMarketMonitoringPlan(
            monitoring_frequency="weekly",
            data_collection_methods=["user_feedback", "telemetry", "incident_reports"],
            incident_reporting_protocol="notify_within_24h_via_pagerduty",
        )
    )

    doc.set_performance_metrics(
        {
            "accuracy": 0.97,
            "robustness_accuracy": 0.93,
            "cybersecurity_score": 0.88,
        }
    )

    doc.set_risk_classification(RiskLevel.HIGH)

    return doc
