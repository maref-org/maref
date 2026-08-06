from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.integration.percv.mas_ts_bridge import MasTSBridge
from maref.integration.percv.mas_ts_integration import enrich_experiment_result, evaluate_with_masts
from maref.integration.percv.multi_target_ratchet import ExperimentResult


class TestMastsIntegration:
    def test_evaluate_with_masts_default(self) -> None:
        def evaluate_fn():
            return {"consistency_score": 0.85}

        mas_ts = MasTSBridge(mas_ts_root="/nonexistent")
        result = evaluate_with_masts(evaluate_fn, mas_ts)
        assert result["percv_score"] == 0.85
        assert result["mas_ts_score"] > 0
        assert result["combined_score"] > 0

    def test_evaluate_with_masts_custom_scores(self) -> None:
        def evaluate_fn():
            return {"score": 0.90}

        mock_bridge = MagicMock()
        mock_bridge.run_fast_screen.return_value = {
            "overall_score": 88.0, "level": "L0", "details": {},
        }
        result = evaluate_with_masts(evaluate_fn, mock_bridge)
        assert result["percv_score"] == 0.90
        assert result["mas_ts_score"] == 88.0
        assert result["combined_score"] == pytest.approx((0.90 + 0.88) / 2)

    def test_enrich_experiment_result(self) -> None:
        result = ExperimentResult(
            commit="abc", metric_value=0.8, previous_best=0.7,
            delta=0.1, status="keep", description="test", memory_mb=100.0,
        )
        eval_result = {"mas_ts_score": 90.0, "mas_ts_level": "L0"}
        enriched = enrich_experiment_result(result, eval_result)
        assert enriched.mas_ts_score == 90.0
        assert enriched.mas_ts_level == "L0"

    def test_evaluate_with_string_scores(self) -> None:
        def evaluate_fn():
            return {"consistency_score": "0.75"}

        mock_bridge = MagicMock()
        mock_bridge.run_fast_screen.return_value = {
            "overall_score": "82.0", "level": "L0", "details": {},
        }
        result = evaluate_with_masts(evaluate_fn, mock_bridge)
        assert result["percv_score"] == 0.75
        assert result["mas_ts_score"] == 82.0
