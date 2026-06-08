"""Tests for CognitiveProbe — cognitive-augmented governance observation."""

from __future__ import annotations

import math

from maref.observation.cognitive_probe import CognitiveDimension, CognitiveProbe
from maref.observation.probes import ProbeSeverity
from maref.observation.registry import ProbeRegistry


class TestCognitiveProbeDimensions:
    def test_composite_risk_critical(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.9,
            value_alignment=0.85,
            reasoning_depth=0.2,
            emotional_volatility=0.8,
            knowledge_gap_rate=0.75,
            rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_composite_risk_warning(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.6,
            value_alignment=0.55,
            reasoning_depth=0.4,
            emotional_volatility=0.6,
            knowledge_gap_rate=0.5,
            rejection_pattern=0.45,
            metacognitive_awareness=0.4,
        )
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.WARNING

    def test_composite_risk_normal(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.2,
            value_alignment=0.1,
            reasoning_depth=0.9,
            emotional_volatility=0.1,
            knowledge_gap_rate=0.0,
            rejection_pattern=0.0,
            metacognitive_awareness=0.95,
        )
        assert len(readings) == 0

    def test_missing_dimensions_default_to_zero(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read()
        assert len(readings) == 0

    def test_partial_dimensions_no_alert(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(decision_consistency=0.3, value_alignment=0.2)
        assert len(readings) == 0

    def test_reading_contains_dimension_context(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.9,
            value_alignment=0.85,
            reasoning_depth=0.2,
            emotional_volatility=0.8,
            knowledge_gap_rate=0.75,
            rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        assert len(readings) == 1
        ctx = readings[0].context
        assert "composite_risk" in ctx
        assert "dimensions" in ctx
        dims = ctx["dimensions"]
        assert isinstance(dims, dict)
        assert dims["decision_consistency"] == 0.9
        assert dims["knowledge_gap_rate"] == 0.75

    def test_reading_score_is_composite(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.9,
            value_alignment=0.85,
            reasoning_depth=0.2,
            emotional_volatility=0.8,
            knowledge_gap_rate=0.75,
            rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        assert len(readings) == 1
        assert 0.0 <= readings[0].value <= 1.0


class TestCognitiveProbeHistoricalTracking:
    def test_readings_accumulate(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        probe.read(
            decision_consistency=0.9, value_alignment=0.85,
            reasoning_depth=0.2, emotional_volatility=0.8,
            knowledge_gap_rate=0.75, rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        probe.read(
            decision_consistency=0.1, value_alignment=0.1,
            reasoning_depth=0.9, emotional_volatility=0.1,
            knowledge_gap_rate=0.1, rejection_pattern=0.1,
            metacognitive_awareness=0.9,
        )
        probe.read(
            decision_consistency=0.9, value_alignment=0.85,
            reasoning_depth=0.2, emotional_volatility=0.8,
            knowledge_gap_rate=0.75, rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        assert probe.reading_count == 2  # only triggered readings accumulate

    def test_trend_detected_rising(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        probe.read(decision_consistency=0.3, value_alignment=0.3)
        probe.read(decision_consistency=0.5, value_alignment=0.5)
        probe.read(decision_consistency=0.7, value_alignment=0.7)
        trend = probe.get_trend(window=3)
        assert trend["direction"] == "rising"

    def test_trend_detected_falling(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        probe.read(decision_consistency=0.7, value_alignment=0.7)
        probe.read(decision_consistency=0.5, value_alignment=0.5)
        probe.read(decision_consistency=0.3, value_alignment=0.3)
        trend = probe.get_trend(window=3)
        assert trend["direction"] == "falling"

    def test_trend_stable(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        probe.read(decision_consistency=0.5, value_alignment=0.5)
        probe.read(decision_consistency=0.5, value_alignment=0.5)
        trend = probe.get_trend(window=3)
        assert trend["direction"] == "stable"

    def test_trend_window_limit(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        probe.read(decision_consistency=0.9)
        probe.read(decision_consistency=0.9)
        probe.read(decision_consistency=0.9)
        probe.read(decision_consistency=0.9)
        trend = probe.get_trend(window=2)
        assert len(trend["scores"]) <= 2


class TestCognitiveDimensionEnum:
    def test_dimension_count(self) -> None:
        assert len(CognitiveDimension) == 7

    def test_dimension_names(self) -> None:
        names = {d.value for d in CognitiveDimension}
        assert "decision_consistency" in names
        assert "value_alignment" in names
        assert "reasoning_depth" in names
        assert "emotional_volatility" in names
        assert "knowledge_gap_rate" in names
        assert "rejection_pattern" in names
        assert "metacognitive_awareness" in names


class TestCognitiveReading:
    def test_readings_have_probe_name(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency=0.9)
        assert readings[0].probe_name == "cognitive"

    def test_inverse_dimension_inverts(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(
            decision_consistency=0.9,
            reasoning_depth=0.9,
            value_alignment=0.9,
            emotional_volatility=0.9,
            knowledge_gap_rate=0.9,
            rejection_pattern=0.9,
            metacognitive_awareness=0.9,
        )
        assert len(readings) == 1
        ctx = readings[0].context["dimensions"]
        # Inverse dimensions: reasoning_depth and metacognitive_awareness
        # High raw values → contribute LOW to risk
        assert ctx["reasoning_depth"] == 0.1
        assert ctx["metacognitive_awareness"] == 0.1

    def test_to_dict_includes_composite(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency=0.9)
        d = readings[0].to_dict()
        assert "composite_risk" in d["context"]
        assert "dimensions" in d["context"]


class TestCognitiveProbeEdgeCases:
    def test_nan_dimension_skipped(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(
            decision_consistency=float("nan"),
            value_alignment=0.9,
        )
        # NaN skipped, only value_alignment=0.9 → composite=0.9 → CRITICAL
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_nan_only_skipped_all(self) -> None:
        probe = CognitiveProbe()
        readings = probe.read(
            decision_consistency=float("nan"),
            value_alignment=float("nan"),
            reasoning_depth=float("nan"),
            emotional_volatility=float("nan"),
            knowledge_gap_rate=float("nan"),
            rejection_pattern=float("nan"),
            metacognitive_awareness=float("nan"),
        )
        assert len(readings) == 0

    def test_nan_does_not_pollute_trend(self) -> None:
        probe = CognitiveProbe()
        probe.read(decision_consistency=float("nan"))
        probe.read(decision_consistency=0.3, value_alignment=0.3)
        trend = probe.get_trend(window=5)
        assert not any(math.isnan(s) for s in trend["scores"])

    def test_infinity_clamped_to_one(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency=float("inf"))
        assert len(readings) == 1
        assert readings[0].value >= 0.0
        # infinity → clamped to 1.0
        ctx = readings[0].context["dimensions"]
        assert ctx["decision_consistency"] == 1.0

    def test_negative_clamped_to_zero(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency=-1.0)
        assert len(readings) == 0  # clamped to 0.0 < shadow=0.5

    def test_above_one_clamped(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency=1.5)
        assert len(readings) == 1  # clamped to 1.0 > 0.8
        ctx = readings[0].context["dimensions"]
        assert ctx["decision_consistency"] == 1.0

    def test_exact_shadow_boundary_triggers_warning(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(decision_consistency=0.5)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.WARNING
        assert readings[0].value == 0.5

    def test_exact_primary_boundary_triggers_critical(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5)
        readings = probe.read(decision_consistency=0.8)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL
        assert readings[0].value == 0.8

    def test_non_numeric_type_skipped(self) -> None:
        probe = CognitiveProbe(primary_threshold=0.8)
        readings = probe.read(decision_consistency="not_a_number", value_alignment=0.9)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_get_trend_filters_nan_scores(self) -> None:
        probe = CognitiveProbe()
        probe._composite_scores.extend([float("nan"), 0.3, float("nan"), 0.5, float("nan")])
        trend = probe.get_trend(window=5)
        assert trend["direction"] == "rising"
        assert len(trend["scores"]) == 2
        assert trend["scores"] == [0.3, 0.5]


class TestCognitiveProbeIntegration:
    def test_registers_in_registry(self) -> None:
        registry = ProbeRegistry()
        registry.register(CognitiveProbe())
        assert "cognitive" in registry.list_probes()

    def test_reads_via_registry(self) -> None:
        registry = ProbeRegistry()
        registry.register(CognitiveProbe(primary_threshold=0.8, shadow_threshold=0.5))
        readings = registry.read_all(
            decision_consistency=0.9,
            value_alignment=0.85,
            reasoning_depth=0.2,
            emotional_volatility=0.8,
            knowledge_gap_rate=0.75,
            rejection_pattern=0.7,
            metacognitive_awareness=0.1,
        )
        assert len(readings) >= 1
        cognitive_readings = [r for r in readings if r.probe_name == "cognitive"]
        assert len(cognitive_readings) == 1

    def test_coexists_with_entropy_probe(self) -> None:
        from maref.observation.probes import EntropyProbe

        registry = ProbeRegistry()
        registry.register(CognitiveProbe(primary_threshold=0.8))
        registry.register(EntropyProbe(primary_threshold=4.0))
        readings = registry.read_all(
            decision_consistency=0.9,
            entropy=4,
        )
        names = {r.probe_name for r in readings}
        assert "cognitive" in names
        assert "entropy" in names
