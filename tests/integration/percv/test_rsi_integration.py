from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.cross_dimensional_analyzer import CrossDimensionalAnalyzer
from maref.integration.percv.mas_ts_bridge import MasTSBridge
from maref.integration.percv.mas_ts_integration import evaluate_with_masts
from maref.integration.percv.meta_ratchet import MetaRatchet, ProtocolChange
from maref.integration.percv.multi_target_ratchet import (
    ExperimentResult,
    ImprovementTarget,
    MultiTargetConfig,
    MultiTargetRatchet,
)
from maref.integration.percv.ratchet_bridge import RatchetBridge
from maref.integration.percv.weight_registry import SimpleWeightRegistry


class TestRSIIntegration:
    def test_full_multi_target_ratchet_flow(self) -> None:
        mtr = MultiTargetRatchet()
        target = mtr.next_target()
        assert target in mtr.targets

        result = ExperimentResult(
            commit="test123", metric_value=0.85, previous_best=0.80,
            delta=0.05, status="keep", description="improved", memory_mb=128.0,
            mas_ts_score=87.0, mas_ts_level="L0",
        )
        mtr.record_result(target, result)
        assert len(mtr.history[target.value]) == 1

    def test_ratchet_bridge_with_masts(self) -> None:
        mas_ts = MasTSBridge(mas_ts_root="/nonexistent")
        bridge = RatchetBridge(mas_ts_bridge=mas_ts)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "score: 0.85"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            with patch.object(bridge, "_get_git_diff", return_value=""):
                iterations = bridge.run_improvement_cycle(budget=1)

        assert len(iterations) == 1
        assert iterations[0].score == 0.85

    def test_weight_registry_feeds_ratchet(self) -> None:
        registry = SimpleWeightRegistry()
        registry.record_hit("correctness", hit=True)
        weights = registry.get_all_weights()
        assert weights["correctness"]["current_weight"] > 0.5

        target_file = registry.get_target_for_dimension("correctness")
        assert target_file == "prompts/distill_v1.yaml"

    def test_meta_ratchet_triggered_by_discards(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = [
            MagicMock(
                iteration=i, score=0.5, approved=False, best_score=0.5,
                best_iteration=None, duration_s=1.0, status="discard",
                target=ImprovementTarget.PROMPT_DISTILL.value,
                mas_ts_score=0, mas_ts_level="",
            )
            for i in range(5)
        ]
        meta = MetaRatchet(ratchet_bridge=bridge)
        triggers = meta.check_triggers(ImprovementTarget.PROMPT_DISTILL)
        assert "consecutive_discards" in triggers

        diag = meta.diagnose_stagnation(ImprovementTarget.PROMPT_DISTILL)
        assert diag.severity == "high"

        change = meta.propose_protocol_change(diag)
        assert change is not None

    def test_cross_dimensional_analyzer_works_with_experiment_results(self) -> None:
        history = []
        for i in range(5):
            history.append(ExperimentResult(
                commit=f"abc{i}", metric_value=0.7 + i * 0.05,
                previous_best=0.7, delta=i * 0.05, status="keep",
                description="", memory_mb=100.0,
                dimension_scores={
                    "correctness": 0.7 + i * 0.05,
                    "testing": 0.6 + i * 0.02,
                    "code_quality": 0.5 + i * 0.01,
                },
            ))
        cda = CrossDimensionalAnalyzer(history)
        effects = cda.detect_cross_effects(window=5)
        assert isinstance(effects, list)

    def test_redline_config_loaded_by_bridge(self) -> None:
        bridge = RatchetBridge()
        assert "rsi_immutables" in bridge._redlines

    def test_evaluate_with_masts_fallback(self) -> None:
        def evaluate_fn():
            return {"consistency_score": 0.80}

        mas_ts = MasTSBridge(mas_ts_root="/nonexistent")
        result = evaluate_with_masts(evaluate_fn, mas_ts)
        assert result["percv_score"] == 0.80
        assert result["mas_ts_score"] == 75.0
        assert result["combined_score"] > 0

    def test_meta_ratchet_sandbox_test_with_protocol_change(self) -> None:
        meta = MetaRatchet()
        change = ProtocolChange(
            config_key="max_consecutive_discards",
            old_value=5, new_value=4, rationale="test reduction",
        )
        result = meta.sandbox_test(change, n_rounds=10)
        assert isinstance(result.improvement, float)
        assert isinstance(result.adopted, bool)

    def test_redline_rl004_discards_on_low_masts_during_cycle(self) -> None:
        mas_ts_mock = MagicMock()
        mas_ts_mock.run_fast_screen.return_value = {"overall_score": 50.0, "level": "L0"}
        bridge = RatchetBridge(vault_path=Path("/tmp"), mas_ts_bridge=mas_ts_mock)
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "score: 0.90"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            with patch.object(bridge, "_get_git_diff", return_value=""):
                iterations = bridge.run_improvement_cycle(budget=3)
        assert len(iterations) == 3
        assert iterations[0].mas_ts_score == 50.0
        assert iterations[0].status == "discard"

    def test_weight_registry_drives_multi_target_selection(self) -> None:
        targets = [ImprovementTarget.PROMPT_DISTILL, ImprovementTarget.PROMPT_PROJECT]
        mtr = MultiTargetRatchet(targets=targets, config=MultiTargetConfig(rotation_mode="weighted"))
        registry = SimpleWeightRegistry()
        registry.set("correctness", 0.9)
        registry.set("testing", 0.3)
        mtr.set_weight_registry(registry)
        selections = [mtr.next_target() for _ in range(50)]
        project_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_PROJECT)
        distill_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_DISTILL)
        assert project_count > distill_count, (
            f"PROMPT_PROJECT (low weight=0.3) should be selected more than "
            f"PROMPT_DISTILL (high weight=0.9): {project_count} vs {distill_count}"
        )

    def test_redline_rl001_halts_on_no_human_gate(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp"))
        result = bridge._enforce_redlines("target", mas_ts_score=0, human_gate=False)
        assert result.get("action") == "HALT"
