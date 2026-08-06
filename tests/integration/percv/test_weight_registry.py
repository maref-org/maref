from __future__ import annotations

import pytest

from maref.integration.percv.weight_registry import SimpleWeightRegistry


class TestSimpleWeightRegistry:
    def test_init_has_default_weights(self) -> None:
        r = SimpleWeightRegistry()
        weights = r.get_all_weights()
        assert "correctness" in weights
        assert "testing" in weights
        assert weights["correctness"]["current_weight"] == 0.5

    def test_set_weight(self) -> None:
        r = SimpleWeightRegistry()
        r.set("correctness", 0.8)
        assert r.get_weight("correctness") == 0.8

    def test_set_weight_clamps(self) -> None:
        r = SimpleWeightRegistry()
        r.set("correctness", 1.5)
        assert r.get_weight("correctness") == 1.0
        r.set("correctness", -0.5)
        assert r.get_weight("correctness") == 0.0

    def test_set_new_dimension(self) -> None:
        r = SimpleWeightRegistry()
        r.set("novelty", 0.7)
        assert r.get_weight("novelty") == 0.7

    def test_record_hit_updates_weight(self) -> None:
        r = SimpleWeightRegistry()
        r.record_hit("correctness", hit=True)
        w = r.get_weight("correctness")
        assert w > 0.5

    def test_record_miss_lowers_weight(self) -> None:
        r = SimpleWeightRegistry()
        r.record_hit("correctness", hit=True)
        w_after_hit = r.get_weight("correctness")
        r.record_hit("correctness", hit=False)
        w_after_miss = r.get_weight("correctness")
        assert w_after_miss < w_after_hit

    def test_record_hit_new_dimension(self) -> None:
        r = SimpleWeightRegistry()
        r.record_hit("novelty", hit=True)
        assert r.get_weight("novelty") > 0.5

    def test_get_all_weights_structure(self) -> None:
        r = SimpleWeightRegistry()
        weights = r.get_all_weights()
        for name, data in weights.items():
            assert "current_weight" in data
            assert "hit_count" in data
            assert "sample_count" in data
            assert "trend" in data

    def test_trend_stable_with_single_sample(self) -> None:
        r = SimpleWeightRegistry()
        trend = r._compute_trend(r.weights["correctness"])
        assert trend == "stable"

    def test_reset_weights(self) -> None:
        r = SimpleWeightRegistry()
        r.set("correctness", 0.9)
        r.reset_weights()
        assert r.get_weight("correctness") == 0.5

    def test_get_target_for_dimension(self) -> None:
        r = SimpleWeightRegistry()
        assert r.get_target_for_dimension("correctness") == "prompts/distill_v1.yaml"
        assert r.get_target_for_dimension("unknown") is None
