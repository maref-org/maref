"""Tests for EvolutionQualityGate integration into RecursiveEvolutionEngine."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.evolution.engine import RecursiveEvolutionEngine, EvolutionConfig
from maref.integration.test_platform.quality_gate import (
    EvolutionQualityGate,
    QualityGateConfig,
)


class TestEvolutionEngineQualityGate:
    def test_engine_accepts_quality_gate(self):
        gate = EvolutionQualityGate()
        engine = RecursiveEvolutionEngine(quality_gate=gate)
        assert engine.quality_gate is gate

    def test_quality_gate_used_in_c1_to_c2(self):
        gate = MagicMock()
        gate.build_mock_report.return_value = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict.value = "approved"

        engine = RecursiveEvolutionEngine(quality_gate=gate)
        result = engine.evaluate_candidate_with_quality_gate(
            candidate_id="test", cycle="c1", score=85.0,
        )
        assert result.get("verdict") == "approved"
        gate.evaluate_c1_to_c2.assert_called_once()

    def test_quality_gate_rejects_candidate(self):
        gate = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict.value = "rejected"

        engine = RecursiveEvolutionEngine(quality_gate=gate)
        result = engine.evaluate_candidate_with_quality_gate(
            candidate_id="test", cycle="c1", score=55.0,
        )
        assert result.get("verdict") == "rejected"

    def test_evolution_engine_stops_on_quality_gate_failure(self):
        gate = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict = MagicMock()
        gate.evaluate_c1_to_c2.return_value.verdict.value = "rejected"

        engine = RecursiveEvolutionEngine(quality_gate=gate, config=EvolutionConfig(dry_run=True))
        engine.evaluate_candidate_with_quality_gate("test", "c1", 55.0)

        gate.evaluate_c2_to_c3.assert_not_called()
