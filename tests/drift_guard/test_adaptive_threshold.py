"""Smoke tests for drift_guard.adaptive_threshold."""
from __future__ import annotations

import pytest

from drift_guard.adaptive_threshold import (
    AdaptiveThresholdConfig,
    AdaptiveThresholdManager,
    ThresholdPerformance,
)


class TestThresholdPerformance:
    def test_init_default(self) -> None:
        perf = ThresholdPerformance()
        assert perf.true_positives == 0
        assert perf.precision == 0.0
        assert perf.recall == 0.0
        assert perf.f1_score == 0.0

    def test_precision(self) -> None:
        perf = ThresholdPerformance(true_positives=8, false_positives=2)
        assert perf.precision == 0.8
        assert perf.recall == 1.0  # no FNs

    def test_recall(self) -> None:
        perf = ThresholdPerformance(true_positives=7, false_negatives=3)
        assert perf.recall == 0.7

    def test_f1_score(self) -> None:
        perf = ThresholdPerformance(true_positives=6, false_positives=2, false_negatives=2)
        assert perf.precision == 0.75
        assert perf.recall == 0.75
        assert perf.f1_score == 0.75

    def test_false_positive_rate(self) -> None:
        perf = ThresholdPerformance(false_positives=2, true_negatives=8)
        assert perf.false_positive_rate == 0.2

    def test_false_negative_rate(self) -> None:
        perf = ThresholdPerformance(false_negatives=2, true_positives=8)
        assert perf.false_negative_rate == 0.2

    def test_zero_division_precision(self) -> None:
        perf = ThresholdPerformance()
        assert perf.precision == 0.0

    def test_zero_division_f1(self) -> None:
        perf = ThresholdPerformance()
        assert perf.f1_score == 0.0


class TestAdaptiveThresholdConfig:
    def test_init_default(self) -> None:
        config = AdaptiveThresholdConfig()
        assert config.learning_rate == 0.1
        assert config.target_fpr == 0.05
        assert config.target_fnr == 0.02
        assert config.enabled is True

    def test_init_custom(self) -> None:
        config = AdaptiveThresholdConfig(
            learning_rate=0.2, target_fpr=0.1, target_fnr=0.05,
            min_kl_warning=0.02, enabled=False,
        )
        assert config.learning_rate == 0.2
        assert config.enabled is False

    def test_to_dict(self) -> None:
        config = AdaptiveThresholdConfig()
        d = config.to_dict()
        assert d["learning_rate"] == 0.1
        assert d["enabled"] is True


class TestAdaptiveThresholdManager:
    def test_init_default(self) -> None:
        manager = AdaptiveThresholdManager()
        assert manager is not None
        assert manager._config is not None

    def test_init_with_config(self) -> None:
        config = AdaptiveThresholdConfig(learning_rate=0.5)
        manager = AdaptiveThresholdManager(config=config)
        assert manager._config.learning_rate == 0.5

    def test_record_outcome(self) -> None:
        manager = AdaptiveThresholdManager()
        manager.record_outcome(threshold_used=0.1, predicted_drift=True, actual_drift=True)
        assert manager._performance.true_positives == 1
        assert len(manager._history) == 1

    def test_record_outcome_false_positive(self) -> None:
        manager = AdaptiveThresholdManager()
        manager.record_outcome(threshold_used=0.1, predicted_drift=True, actual_drift=False)
        assert manager._performance.false_positives == 1

    def test_record_outcome_false_negative(self) -> None:
        manager = AdaptiveThresholdManager()
        manager.record_outcome(threshold_used=0.1, predicted_drift=False, actual_drift=True)
        assert manager._performance.false_negatives == 1

    def test_should_adjust_not_enough(self) -> None:
        manager = AdaptiveThresholdManager()
        assert manager.should_adjust() is False

    def test_should_adjust_enough(self) -> None:
        manager = AdaptiveThresholdManager()
        config = AdaptiveThresholdConfig(evaluation_window=3)
        manager2 = AdaptiveThresholdManager(config=config)
        for i in range(3):
            manager2.record_outcome(0.1, True, True)
        assert manager2.should_adjust() is True

    def test_compute_adjustment_no_history(self) -> None:
        manager = AdaptiveThresholdManager()
        adj = manager.compute_adjustment(0.1)
        assert adj == 0.0

    def test_adjust_threshold_no_history(self) -> None:
        manager = AdaptiveThresholdManager()
        result = manager.adjust_threshold(0.1, "warning")
        assert result == 0.1

    def test_get_stats(self) -> None:
        manager = AdaptiveThresholdManager()
        stats = manager.get_stats()
        assert "config" in stats
        assert "performance" in stats
        assert stats["history_size"] == 0
        assert stats["ready_to_adjust"] is False

    def test_reset(self) -> None:
        manager = AdaptiveThresholdManager()
        manager.record_outcome(0.1, True, True)
        assert manager._performance.true_positives == 1
        manager.reset()
        assert manager._performance.true_positives == 0
