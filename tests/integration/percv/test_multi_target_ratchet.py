from __future__ import annotations

import pytest

from maref.integration.percv.multi_target_ratchet import (
    ExperimentResult,
    ImprovementTarget,
    MultiTargetConfig,
    MultiTargetRatchet,
)


class TestMultiTargetRatchet:
    def test_init_defaults(self) -> None:
        mtr = MultiTargetRatchet()
        assert len(mtr.targets) == 3
        assert mtr.config.rotation_mode == "round_robin"

    def test_next_target_round_robin(self) -> None:
        mtr = MultiTargetRatchet()
        first = mtr.next_target()
        second = mtr.next_target()
        third = mtr.next_target()
        fourth = mtr.next_target()
        assert first == ImprovementTarget.PROMPT_DISTILL
        assert second == ImprovementTarget.PROMPT_PROJECT
        assert third == ImprovementTarget.EVALUATION_WEIGHTS
        assert fourth == ImprovementTarget.PROMPT_DISTILL

    def test_next_target_custom_order(self) -> None:
        targets = [ImprovementTarget.PROMPT_PROJECT, ImprovementTarget.GOVERNANCE_RULES]
        mtr = MultiTargetRatchet(targets=targets)
        assert mtr.next_target() == ImprovementTarget.PROMPT_PROJECT
        assert mtr.next_target() == ImprovementTarget.GOVERNANCE_RULES
        assert mtr.next_target() == ImprovementTarget.PROMPT_PROJECT

    def test_record_result_updates_history(self) -> None:
        mtr = MultiTargetRatchet()
        result = ExperimentResult(
            commit="abc123", metric_value=0.85, previous_best=0.80,
            delta=0.05, status="keep", description="improved", memory_mb=128.0,
        )
        mtr.record_result(ImprovementTarget.PROMPT_DISTILL, result)
        assert len(mtr.history[ImprovementTarget.PROMPT_DISTILL.value]) == 1

    def test_should_escalate_false_with_few_records(self) -> None:
        mtr = MultiTargetRatchet()
        assert mtr.should_escalate(ImprovementTarget.PROMPT_DISTILL) is False

    def test_should_escalate_true(self) -> None:
        mtr = MultiTargetRatchet()
        target = ImprovementTarget.PROMPT_DISTILL
        for i in range(5):
            result = ExperimentResult(
                commit=f"abc{i}", metric_value=0.5, previous_best=0.5,
                delta=0.0, status="discard", description="", memory_mb=100.0,
            )
            mtr.record_result(target, result)
        assert mtr.should_escalate(target) is True

    def test_get_target_summary_empty(self) -> None:
        mtr = MultiTargetRatchet()
        summary = mtr.get_target_summary()
        for key in summary:
            assert summary[key]["rounds"] == 0

    def test_get_target_summary_with_data(self) -> None:
        mtr = MultiTargetRatchet()
        for i in range(3):
            r = ExperimentResult(
                commit=f"abc{i}", metric_value=0.8 + i * 0.05, previous_best=0.8,
                delta=0.05, status="keep", description="", memory_mb=100.0,
                mas_ts_score=80.0 + i,
            )
            mtr.record_result(ImprovementTarget.PROMPT_DISTILL, r)
        summary = mtr.get_target_summary()
        pd = summary[ImprovementTarget.PROMPT_DISTILL.value]
        assert pd["rounds"] == 3
        assert pd["best_score"] > 0.8

    def test_weighted_select_favors_lower_weight_via_heuristic(self) -> None:
        targets = [ImprovementTarget.PROMPT_DISTILL, ImprovementTarget.PROMPT_PROJECT]
        mtr = MultiTargetRatchet(targets=targets, config=MultiTargetConfig(rotation_mode="weighted"))
        for _ in range(5):
            r = ExperimentResult(
                commit="x", metric_value=0.5, previous_best=0.5,
                delta=0.0, status="discard", description="", memory_mb=100.0,
            )
            mtr.record_result(ImprovementTarget.PROMPT_DISTILL, r)
        for _ in range(5):
            r = ExperimentResult(
                commit="y", metric_value=0.9, previous_best=0.9,
                delta=0.0, status="keep", description="", memory_mb=100.0,
            )
            mtr.record_result(ImprovementTarget.PROMPT_PROJECT, r)
        selections = [mtr.next_target() for _ in range(20)]
        prompt_project_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_PROJECT)
        prompt_distill_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_DISTILL)
        assert prompt_project_count > prompt_distill_count, (
            f"Expected PROMPT_PROJECT (0 keep discards) > PROMPT_DISTILL "
            f"(all discards), got {prompt_project_count} vs {prompt_distill_count}"
        )

    def test_weighted_select_via_registry(self) -> None:
        from unittest.mock import MagicMock
        targets = [ImprovementTarget.PROMPT_DISTILL, ImprovementTarget.PROMPT_PROJECT]
        mtr = MultiTargetRatchet(targets=targets, config=MultiTargetConfig(rotation_mode="weighted"))
        registry = MagicMock()
        registry.get_all_weights.return_value = {
            "correctness": {"current_weight": 0.9},
            "testing": {"current_weight": 0.3},
        }
        registry.DIMENSION_TARGET_MAP = {
            "correctness": "prompts/distill_v1.yaml",
            "testing": "prompts/project_v1.yaml",
        }
        mtr.set_weight_registry(registry)
        selections = [mtr.next_target() for _ in range(30)]
        project_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_PROJECT)
        distill_count = sum(1 for s in selections if s == ImprovementTarget.PROMPT_DISTILL)
        assert project_count > distill_count, (
            f"Expected PROMPT_PROJECT (weight 0.3) selected more than "
            f"PROMPT_DISTILL (weight 0.9), got {project_count} vs {distill_count}"
        )


class TestExperimentResult:
    def test_default_fields(self) -> None:
        r = ExperimentResult(
            commit="abc", metric_value=0.8, previous_best=0.7,
            delta=0.1, status="keep", description="test", memory_mb=100.0,
        )
        assert r.mas_ts_score == 0.0
        assert r.mas_ts_level == ""
        assert r.target_dimension == ""
        assert r.dimension_scores is None

    def test_masts_fields(self) -> None:
        r = ExperimentResult(
            commit="abc", metric_value=0.8, previous_best=0.7,
            delta=0.1, status="keep", description="test", memory_mb=100.0,
            mas_ts_score=85.0, mas_ts_level="L0",
        )
        assert r.mas_ts_score == 85.0
        assert r.mas_ts_level == "L0"
