"""Tests for GPAI compliance (EU AI Act Art.53-55 + Annex XI)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from maref.compliance.eu_ai_act_v2.gpai import (
    CopyrightPolicy,
    DownstreamTransparency,
    EnergyEfficiencyReport,
    EvalType,
    GPAIComplianceManager,
    GPAIStatus,
    ModelEvaluation,
    PostMarketMonitoringGPAI,
    SystemicRiskAssessment,
    TechnicalDocumentation,
    TrainingDataSummary,
)


class TestGPAIStatusEnum:
    def test_enum_values(self) -> None:
        assert GPAIStatus.BELOW_THRESHOLD.value == "below_threshold"
        assert GPAIStatus.GPAI.value == "gpai"
        assert GPAIStatus.GPAI_WITH_SYSTEMIC_RISK.value == "gpai_with_systemic_risk"

    def test_enum_members(self) -> None:
        assert len(GPAIStatus) == 3

    def test_enum_ordering(self) -> None:
        members = list(GPAIStatus)
        assert members[0] == GPAIStatus.BELOW_THRESHOLD


class TestEvalTypeEnum:
    def test_eval_type_values(self) -> None:
        assert EvalType.STANDARDIZED.value == "standardized"
        assert EvalType.ADVERSARIAL.value == "adversarial"

    def test_eval_type_members(self) -> None:
        assert len(EvalType) == 2


class TestGPAIStatusDetermination:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_below_threshold_non_generative(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e22,
            is_generative=False,
        )
        assert status == GPAIStatus.BELOW_THRESHOLD

    def test_below_threshold_generative_low_compute(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e22,
            is_generative=True,
        )
        assert status == GPAIStatus.BELOW_THRESHOLD

    def test_gpai_at_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e23,
            is_generative=True,
        )
        assert status == GPAIStatus.GPAI

    def test_gpai_above_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=5e24,
            is_generative=True,
        )
        assert status == GPAIStatus.GPAI

    def test_gpai_non_generative_above_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e23,
            is_generative=False,
        )
        assert status == GPAIStatus.GPAI

    def test_systemic_risk_at_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e25,
            is_generative=True,
        )
        assert status == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK

    def test_systemic_risk_above_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e26,
            is_generative=True,
        )
        assert status == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK

    def test_commission_designated_systemic_risk(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e22,
            is_generative=True,
            commission_designated=True,
        )
        assert status == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK

    def test_systemic_risk_non_generative(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e25,
            is_generative=False,
            commission_designated=False,
        )
        assert status == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK

    def test_below_threshold_zero_compute(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=0.0,
            is_generative=False,
        )
        assert status == GPAIStatus.BELOW_THRESHOLD

    def test_commission_designated_below_threshold(self) -> None:
        status = self.manager.determine_gpai_status(
            training_compute=1e10,
            is_generative=False,
            commission_designated=True,
        )
        assert status == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK


class TestTechnicalDocumentation:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_technical_documentation(self) -> None:
        doc = self.manager.create_technical_documentation(
            model_name="test-model",
            version="1.0.0",
            description="A test GPAI model",
            training_methodology={"architecture": "transformer", "parameters": 70e9},
            evaluation_results={"mmlu": 0.85, "hellaswag": 0.82},
        )
        assert isinstance(doc, TechnicalDocumentation)
        assert doc.model_name == "test-model"
        assert doc.version == "1.0.0"
        assert doc.general_description == "A test GPAI model"
        assert doc.training_methodology["architecture"] == "transformer"
        assert doc.evaluation_results["mmlu"] == 0.85

    def test_technical_documentation_has_uuid(self) -> None:
        doc = self.manager.create_technical_documentation(
            model_name="m", version="1", description="d",
            training_methodology={}, evaluation_results={},
        )
        UUID(doc.doc_id)

    def test_technical_documentation_has_timestamp(self) -> None:
        doc = self.manager.create_technical_documentation(
            model_name="m", version="1", description="d",
            training_methodology={}, evaluation_results={},
        )
        assert isinstance(doc.created_at, datetime)

    def test_technical_documentation_defaults(self) -> None:
        doc = TechnicalDocumentation()
        assert doc.model_name == ""
        assert doc.version == ""
        assert doc.general_description == ""


class TestCopyrightPolicy:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_copyright_policy(self) -> None:
        policy = self.manager.create_copyright_policy(
            opt_out_mechanisms=["robots.txt", "tDM Reservation Protocol"],
            rights_reservations=["Text and Data Mining reservation"],
        )
        assert isinstance(policy, CopyrightPolicy)
        assert "robots.txt" in policy.opt_out_mechanism
        assert policy.training_data_compliance is True
        assert len(policy.rights_reservations) == 1
        UUID(policy.policy_id)

    def test_copyright_policy_empty_rights(self) -> None:
        policy = self.manager.create_copyright_policy(
            opt_out_mechanisms=["robots.txt"],
            rights_reservations=[],
        )
        assert policy.rights_reservations == []

    def test_copyright_policy_no_opt_out(self) -> None:
        policy = self.manager.create_copyright_policy(
            opt_out_mechanisms=[],
            rights_reservations=["reservation"],
        )
        assert policy.opt_out_mechanism == []

    def test_copyright_policy_defaults(self) -> None:
        policy = CopyrightPolicy()
        UUID(policy.policy_id)
        assert policy.training_data_compliance is False


class TestTrainingDataSummary:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_training_data_summary(self) -> None:
        summary = self.manager.create_training_data_summary(
            data_sources=["Common Crawl", "Wikipedia", "GitHub"],
            data_categories=["text", "code"],
            size_estimate="15TB",
        )
        assert isinstance(summary, TrainingDataSummary)
        assert len(summary.data_sources) == 3
        assert "text" in summary.data_categories
        assert summary.size_estimate == "15TB"

    def test_training_data_summary_defaults(self) -> None:
        summary = TrainingDataSummary()
        assert summary.data_sources == []
        assert summary.data_categories == []
        assert summary.size_estimate == ""

    def test_training_data_summary_with_optional_fields(self) -> None:
        summary = TrainingDataSummary(
            data_sources=["source"],
            data_categories=["cat"],
            size_estimate="1TB",
            languages=["en", "zh"],
            preprocessing=["tokenization", "deduplication"],
            filtering_methods=["perplexity_filter", "toxicity_filter"],
        )
        assert "en" in summary.languages
        assert "tokenization" in summary.preprocessing
        assert "perplexity_filter" in summary.filtering_methods


class TestDownstreamTransparency:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_downstream_transparency(self) -> None:
        info = self.manager.create_downstream_transparency(
            model_name="test-model",
            version="2.0.0",
            capable_tasks=["text_generation", "summarization"],
            limitations=["may produce biased output", "limited context window"],
            integration_guide="See documentation at docs.example.com",
            hardware_requirements={"gpu": "A100", "vram_gb": 80},
            evaluation_results={"bbh": 0.72},
        )
        assert isinstance(info, DownstreamTransparency)
        assert info.model_name == "test-model"
        assert len(info.capable_tasks) == 2
        assert len(info.limitations) == 2
        assert "GPU" not in info.hardware_requirements

    def test_downstream_transparency_defaults(self) -> None:
        info = DownstreamTransparency()
        assert info.model_name == ""
        assert info.capable_tasks == []
        assert info.evaluation_results == {}


class TestSystemicRiskAssessment:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_conduct_systemic_risk_assessment(self) -> None:
        assessment = self.manager.conduct_systemic_risk_assessment(
            model_name="high-risk-model",
        )
        assert isinstance(assessment, SystemicRiskAssessment)
        UUID(assessment.assessment_id)
        assert len(assessment.risk_categories) == 5
        assert "bias_and_fairness" in assessment.risk_categories
        assert assessment.severity_scores["bias_and_fairness"] == 0.0

    def test_systemic_risk_default_mitigation_empty(self) -> None:
        assessment = self.manager.conduct_systemic_risk_assessment(
            model_name="test",
        )
        assert assessment.mitigation_measures == []
        assert assessment.residual_risks == []

    def test_systemic_risk_assessment_defaults(self) -> None:
        assessment = SystemicRiskAssessment()
        UUID(assessment.assessment_id)
        assert assessment.risk_categories == []


class TestModelEvaluation:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_standardized_evaluation(self) -> None:
        eval_result = self.manager.create_model_evaluation(
            model_name="test-model",
            eval_type=EvalType.STANDARDIZED,
            benchmark="MMLU",
            results={"accuracy": 0.87, "f1": 0.85},
        )
        assert isinstance(eval_result, ModelEvaluation)
        UUID(eval_result.eval_id)
        assert eval_result.eval_type == EvalType.STANDARDIZED
        assert eval_result.benchmark_name == "MMLU"
        assert eval_result.results["accuracy"] == 0.87

    def test_create_adversarial_evaluation(self) -> None:
        eval_result = self.manager.create_model_evaluation(
            model_name="test-model",
            eval_type=EvalType.ADVERSARIAL,
            benchmark="AdvBench",
            results={"attack_success_rate": 0.12},
        )
        assert eval_result.eval_type == EvalType.ADVERSARIAL
        assert eval_result.benchmark_name == "AdvBench"

    def test_evaluation_has_timestamp(self) -> None:
        eval_result = self.manager.create_model_evaluation(
            model_name="m", eval_type=EvalType.STANDARDIZED,
            benchmark="b", results={},
        )
        assert isinstance(eval_result.date_performed, datetime)

    def test_model_evaluation_defaults(self) -> None:
        eval_result = ModelEvaluation()
        UUID(eval_result.eval_id)
        assert eval_result.eval_type == EvalType.STANDARDIZED
        assert eval_result.benchmark_name == ""


class TestIncidentReporting:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_report_incident(self) -> None:
        incident = self.manager.report_incident(
            incident_data={
                "type": "model_hallucination",
                "severity": "high",
                "description": "Model generated harmful content",
                "timestamp": "2026-07-11T12:00:00Z",
            },
        )
        assert incident["status"] == "reported"
        UUID(incident["incident_id"])
        assert "reported_at" in incident
        assert incident["incident_data"]["type"] == "model_hallucination"

    def test_report_empty_incident(self) -> None:
        incident = self.manager.report_incident(incident_data={})
        assert incident["status"] == "reported"
        assert incident["incident_data"] == {}

    def test_report_incident_unique_ids(self) -> None:
        inc1 = self.manager.report_incident(incident_data={"id": 1})
        inc2 = self.manager.report_incident(incident_data={"id": 2})
        assert inc1["incident_id"] != inc2["incident_id"]


class TestEnergyEfficiency:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_create_energy_efficiency_report(self) -> None:
        report = self.manager.create_energy_efficiency_report(
            training_energy_mwh=4500.0,
            inference_energy_mwh=1200.0,
            carbon_emissions_tco2=1800.0,
            hardware_utilization=0.78,
        )
        assert isinstance(report, EnergyEfficiencyReport)
        assert report.training_energy_mwh == 4500.0
        assert report.inference_energy_mwh == 1200.0
        assert report.carbon_emissions_tco2 == 1800.0
        assert report.hardware_utilization == 0.78

    def test_energy_report_zero_values(self) -> None:
        report = self.manager.create_energy_efficiency_report(
            training_energy_mwh=0.0,
            inference_energy_mwh=0.0,
            carbon_emissions_tco2=0.0,
            hardware_utilization=0.0,
        )
        assert report.training_energy_mwh == 0.0

    def test_energy_report_has_date(self) -> None:
        report = self.manager.create_energy_efficiency_report(
            training_energy_mwh=100, inference_energy_mwh=50,
            carbon_emissions_tco2=20, hardware_utilization=0.5,
        )
        assert isinstance(report.report_date, datetime)

    def test_energy_report_defaults(self) -> None:
        report = EnergyEfficiencyReport()
        assert report.training_energy_mwh == 0.0
        assert report.hardware_utilization == 0.0
        assert isinstance(report.report_date, datetime)


class TestPostMarketMonitoring:
    def test_post_market_monitoring_defaults(self) -> None:
        mon = PostMarketMonitoringGPAI()
        assert mon.monitoring_plan == ""
        assert mon.incident_reporting_protocol == ""
        assert mon.reporting_interval_days == 30
        assert mon.contact_info == ""

    def test_post_market_monitoring_custom(self) -> None:
        mon = PostMarketMonitoringGPAI(
            monitoring_plan="Quarterly audit",
            incident_reporting_protocol="24h email report",
            reporting_interval_days=90,
            contact_info="ai-office@ec.europa.eu",
        )
        assert mon.reporting_interval_days == 90
        assert "europa" in mon.contact_info


class TestFullCompliancePackage:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_generate_full_package_empty(self) -> None:
        package = self.manager.generate_full_compliance_package(
            model_name="test-model",
            all_data={},
        )
        assert package["model_name"] == "test-model"
        assert "package_id" in package
        UUID(package["package_id"])
        assert package["artifacts"] == {}

    def test_generate_full_package_all_artifacts(self) -> None:
        all_data: dict = {
            "technical_documentation": {
                "version": "1.0.0",
                "description": "Full GPAI model",
                "training_methodology": {"architecture": "transformer"},
                "evaluation_results": {"mmlu": 0.9},
            },
            "copyright_policy": {
                "opt_out_mechanisms": ["robots.txt"],
                "rights_reservations": ["TDM reservation"],
            },
            "training_data_summary": {
                "data_sources": ["web"],
                "data_categories": ["text"],
                "size_estimate": "10TB",
            },
            "downstream_transparency": {
                "version": "1.0.0",
                "capable_tasks": ["generation"],
                "limitations": ["bias"],
                "integration_guide": "docs.example.com",
                "hardware_requirements": {"gpu": "A100"},
                "evaluation_results": {"bbh": 0.8},
            },
            "systemic_risk_assessment": True,
            "model_evaluation": {
                "eval_type": EvalType.STANDARDIZED,
                "benchmark": "MMLU",
                "results": {"accuracy": 0.87},
            },
            "incident_report": {"type": "test", "severity": "low"},
            "energy_efficiency_report": {
                "training_energy_mwh": 5000.0,
                "inference_energy_mwh": 1000.0,
                "carbon_emissions_tco2": 2000.0,
                "hardware_utilization": 0.85,
            },
        }
        package = self.manager.generate_full_compliance_package(
            model_name="full-model",
            all_data=all_data,
        )
        assert package["model_name"] == "full-model"
        artifacts = package["artifacts"]
        assert "technical_documentation" in artifacts
        assert "copyright_policy" in artifacts
        assert "training_data_summary" in artifacts
        assert "downstream_transparency" in artifacts
        assert "systemic_risk_assessment" in artifacts
        assert "model_evaluation" in artifacts
        assert "incident_report" in artifacts
        assert "energy_efficiency_report" in artifacts

    def test_partial_package_artifacts(self) -> None:
        all_data: dict = {
            "technical_documentation": {
                "version": "1.0",
                "description": "Partial",
                "training_methodology": {},
                "evaluation_results": {},
            },
            "incident_report": {"type": "test"},
        }
        package = self.manager.generate_full_compliance_package(
            model_name="partial",
            all_data=all_data,
        )
        assert "technical_documentation" in package["artifacts"]
        assert "incident_report" in package["artifacts"]
        assert "copyright_policy" not in package["artifacts"]


class TestMissingObligations:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_below_threshold_all_missing(self) -> None:
        missing = self.manager.get_missing_obligations(
            GPAIStatus.BELOW_THRESHOLD,
        )
        # Both Art.53 and Art.55 obligations are missing
        assert len(missing) == 9
        assert any("Art.53(1)(a)" in o for o in missing)
        assert any("Art.53(1)(b)" in o for o in missing)
        assert any("Art.53(1)(c)" in o for o in missing)
        assert any("Art.53(1)(d)" in o for o in missing)
        assert any("Art.55(1)(a)" in o for o in missing)
        assert any("Art.55(1)(b)" in o for o in missing)
        assert any("Art.55(1)(c)" in o for o in missing)
        assert any("Art.55(1)(d)" in o for o in missing)
        assert any("Art.55(1)(e)" in o for o in missing)

    def test_gpai_art55_missing(self) -> None:
        missing = self.manager.get_missing_obligations(GPAIStatus.GPAI)
        assert len(missing) == 5
        assert all("Art.55" in o for o in missing)

    def test_gpai_systemic_no_missing(self) -> None:
        missing = self.manager.get_missing_obligations(
            GPAIStatus.GPAI_WITH_SYSTEMIC_RISK,
        )
        assert missing == []

    def test_missing_obligations_immutable(self) -> None:
        missing = self.manager.get_missing_obligations(GPAIStatus.GPAI)
        missing.append("extra")
        # Original list should not be affected
        missing2 = self.manager.get_missing_obligations(GPAIStatus.GPAI)
        assert len(missing2) == 5


class TestEdgeCases:
    def setup_method(self) -> None:
        self.manager = GPAIComplianceManager()

    def test_technical_doc_minimal_data(self) -> None:
        doc = self.manager.create_technical_documentation(
            model_name="", version="", description="",
            training_methodology={}, evaluation_results={},
        )
        assert doc.model_name == ""
        assert doc.general_description == ""

    def test_copyright_policy_robots_txt_rfc_9309(self) -> None:
        policy = self.manager.create_copyright_policy(
            opt_out_mechanisms=["robots.txt"],
            rights_reservations=[],
        )
        assert "robots.txt" in policy.opt_out_mechanism

    def test_downstream_transparency_no_tasks(self) -> None:
        info = self.manager.create_downstream_transparency(
            model_name="m", version="1",
            capable_tasks=[], limitations=[],
            integration_guide="", hardware_requirements={},
            evaluation_results={},
        )
        assert info.capable_tasks == []
        assert info.limitations == []

    def test_model_evaluation_empty_results(self) -> None:
        eval_result = self.manager.create_model_evaluation(
            model_name="m", eval_type=EvalType.STANDARDIZED,
            benchmark="b", results={},
        )
        assert eval_result.results == {}

    def test_energy_report_negative_values(self) -> None:
        report = self.manager.create_energy_efficiency_report(
            training_energy_mwh=-1.0,
            inference_energy_mwh=-1.0,
            carbon_emissions_tco2=-1.0,
            hardware_utilization=-1.0,
        )
        assert report.training_energy_mwh == -1.0
        assert report.hardware_utilization == -1.0

    def test_training_data_summary_empty_sources(self) -> None:
        summary = self.manager.create_training_data_summary(
            data_sources=[], data_categories=[], size_estimate="",
        )
        assert summary.data_sources == []

    def test_systemic_risk_with_custom_data(self) -> None:
        assessment = SystemicRiskAssessment(
            risk_categories=["custom_risk"],
            severity_scores={"custom_risk": 0.9},
            mitigation_measures=["implement guardrails"],
            residual_risks=["low_frequency_events"],
        )
        assert assessment.severity_scores["custom_risk"] == 0.9
        assert "implement guardrails" in assessment.mitigation_measures
