"""Tests for metacognition.py — ConfidenceCalibrator, SelfLimitationAwareness, ErrorAttribution."""
from __future__ import annotations

import pytest

from maref.recursive.metacognition import (
    AttributionResult,
    CapabilityBound,
    ConfidenceCalibrator,
    ErrorAttribution,
    EscalationProposal,
    LimitationReason,
    SelfLimitationAwareness,
    UncertaintyQuantification,
)


class TestUncertaintyQuantification:
    @pytest.mark.slow
    def test_total_uncertainty(self):
        uq = UncertaintyQuantification(aleatoric=0.3, epistemic=0.2)
        assert uq.total_uncertainty == 0.5

    @pytest.mark.slow
    def test_total_uncertainty_clamped(self):
        uq = UncertaintyQuantification(aleatoric=0.6, epistemic=0.6)
        assert uq.total_uncertainty == 1.0

    @pytest.mark.slow
    def test_confidence(self):
        uq = UncertaintyQuantification(aleatoric=0.2, epistemic=0.1)
        assert uq.confidence == 0.7

    @pytest.mark.slow
    def test_confidence_zero(self):
        uq = UncertaintyQuantification(aleatoric=1.0, epistemic=1.0)
        assert uq.confidence == 0.0


class TestConfidenceCalibrator:
    @pytest.mark.slow
    def test_calibrate(self):
        cc = ConfidenceCalibrator(max_bins=10)
        cc.calibrate(0.9, True)
        cc.calibrate(0.1, False)
        assert cc.prediction_count() == 2

    @pytest.mark.slow
    def test_calibration_curve_empty(self):
        cc = ConfidenceCalibrator()
        curve = cc.calibration_curve()
        assert curve == []
        assert cc.expected_calibration_error() == 0.0

    @pytest.mark.slow
    def test_calibration_curve(self):
        cc = ConfidenceCalibrator(max_bins=5)
        for _ in range(10):
            cc.calibrate(0.9, True)
            cc.calibrate(0.1, False)
        curve = cc.calibration_curve()
        assert len(curve) > 0
        for conf, acc in curve:
            assert 0 <= conf <= 1
            assert 0 <= acc <= 1

    @pytest.mark.slow
    def test_is_well_calibrated(self):
        cc = ConfidenceCalibrator(max_bins=5)
        for _ in range(10):
            cc.calibrate(1.0, True)
        assert cc.is_well_calibrated(threshold=0.5) is True

    @pytest.mark.slow
    def test_perfect_calibration(self):
        cc = ConfidenceCalibrator(max_bins=5)
        for _ in range(5):
            cc.calibrate(1.0, True)
        assert cc.is_well_calibrated() is True


class TestSelfLimitationAwareness:
    @pytest.mark.slow
    def test_register_bound(self):
        sla = SelfLimitationAwareness()
        bound = CapabilityBound("code_gen", min_input_complexity=0.0, max_input_complexity=1.0)
        sla.register_bound(bound)
        assert len(sla.known_capabilities()) == 1

    @pytest.mark.slow
    def test_is_within_capability(self):
        sla = SelfLimitationAwareness()
        sla.register_bound(CapabilityBound("code_gen", 0.0, 1.0))
        assert sla.is_within_capability(0.5, "code_gen") is True
        assert sla.is_within_capability(1.5, "code_gen") is False
        assert sla.is_within_capability(0.5, "unknown") is False

    @pytest.mark.slow
    def test_confidence_in_capability_unknown(self):
        sla = SelfLimitationAwareness()
        assert sla.confidence_in_capability("unknown", 0.5) == 0.0

    @pytest.mark.slow
    def test_confidence_in_capability_out_of_range(self):
        sla = SelfLimitationAwareness()
        sla.register_bound(CapabilityBound("code_gen", 0.0, 0.5))
        assert sla.confidence_in_capability("code_gen", 1.0) == 0.0

    @pytest.mark.slow
    def test_confidence_in_capability_within_range(self):
        sla = SelfLimitationAwareness()
        sla.register_bound(CapabilityBound("code_gen", 0.0, 1.0, success_rate=0.8))
        confidence = sla.confidence_in_capability("code_gen", 0.5)
        assert confidence > 0

    @pytest.mark.slow
    def test_confidence_zero_range(self):
        sla = SelfLimitationAwareness()
        sla.register_bound(CapabilityBound("pinpoint", 0.5, 0.5, success_rate=0.9))
        assert sla.confidence_in_capability("pinpoint", 0.5) == 0.9

    @pytest.mark.slow
    def test_unknown_response(self):
        sla = SelfLimitationAwareness()
        response = sla.unknown_response("What is the meaning of life?")
        assert "cannot answer" in response
        assert len(sla.unknown_response_log()) == 1

    @pytest.mark.slow
    def test_suggest_escalation(self):
        sla = SelfLimitationAwareness()
        proposal = sla.suggest_escalation(LimitationReason.BEYOND_CAPABILITY)
        assert isinstance(proposal, EscalationProposal)
        assert "beyond_capability" in proposal.suggestion


class TestErrorAttribution:
    @pytest.mark.slow
    def test_attribute_dependency_error(self):
        ea = ErrorAttribution()
        result = ea.attribute("ModuleNotFoundError: missing package", {"file": "test.py"})
        assert result.attribution == "dependency_error"
        assert result.confidence == 0.7

    @pytest.mark.slow
    def test_attribute_timeout_error(self):
        ea = ErrorAttribution()
        result = ea.attribute("Connection timed out after 30s", {})
        assert result.attribution == "environment_error"

    @pytest.mark.slow
    def test_attribute_permission_error(self):
        ea = ErrorAttribution()
        result = ea.attribute("Permission denied: access to /etc/shadow", {})
        assert result.attribution == "environment_error"

    @pytest.mark.slow
    def test_attribute_input_error(self):
        ea = ErrorAttribution()
        result = ea.attribute("Invalid input: expected integer", {})
        assert result.attribution == "input_error"

    @pytest.mark.slow
    def test_attribute_self_error(self):
        ea = ErrorAttribution()
        result = ea.attribute("AssertionError: expected True, got False", {})
        assert result.attribution == "self_error"

    @pytest.mark.slow
    def test_attribute_unknown(self):
        ea = ErrorAttribution()
        result = ea.attribute("Something completely unexpected happened", {})
        assert result.attribution == "unknown"
        assert result.confidence == 0.3

    @pytest.mark.slow
    def test_history(self):
        ea = ErrorAttribution()
        ea.attribute("error 1", {})
        ea.attribute("error 2", {})
        assert len(ea.history()) == 2

    @pytest.mark.slow
    def test_attribution_stats(self):
        ea = ErrorAttribution()
        ea.attribute("ModuleNotFoundError", {})
        ea.attribute("timeout", {})
        ea.attribute("timeout", {})
        stats = ea.attribution_stats()
        assert stats["dependency_error"] == 1
        assert stats["environment_error"] == 2
