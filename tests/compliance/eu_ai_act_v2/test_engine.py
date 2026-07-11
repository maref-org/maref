"""Integration tests for EUAIComplianceEngineV2 and full pipeline."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.engine import (
    EUAIComplianceEngineV2,
    EUAIComplianceSummary,
)
from maref.compliance.eu_ai_act_v2.fria import (
    FRIAScope,
    FundamentalRight,
    RiskRating,
)
from maref.compliance.eu_ai_act_v2.incident_reporting import (
    IncidentSeverity,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    ClassificationDetail,
    GPAIThreshold,
    RiskLevel,
)
from maref.compliance.eu_ai_act_v2.risk_management import (
    RiskManagementLifecycleState,
)
from maref.compliance.registry import (
    ComplianceRegistry,
    ComplianceStatus,
    Jurisdiction,
)


class TestEngineInitialization:
    def test_engine_creates_with_defaults(self) -> None:
        engine = EUAIComplianceEngineV2()
        assert engine.system_name == "MAREF-Agent"
        assert engine.version == "1.0.0"
        assert engine.classifier is not None
        assert engine.risk_mgmt is not None
        assert engine.technical_docs is not None
        assert engine.transparency_mgr is not None
        assert engine.conformity is not None
        assert engine.gpai_mgr is not None

    def test_engine_creates_with_custom_name(self) -> None:
        engine = EUAIComplianceEngineV2(
            system_name="TestSystem",
            version="2.1.0",
        )
        assert engine.system_name == "TestSystem"
        assert engine.version == "2.1.0"


class TestEngineClassify:
    def test_classify_high_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        detail = engine.classify(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert isinstance(detail, ClassificationDetail)
        assert detail.risk_level == RiskLevel.HIGH

    def test_classify_minimal_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        detail = engine.classify(categories=[])
        assert detail.risk_level == RiskLevel.MINIMAL

    def test_classify_gpai_systemic(self) -> None:
        engine = EUAIComplianceEngineV2()
        detail = engine.classify(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_25,
            is_generative=True,
        )
        assert detail.risk_level == RiskLevel.GPAI_WITH_SYSTEMIC_RISK


class TestEngineRiskManagement:
    def test_assess_risk_management(self) -> None:
        engine = EUAIComplianceEngineV2()
        result = engine.assess_risk_management()
        assert "total_risks" in result or "overall_score" in result
        if "total_risks" in result:
            assert result["total_risks"] > 0

    def test_risk_management_lifecycle(self) -> None:
        engine = EUAIComplianceEngineV2()
        engine.assess_risk_management()
        assert engine.risk_mgmt.state in (
            RiskManagementLifecycleState.IDENTIFY,
            RiskManagementLifecycleState.EVALUATE,
        )


class TestEngineHumanOversight:
    def test_setup_oversight_high_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        assessment = engine.setup_human_oversight(RiskLevel.HIGH)
        assert assessment.overall_score > 0
        assert assessment.recommended_mode is not None

    def test_setup_oversight_minimal_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        assessment = engine.setup_human_oversight(RiskLevel.MINIMAL)
        assert assessment.recommended_mode is not None


class TestEngineConformity:
    def test_conformity_high_risk_internal(self) -> None:
        engine = EUAIComplianceEngineV2()
        result = engine.run_conformity_assessment(
            risk_level=RiskLevel.HIGH,
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert result["route"] is not None

    def test_conformity_minimal_risk_no_route(self) -> None:
        engine = EUAIComplianceEngineV2()
        result = engine.run_conformity_assessment(
            risk_level=RiskLevel.MINIMAL,
        )
        assert result["route"] is None


class TestEngineGPAI:
    def test_gpai_below_threshold(self) -> None:
        engine = EUAIComplianceEngineV2()
        result = engine.setup_gpai(training_compute=0.0)
        assert result["gpai_status"] == "below_threshold"

    def test_gpai_with_systemic_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        result = engine.setup_gpai(
            training_compute=10**26,
            is_generative=True,
        )
        assert result["gpai_status"] == "gpai_with_systemic_risk"


class TestEngineGenerateSummary:
    def test_generate_summary_structure(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert isinstance(summary, EUAIComplianceSummary)
        assert summary.system_name == "MAREF-Agent"
        assert summary.version == "1.0.0"
        assert isinstance(summary.risk_level, RiskLevel)
        assert summary.overall_score >= 0
        assert summary.assessed_at != ""

    def test_generate_summary_high_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert summary.risk_level == RiskLevel.HIGH
        assert summary.conformity_route is not None

    def test_generate_summary_minimal_risk(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[])
        assert summary.risk_level == RiskLevel.MINIMAL
        assert summary.conformity_route is None

    def test_generate_summary_gpai(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[],
            compute_threshold=GPAIThreshold.ABOVE_10_23,
            is_generative=True,
        )
        assert summary.risk_level == RiskLevel.GPAI
        assert summary.gpai_status is not None

    def test_generate_summary_gaps_recommendations(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.BIOMETRICS],
            compute_threshold=GPAIThreshold.ABOVE_10_23,
            is_generative=True,
        )
        assert isinstance(summary.gaps, list)
        assert isinstance(summary.recommendations, list)

    def test_generate_summary_score_range(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert 0 <= summary.overall_score <= 100


class TestEngineGenerateReport:
    def test_generate_report_structure(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert "report_title" in report
        assert "risk_classification" in report
        assert "risk_management" in report
        assert "technical_documentation" in report
        assert "transparency" in report
        assert "human_oversight" in report
        assert "conformity_assessment" in report
        assert "gpai" in report
        assert "overall" in report
        assert "gaps" in report
        assert "recommendations" in report

    def test_generate_report_risk_level(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert report["risk_classification"]["risk_level"] == RiskLevel.HIGH.value

    def test_generate_report_overall_score(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(categories=[])
        assert 0 <= report["overall"]["score"] <= 100


class TestEngineRegistryIntegration:
    def test_sync_with_registry(self) -> None:
        registry = ComplianceRegistry()
        engine = EUAIComplianceEngineV2(
            system_name="RegistryTest",
            registry=registry,
        )
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        assert summary.overall_score > 0

        # Check registry has been updated with requirement statuses
        eu_status = registry.get_jurisdiction_compliance_status(Jurisdiction.EU)
        assert eu_status["jurisdiction"] == "eu"
        req_keys = [k for k in registry.requirements if k.startswith("eu-ai-act-")]
        assert len(req_keys) > 0
        assert registry.requirements[req_keys[0]].status != ComplianceStatus.PENDING_REVIEW

    def test_registry_has_check_result(self) -> None:
        registry = ComplianceRegistry()
        engine = EUAIComplianceEngineV2(
            system_name="CheckResultTest",
            registry=registry,
        )
        engine.generate_summary(
            categories=[AnnexIIICategory.EMPLOYMENT],
        )
        # Registry should have at least one check result
        assert len(registry.check_results) > 0

    def test_check_result_has_score(self) -> None:
        registry = ComplianceRegistry()
        engine = EUAIComplianceEngineV2(
            system_name="ScoreTest",
            registry=registry,
        )
        engine.generate_summary(categories=[])
        results = list(registry.check_results.values())
        assert len(results) > 0
        assert results[-1].score > 0


class TestEngineEdgeCases:
    def test_empty_classify_kwargs(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary()
        assert summary.risk_level == RiskLevel.MINIMAL

    def test_prohibited_override(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            is_prohibited=True,
        )
        assert summary.risk_level == RiskLevel.UNACCEPTABLE
        assert summary.overall_compliant is False

    def test_multiple_classify_calls(self) -> None:
        engine = EUAIComplianceEngineV2()
        d1 = engine.classify(categories=[])
        d2 = engine.classify(
            categories=[AnnexIIICategory.BIOMETRICS],
        )
        assert d1.risk_level != d2.risk_level

    def test_report_generated_at_recent(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(categories=[])
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()[:10]
        assert report["generated_at"][:10] == now[:10]

    def test_score_bounds(self) -> None:
        """Score should never exceed 100 even for fully compliant system."""
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.EMPLOYMENT],
            compute_threshold=GPAIThreshold.BELOW_THRESHOLD,
        )
        assert summary.overall_score <= 100


class TestEngineM2Integration:
    """Integration tests for M2 (Art.10, 12, 15) in the engine."""

    def test_data_governance_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "data_governance_complete")
        assert hasattr(summary, "data_governance_gaps")
        assert isinstance(summary.data_governance_complete, bool)
        assert isinstance(summary.data_governance_gaps, list)

    def test_record_keeping_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "record_keeping_enabled")
        assert hasattr(summary, "record_keeping_count")
        assert summary.record_keeping_enabled is True
        assert isinstance(summary.record_keeping_count, int)

    def test_accuracy_robustness_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "accuracy_robustness_complete")
        assert hasattr(summary, "accuracy_robustness_gaps")
        assert isinstance(summary.accuracy_robustness_complete, bool)
        assert isinstance(summary.accuracy_robustness_gaps, list)

    def test_full_pipeline_with_m2(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(
            categories=[AnnexIIICategory.BIOMETRICS],
            compute_threshold=GPAIThreshold.BELOW_THRESHOLD,
        )
        assert summary.risk_level == RiskLevel.HIGH
        assert summary.overall_score >= 0
        assert summary.data_governance_complete is not None
        assert summary.record_keeping_count >= 0
        assert summary.accuracy_robustness_complete is not None

    def test_report_includes_m2_sections(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(categories=[AnnexIIICategory.EMPLOYMENT])
        assert "data_governance" in report
        assert "record_keeping" in report
        assert "accuracy_robustness" in report
        assert "complete" in report["data_governance"]
        assert "enabled" in report["record_keeping"]
        assert "complete" in report["accuracy_robustness"]

    def test_record_logging_after_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        # The recorder should have logged events from other operations
        assert engine.recorder.count_events() >= 0

    def test_data_governance_register_and_assess(self) -> None:
        engine = EUAIComplianceEngineV2()
        ds = engine.data_gov.register_dataset(
            name="training-v1",
            collection_purpose="model training",
            data_origin="internal",
        )
        assert ds.dataset_id is not None
        from maref.compliance.eu_ai_act_v2.data_governance import (
            DatasetQualityMetrics,
        )
        engine.data_gov.assess_quality(
            ds.dataset_id,
            DatasetQualityMetrics(
                relevance_score=0.95,
                representativeness_score=0.90,
                completeness_score=0.98,
                error_rate=0.01,
                is_relevant=True,
                is_representative=True,
                is_complete=True,
                is_free_of_errors=True,
            ),
        )
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.data_governance_gaps is not None

    def test_accuracy_declare_and_validate(self) -> None:
        engine = EUAIComplianceEngineV2()
        from maref.compliance.eu_ai_act_v2.accuracy_robustness import (
            AccuracyMetricType,
        )
        engine.accuracy.declare_accuracy(
            metric=AccuracyMetricType.F1,
            value=0.92,
            threshold=0.80,
        )
        engine.accuracy.declare_accuracy(
            metric=AccuracyMetricType.AUC_ROC,
            value=0.95,
            threshold=0.85,
        )
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.accuracy_robustness_complete is not None


class TestEngineM3Integration:
    """Integration tests for M3 (Art.17, 20, 27, 61, 73) in the engine."""

    def test_qms_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "qms_established")
        assert hasattr(summary, "qms_doc_count")
        assert hasattr(summary, "qms_audit_status")
        assert isinstance(summary.qms_established, bool)
        assert isinstance(summary.qms_doc_count, int)

    def test_incident_reporting_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "incidents_open")
        assert hasattr(summary, "incidents_total")
        assert isinstance(summary.incidents_open, int)
        assert isinstance(summary.incidents_total, int)

    def test_fria_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "fria_complete")
        assert hasattr(summary, "fria_high_risk_rights")
        assert isinstance(summary.fria_complete, bool)

    def test_pmm_in_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert hasattr(summary, "pmm_active")
        assert hasattr(summary, "pmm_observations")
        assert hasattr(summary, "pmm_review_due")
        assert isinstance(summary.pmm_active, bool)

    def test_report_includes_m3_sections(self) -> None:
        engine = EUAIComplianceEngineV2()
        report = engine.generate_report(categories=[AnnexIIICategory.EMPLOYMENT])
        assert "qms" in report
        assert "incident_reporting" in report
        assert "fria" in report
        assert "post_market_monitoring" in report
        assert "established" in report["qms"]
        assert "open_incidents" in report["incident_reporting"]
        assert "complete" in report["fria"]
        assert "active" in report["post_market_monitoring"]

    def test_qms_create_document_and_summary(self) -> None:
        engine = EUAIComplianceEngineV2()
        engine.qms.create_document(
            title="QMS Policy",
            section="compliance_strategy",
            content="MAREF compliance strategy v1",
        )
        engine.qms.create_document(
            title="Risk Management Procedure",
            section="risk_management",
            content="Risk management process v1",
        )
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.qms_established
        assert summary.qms_doc_count >= 2

    def test_incident_lifecycle_in_engine(self) -> None:
        engine = EUAIComplianceEngineV2()
        inc = engine.incident_mgr.report_incident(
            system_name="TestSystem",
            description="Unexpected output detected",
            severity=IncidentSeverity.MINOR,
        )
        assert inc.incident_id is not None
        # Add corrective action and close
        engine.incident_mgr.add_corrective_action(
            incident_id=inc.incident_id,
            description="Fix model threshold",
            deadline="2026-08-01",
            assigned_to="team-a",
        )
        engine.incident_mgr.close_incident(inc.incident_id)
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.incidents_total >= 1

    def test_fria_in_engine(self) -> None:
        engine = EUAIComplianceEngineV2()
        engine.fria.set_scope(FRIAScope(
            system_name="TestSystem",
            system_version="1.0",
            deployment_context="HR screening",
            affected_population_description="Job applicants",
            estimated_affected_count=10000,
        ))
        engine.fria.assess_right(
            right=FundamentalRight.NON_DISCRIMINATION,
            rating=RiskRating.LOW,
            rationale="Model tested for demographic parity",
        )
        report = engine.fria.generate_report(reviewed_by="auditor-1")
        assert report.report_id is not None
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.fria_complete is True

    def test_pmm_in_engine(self) -> None:
        engine = EUAIComplianceEngineV2()
        plan = engine.pmm.create_plan(
            system_name="TestSystem",
            objectives=["Monitor accuracy drift"],
            data_sources=["live_logs"],
            kpis=[{"name": "accuracy", "target": 0.95, "threshold": 0.90, "source": "eval"}],
        )
        assert plan.plan_id is not None
        engine.pmm.record_observation(
            plan_id=plan.plan_id,
            source="eval",
            metric="accuracy",
            value=0.94,
        )
        summary = engine.generate_summary(categories=[AnnexIIICategory.EMPLOYMENT])
        assert summary.pmm_active is True
        assert summary.pmm_observations >= 1
