"""Tests for EU AI Act human oversight (Art.14)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.human_oversight import (
    HumanOversightAssessment,
    HumanOversightBridge,
    OversightCapability,
    OversightCapabilityStatus,
    OversightMode,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import RiskLevel


class TestOversightCapability:
    def test_all_capabilities_defined(self) -> None:
        assert len(OversightCapability) == 6

    def test_values_unique(self) -> None:
        values = [c.value for c in OversightCapability]
        assert len(values) == len(set(values))

    def test_understand_value(self) -> None:
        assert OversightCapability.UNDERSTAND.value == "understand"

    def test_bias_awareness_value(self) -> None:
        assert OversightCapability.BIAS_AWARENESS.value == "bias_awareness"

    def test_interpret_output_value(self) -> None:
        assert OversightCapability.INTERPRET_OUTPUT.value == "interpret_output"

    def test_override_stop_value(self) -> None:
        assert OversightCapability.OVERRIDE_STOP.value == "override_stop"

    def test_stop_button_value(self) -> None:
        assert OversightCapability.STOP_BUTTON.value == "stop_button"

    def test_real_time_monitor_value(self) -> None:
        assert OversightCapability.REAL_TIME_MONITOR.value == "real_time_monitor"


class TestOversightMode:
    def test_all_modes_defined(self) -> None:
        assert len(OversightMode) == 3

    def test_mode_values_unique(self) -> None:
        values = [m.value for m in OversightMode]
        assert len(values) == len(set(values))

    def test_hitl_value(self) -> None:
        assert OversightMode.HITL.value == "hitl"

    def test_hotl_value(self) -> None:
        assert OversightMode.HOTL.value == "hotl"

    def test_hatl_value(self) -> None:
        assert OversightMode.HATL.value == "hatl"

    def test_hitl_description(self) -> None:
        desc = OversightMode.HITL.description()
        assert "Human-In-The-Loop" in desc
        assert "every action" in desc

    def test_hotl_description(self) -> None:
        desc = OversightMode.HOTL.description()
        assert "Human-On-The-Loop" in desc
        assert "intervention" in desc

    def test_hatl_description(self) -> None:
        desc = OversightMode.HATL.description()
        assert "Human-Across-The-Loop" in desc
        assert "audit" in desc


class TestOversightCapabilityStatus:
    def test_dataclass_construction(self) -> None:
        status = OversightCapabilityStatus(
            capability=OversightCapability.UNDERSTAND,
            implemented=True,
            details="Documentation provided",
        )
        assert status.capability == OversightCapability.UNDERSTAND
        assert status.implemented is True
        assert status.details == "Documentation provided"

    def test_dataclass_not_implemented(self) -> None:
        status = OversightCapabilityStatus(
            capability=OversightCapability.STOP_BUTTON,
            implemented=False,
            details="Not configured",
        )
        assert status.implemented is False
        assert status.details == "Not configured"


class TestHumanOversightAssessment:
    def test_dataclass_construction(self) -> None:
        cap = OversightCapabilityStatus(
            capability=OversightCapability.STOP_BUTTON,
            implemented=True,
            details="Stop button configured",
        )
        assessment = HumanOversightAssessment(
            overall_score=0.8,
            capabilities=[cap],
            recommended_mode=OversightMode.HITL,
            gaps=["Missing logging"],
            recommendations=["Add logging"],
        )
        assert assessment.overall_score == 0.8
        assert len(assessment.capabilities) == 1
        assert assessment.recommended_mode == OversightMode.HITL
        assert assessment.gaps == ["Missing logging"]
        assert assessment.recommendations == ["Add logging"]

    def test_dataclass_no_gaps(self) -> None:
        assessment = HumanOversightAssessment(
            overall_score=1.0,
            capabilities=[],
            recommended_mode=OversightMode.HITL,
            gaps=[],
            recommendations=[],
        )
        assert assessment.gaps == []
        assert assessment.overall_score == 1.0


class TestHumanOversightBridge:
    def test_initialise_with_system_context(self) -> None:
        bridge = HumanOversightBridge(
            system_name="TestSystem",
            risk_level=RiskLevel.HIGH,
        )
        assert bridge.system_name == "TestSystem"
        assert bridge.risk_level == RiskLevel.HIGH

    def test_assess_capabilities_high_risk_all_implemented(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        assessment = bridge.assess_capabilities()
        for cap_status in assessment.capabilities:
            assert cap_status.implemented is True, (
                f"{cap_status.capability.value} should be implemented for HIGH risk"
            )
        assert assessment.overall_score == 1.0
        assert len(assessment.gaps) == 0
        assert len(assessment.recommendations) == 0

    def test_assess_capabilities_minimal_risk_only_understand(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.MINIMAL)
        assessment = bridge.assess_capabilities()
        implemented = [c for c in assessment.capabilities if c.implemented]
        assert len(implemented) == 1
        assert implemented[0].capability == OversightCapability.UNDERSTAND

    def test_assess_capabilities_gpai_coverage(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI)
        assessment = bridge.assess_capabilities()
        implemented_caps = {c.capability for c in assessment.capabilities if c.implemented}
        assert OversightCapability.UNDERSTAND in implemented_caps
        assert OversightCapability.BIAS_AWARENESS in implemented_caps
        assert OversightCapability.INTERPRET_OUTPUT in implemented_caps
        assert OversightCapability.REAL_TIME_MONITOR in implemented_caps
        assert OversightCapability.STOP_BUTTON not in implemented_caps
        assert OversightCapability.OVERRIDE_STOP not in implemented_caps

    def test_assess_capabilities_unacceptable_no_capabilities(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.UNACCEPTABLE)
        assessment = bridge.assess_capabilities()
        assert assessment.overall_score == 0.0
        implemented = [c for c in assessment.capabilities if c.implemented]
        assert len(implemented) == 0
        assert len(assessment.recommendations) == 6

    def test_assess_capabilities_gpai_systemic_coverage(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI_WITH_SYSTEMIC_RISK)
        assessment = bridge.assess_capabilities()
        implemented_caps = {c.capability for c in assessment.capabilities if c.implemented}
        assert OversightCapability.UNDERSTAND in implemented_caps
        assert OversightCapability.BIAS_AWARENESS in implemented_caps
        assert OversightCapability.INTERPRET_OUTPUT in implemented_caps
        assert OversightCapability.OVERRIDE_STOP in implemented_caps
        assert OversightCapability.REAL_TIME_MONITOR in implemented_caps
        assert OversightCapability.STOP_BUTTON not in implemented_caps

    def test_assess_capabilities_limited_coverage(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.LIMITED)
        assessment = bridge.assess_capabilities()
        implemented_caps = {c.capability for c in assessment.capabilities if c.implemented}
        assert OversightCapability.UNDERSTAND in implemented_caps
        assert OversightCapability.BIAS_AWARENESS in implemented_caps
        assert OversightCapability.INTERPRET_OUTPUT in implemented_caps
        assert OversightCapability.STOP_BUTTON not in implemented_caps
        assert OversightCapability.OVERRIDE_STOP not in implemented_caps

    def test_recommend_oversight_mode_high(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HITL

    def test_recommend_oversight_mode_unacceptable(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.UNACCEPTABLE)
        mode = bridge.recommend_oversight_mode()
        assert mode is None

    def test_recommend_oversight_mode_gpai_systemic(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI_WITH_SYSTEMIC_RISK)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HOTL

    def test_recommend_oversight_mode_gpai(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HOTL

    def test_recommend_oversight_mode_limited(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.LIMITED)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HATL

    def test_recommend_oversight_mode_minimal(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.MINIMAL)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HATL

    def test_recommend_oversight_mode_explicit_risk_override(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.MINIMAL)
        mode = bridge.recommend_oversight_mode(risk_level=RiskLevel.HIGH)
        assert mode == OversightMode.HITL

    def test_verify_stop_button_high_risk_required(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        result = bridge.verify_stop_button()
        assert result["stop_button_required"] is True
        assert result["stop_button_configured"] is True
        assert result["verification_status"] == "passed"
        assert "Art.14(2)(e)" in result["details"]

    def test_verify_stop_button_minimal_not_required(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.MINIMAL)
        result = bridge.verify_stop_button()
        assert result["stop_button_required"] is False
        assert result["verification_status"] == "not_required"

    def test_verify_stop_button_gpai_not_required(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI)
        result = bridge.verify_stop_button()
        assert result["stop_button_required"] is False

    def test_verify_stop_button_limited_not_required(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.LIMITED)
        result = bridge.verify_stop_button()
        assert result["stop_button_required"] is False

    def test_check_automation_bias_high_risk(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        result = bridge.check_automation_bias_mitigation()
        assert result["bias_mitigation_active"] is True
        assert result["active_measure_count"] == 6
        assert result["total_measure_count"] == 6

    def test_check_automation_bias_minimal_risk(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.MINIMAL)
        result = bridge.check_automation_bias_mitigation()
        assert result["bias_mitigation_active"] is True
        assert result["active_measure_count"] == 1
        assert result["total_measure_count"] == 1

    def test_check_automation_bias_limited_risk(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.LIMITED)
        result = bridge.check_automation_bias_mitigation()
        assert result["active_measure_count"] == 2

    def test_check_automation_bias_gpai(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI)
        result = bridge.check_automation_bias_mitigation()
        assert result["active_measure_count"] == 4  # no alternative inputs, no mandatory human review

    def test_check_automation_bias_gpai_systemic(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.GPAI_WITH_SYSTEMIC_RISK)
        result = bridge.check_automation_bias_mitigation()
        assert result["active_measure_count"] == 4

    def test_set_oversight_config_valid(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        caps = [
            OversightCapability.UNDERSTAND,
            OversightCapability.BIAS_AWARENESS,
            OversightCapability.STOP_BUTTON,
        ]
        result = bridge.set_oversight_config(OversightMode.HITL, caps)
        assert result["configured_mode"] == "hitl"
        assert result["mode_matches_recommendation"] is True
        assert len(result["configured_capabilities"]) == 3
        assert "understand" in result["configured_capabilities"]

    def test_set_oversight_config_empty_capabilities_raises(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        try:
            bridge.set_oversight_config(OversightMode.HITL, [])
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_set_oversight_config_unacceptable_raises(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.UNACCEPTABLE)
        try:
            bridge.set_oversight_config(
                OversightMode.HITL,
                [OversightCapability.UNDERSTAND],
            )
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_set_oversight_config_mode_mismatch(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        caps = [OversightCapability.UNDERSTAND]
        result = bridge.set_oversight_config(OversightMode.HATL, caps)
        assert result["mode_matches_recommendation"] is False

    def test_generate_oversight_report_high_risk_compliant(self) -> None:
        bridge = HumanOversightBridge("TestSystem", RiskLevel.HIGH)
        report = bridge.generate_oversight_report()
        assert report["system_name"] == "TestSystem"
        assert report["risk_level"] == "high"
        assert report["overall_compliant"] is True
        assert report["overall_compliance_score"] == 100.0
        assert report["recommended_oversight_mode"] == "hitl"
        assert "Art.14(1)" in report["compliance_articles"]
        assert len(report["identified_gaps"]) == 0
        assert "stop_button_verification" in report
        assert "automation_bias_mitigation" in report
        assert len(report["capability_assessment"]) == 6

    def test_generate_oversight_report_minimal_risk_not_fully_compliant(self) -> None:
        bridge = HumanOversightBridge("MinimalSys", RiskLevel.MINIMAL)
        report = bridge.generate_oversight_report()
        assert report["overall_compliant"] is False
        assert abs(report["overall_compliance_score"] - 16.7) < 0.1
        assert report["recommended_oversight_mode"] == "hatl"
        assert len(report["identified_gaps"]) == 5

    def test_generate_oversight_report_unacceptable_compliant_by_definition(self) -> None:
        bridge = HumanOversightBridge("BadSys", RiskLevel.UNACCEPTABLE)
        report = bridge.generate_oversight_report()
        assert report["overall_compliant"] is True
        assert report["recommended_oversight_mode"] == "N/A (UNACCEPTABLE)"
        assert report["overall_compliance_score"] == 0.0

    def test_generate_oversight_report_gpai(self) -> None:
        bridge = HumanOversightBridge("GPatch", RiskLevel.GPAI)
        report = bridge.generate_oversight_report()
        assert report["risk_level"] == "gpai"
        assert report["recommended_oversight_mode"] == "hotl"
        assert 0 < report["overall_compliance_score"] < 100

    def test_assessment_cached_after_first_call(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        first = bridge.assess_capabilities()
        second = bridge.assess_capabilities()
        assert first is second

    def test_report_generated_without_explicit_assessment(self) -> None:
        bridge = HumanOversightBridge("TestAI", RiskLevel.HIGH)
        report = bridge.generate_oversight_report()
        assert report["overall_compliance_score"] == 100.0
