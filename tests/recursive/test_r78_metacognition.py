from __future__ import annotations

import pytest

from maref.recursive.metacognition import (
    CapabilityBound,
    ConfidenceCalibrator,
    ErrorAttribution,
    EscalationProposal,
    LimitationReason,
    SelfLimitationAwareness,
    UncertaintyQuantification,
)


class TestUncertaintyQuantification:
    def test_create(self) -> None:
        uq = UncertaintyQuantification(
            aleatoric=0.1, epistemic=0.2,
            confidence_interval_low=0.3, confidence_interval_high=0.8,
        )
        assert uq.total_uncertainty == pytest.approx(0.3)
        assert uq.confidence == pytest.approx(0.7)

    def test_min_max_bounds(self) -> None:
        uq = UncertaintyQuantification(aleatoric=0.5, epistemic=0.5)
        assert uq.total_uncertainty == 1.0
        assert uq.confidence == 0.0

    def test_no_uncertainty(self) -> None:
        uq = UncertaintyQuantification()
        assert uq.total_uncertainty == 0.0
        assert uq.confidence == 1.0


class TestConfidenceCalibrator:
    def test_calibrate_single_prediction(self) -> None:
        calibrator = ConfidenceCalibrator()
        calibrator.calibrate(0.9, True)
        assert calibrator.prediction_count() == 1

    def test_calibrate_many_predictions(self) -> None:
        calibrator = ConfidenceCalibrator(max_bins=5)
        for _ in range(10):
            calibrator.calibrate(0.8, True)
        for _ in range(10):
            calibrator.calibrate(0.3, False)
        assert calibrator.prediction_count() == 20
        curve = calibrator.calibration_curve()
        assert len(curve) >= 2

    def test_expected_calibration_error(self) -> None:
        calibrator = ConfidenceCalibrator(max_bins=5)
        for _ in range(10):
            calibrator.calibrate(0.9, True)
        ece = calibrator.expected_calibration_error()
        assert ece >= 0

    def test_well_calibrated_default(self) -> None:
        calibrator = ConfidenceCalibrator()
        assert calibrator.is_well_calibrated()


class TestSelfLimitationAwareness:
    def test_register_and_check_capability(self) -> None:
        awareness = SelfLimitationAwareness()
        bound = CapabilityBound(
            capability_id="test_cap",
            min_input_complexity=0.1,
            max_input_complexity=0.9,
            success_rate=0.8,
        )
        awareness.register_bound(bound)
        assert awareness.is_within_capability(0.5, "test_cap")
        assert not awareness.is_within_capability(0.05, "test_cap")
        assert not awareness.is_within_capability(1.0, "test_cap")

    def test_unknown_capability(self) -> None:
        awareness = SelfLimitationAwareness()
        assert not awareness.is_within_capability(0.5, "nonexistent")

    def test_confidence_in_capability(self) -> None:
        awareness = SelfLimitationAwareness()
        bound = CapabilityBound(
            capability_id="test_cap",
            min_input_complexity=0.0,
            max_input_complexity=1.0,
            success_rate=0.9,
        )
        awareness.register_bound(bound)
        confidence = awareness.confidence_in_capability("test_cap", 0.5)
        assert confidence > 0.7

    def test_unknown_response(self) -> None:
        awareness = SelfLimitationAwareness()
        response = awareness.unknown_response("What is the meaning of life?")
        assert "cannot answer" in response.lower()
        assert len(awareness.unknown_response_log()) == 1

    def test_suggest_escalation(self) -> None:
        awareness = SelfLimitationAwareness()
        proposal = awareness.suggest_escalation(LimitationReason.BEYOND_CAPABILITY)
        assert isinstance(proposal, EscalationProposal)
        assert proposal.reason == LimitationReason.BEYOND_CAPABILITY

    def test_known_capabilities(self) -> None:
        awareness = SelfLimitationAwareness()
        awareness.register_bound(CapabilityBound("cap_a"))
        awareness.register_bound(CapabilityBound("cap_b"))
        bounds = awareness.known_capabilities()
        assert len(bounds) == 2


class TestErrorAttribution:
    def test_attribute_dependency_error(self) -> None:
        attributor = ErrorAttribution()
        result = attributor.attribute("ModuleNotFoundError: No module named 'foo'", {})
        assert result.attribution == "dependency_error"

    def test_attribute_environment_error(self) -> None:
        attributor = ErrorAttribution()
        result = attributor.attribute("Connection refused: timeout", {})
        assert result.attribution == "environment_error"

    def test_attribute_input_error(self) -> None:
        attributor = ErrorAttribution()
        result = attributor.attribute("Validation error: invalid input format", {})
        assert result.attribution == "input_error"

    def test_attribute_self_error(self) -> None:
        attributor = ErrorAttribution()
        result = attributor.attribute("Assertion failed: unexpected result", {})
        assert result.attribution == "self_error"

    def test_attribute_unknown(self) -> None:
        attributor = ErrorAttribution()
        result = attributor.attribute("Something weird happened", {})
        assert result.attribution == "unknown"
        assert result.confidence < 0.5

    def test_attribution_stats(self) -> None:
        attributor = ErrorAttribution()
        attributor.attribute("ModuleNotFoundError", {})
        attributor.attribute("Connection refused", {})
        attributor.attribute("ModuleNotFoundError", {})

        stats = attributor.attribution_stats()
        assert stats["dependency_error"] == 2
        assert stats["environment_error"] == 1
