"""Smoke tests for maref.stress.adversarial_test_suite."""
from __future__ import annotations

import pytest

from maref.stress.adversarial_test_suite import AdversarialResult


class TestAdversarialResult:
    def test_init_default(self) -> None:
        result = AdversarialResult(test_type="byzantine", scenario="tamper_0.5", success=True)
        assert result.test_type == "byzantine"
        assert result.scenario == "tamper_0.5"
        assert result.success is True
        assert result.detection_rate == 0.0
        assert result.metadata == {}

    def test_init_custom(self) -> None:
        result = AdversarialResult(
            test_type="emergent", scenario="state_conflict", success=False,
            detection_rate=0.8, recovery_time_ms=150.0,
            quality_degradation=0.3, details="Detected conflict",
            metadata={"agent_count": 2},
        )
        assert result.test_type == "emergent"
        assert result.detection_rate == 0.8
        assert result.recovery_time_ms == 150.0
        assert result.metadata == {"agent_count": 2}
