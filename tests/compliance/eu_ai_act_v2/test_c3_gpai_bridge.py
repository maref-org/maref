"""Tests for C3 bridge: GPAI Art.53-55 compliance artifacts + engine integration."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.engine import EUAIComplianceEngineV2
from maref.compliance.eu_ai_act_v2.gpai import (
    CopyrightPolicy,
    DownstreamTransparency,
    EnergyEfficiencyReport,
    GPAIComplianceManager,
    GPAIStatus,
    ModelEvaluation,
    PostMarketMonitoringGPAI,
    SystemicRiskAssessment,
    TrainingDataSummary,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import GPAIThreshold


# ------------------------------------------------------------------ #
# Art.53 — GPAI transparency obligations
# ------------------------------------------------------------------ #

class TestArt53Transparency:
    def test_copyright_policy_creation(self) -> None:
        mgr = GPAIComplianceManager()
        policy = mgr.create_copyright_policy(
            opt_out_mechanisms=["robots.txt"],
            rights_reservations=["Apache-2.0"],
        )
        assert isinstance(policy, CopyrightPolicy)
        assert policy.training_data_compliance

    def test_training_data_summary_creation(self) -> None:
        mgr = GPAIComplianceManager()
        summary = mgr.create_training_data_summary(
            data_sources=["logs", "events"],
            data_categories=["governance"],
            size_estimate="100k",
        )
        assert isinstance(summary, TrainingDataSummary)

    def test_downstream_transparency_creation(self) -> None:
        mgr = GPAIComplianceManager()
        dt = mgr.create_downstream_transparency(
            model_name="MAREF",
            version="1.0",
            capable_tasks=["governance"],
            limitations=["needs_oversight"],
            integration_guide="MCP",
            hardware_requirements={"cpu": "2"},
            evaluation_results={"acc": 0.95},
        )
        assert isinstance(dt, DownstreamTransparency)
        assert dt.model_name == "MAREF"


# ------------------------------------------------------------------ #
# Art.55 — Systemic risk management
# ------------------------------------------------------------------ #

class TestArt55SystemicRisk:
    def test_systemic_risk_assessment_defaults(self) -> None:
        mgr = GPAIComplianceManager()
        assessment = mgr.conduct_systemic_risk_assessment("MAREF")
        assert isinstance(assessment, SystemicRiskAssessment)
        assert len(assessment.risk_categories) == 5

    def test_model_evaluation_creation(self) -> None:
        mgr = GPAIComplianceManager()
        ev = mgr.create_model_evaluation(
            model_name="MAREF",
            eval_type="standardized",
            benchmark="SAEB",
            results={"pass": True},
        )
        assert isinstance(ev, ModelEvaluation)

    def test_energy_efficiency_report(self) -> None:
        mgr = GPAIComplianceManager()
        eer = mgr.create_energy_efficiency_report(
            training_energy_mwh=1.0,
            inference_energy_mwh=0.5,
            carbon_emissions_tco2=0.3,
            hardware_utilization=0.85,
        )
        assert isinstance(eer, EnergyEfficiencyReport)
        assert eer.training_energy_mwh == 1.0


# ------------------------------------------------------------------ #
# GPAI Status determination
# ------------------------------------------------------------------ #

class TestGPAIStatus:
    def test_below_threshold(self) -> None:
        mgr = GPAIComplianceManager()
        assert mgr.determine_gpai_status(0.0, False) == GPAIStatus.BELOW_THRESHOLD

    def test_gpai_generative(self) -> None:
        mgr = GPAIComplianceManager()
        assert mgr.determine_gpai_status(1e23, True) == GPAIStatus.GPAI

    def test_gpai_non_generative(self) -> None:
        mgr = GPAIComplianceManager()
        assert mgr.determine_gpai_status(1e23, False) == GPAIStatus.GPAI

    def test_systemic_risk(self) -> None:
        mgr = GPAIComplianceManager()
        assert mgr.determine_gpai_status(1e25, True) == GPAIStatus.GPAI_WITH_SYSTEMIC_RISK


# ------------------------------------------------------------------ #
# Missing obligations
# ------------------------------------------------------------------ #

class TestMissingObligations:
    def test_below_threshold_all_missing(self) -> None:
        mgr = GPAIComplianceManager()
        missing = mgr.get_missing_obligations(GPAIStatus.BELOW_THRESHOLD)
        assert len(missing) == 9  # 4 Art.53 + 5 Art.55

    def test_gpai_art55_missing(self) -> None:
        mgr = GPAIComplianceManager()
        missing = mgr.get_missing_obligations(GPAIStatus.GPAI)
        assert len(missing) == 5  # Art.55 only

    def test_systemic_no_missing(self) -> None:
        mgr = GPAIComplianceManager()
        missing = mgr.get_missing_obligations(GPAIStatus.GPAI_WITH_SYSTEMIC_RISK)
        assert len(missing) == 0


# ------------------------------------------------------------------ #
# Full compliance package
# ------------------------------------------------------------------ #

class TestFullCompliancePackage:
    def test_generate_full_package_empty(self) -> None:
        mgr = GPAIComplianceManager()
        pkg = mgr.generate_full_compliance_package("test", {})
        assert "artifacts" in pkg
        assert len(pkg["artifacts"]) == 0

    def test_generate_full_package_all_artifacts(self) -> None:
        mgr = GPAIComplianceManager()
        data = {
            "technical_documentation": {"version": "1.0", "description": "test"},
            "copyright_policy": {"opt_out_mechanisms": ["robots.txt"]},
            "training_data_summary": {"data_sources": ["src"], "data_categories": ["cat"], "size_estimate": "1k"},
            "downstream_transparency": {"version": "1.0", "capable_tasks": ["t"], "limitations": ["l"], "integration_guide": "g", "hardware_requirements": {}, "evaluation_results": {}},
            "systemic_risk_assessment": {},
            "model_evaluation": {"eval_type": "standardized", "benchmark": "b", "results": {}},
            "energy_efficiency_report": {"training_energy_mwh": 1.0, "inference_energy_mwh": 0.5, "carbon_emissions_tco2": 0.3, "hardware_utilization": 0.85},
        }
        pkg = mgr.generate_full_compliance_package("test", data)
        assert len(pkg["artifacts"]) == 7

    def test_package_has_metadata(self) -> None:
        mgr = GPAIComplianceManager()
        pkg = mgr.generate_full_compliance_package("test", {})
        assert pkg["model_name"] == "test"
        assert "package_id" in pkg
        assert "generated_at" in pkg


# ------------------------------------------------------------------ #
# Engine integration
# ------------------------------------------------------------------ #

class TestGPAIEngineIntegration:
    def test_engine_setup_gpai_below_threshold(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        result = engine.setup_gpai(training_compute=0.0, is_generative=False)
        assert result["gpai_status"] == "below_threshold"
        assert len(result["missing_obligations"]) == 9

    def test_engine_setup_gpai_systemic(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        result = engine.setup_gpai(training_compute=1e25, is_generative=True)
        assert result["gpai_status"] == "gpai_with_systemic_risk"
        assert len(result["missing_obligations"]) == 0

    def test_engine_setup_gpai_artifacts(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        pkg = engine.setup_gpai_artifacts(model_name="MAREF")
        assert "artifacts" in pkg
        assert "technical_documentation" in pkg["artifacts"]
        assert "copyright_policy" in pkg["artifacts"]
        assert "training_data_summary" in pkg["artifacts"]
        assert "downstream_transparency" in pkg["artifacts"]
        assert "model_evaluation" in pkg["artifacts"]
        assert "energy_efficiency_report" in pkg["artifacts"]

    def test_engine_summary_includes_gpai(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        summary = engine.generate_summary(
            categories=[], compute_threshold=GPAIThreshold.ABOVE_10_25
        )
        assert summary.gpai_status is not None
        assert len(summary.gpai_missing_obligations) == 0

    def test_engine_setup_gpai_preserves_state(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        engine.setup_gpai(training_compute=1e25, is_generative=True)
        engine.setup_gpai_artifacts()
        assert True  # No crash on sequential calls
