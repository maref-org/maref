from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    CycleSpec,
    EvolutionMetrics,
    EvolutionResult,
)


class TestAcceptanceCriteria:
    def test_defaults(self) -> None:
        ac = AcceptanceCriteria()
        assert ac.c1_fnr_max == 0.15
        assert ac.c1_fpr_max == 0.10
        assert ac.c2_weight_std_max == 0.3

    def test_to_dict(self) -> None:
        ac = AcceptanceCriteria()
        d = ac.to_dict()
        assert d["c1_fnr_max"] == 0.15
        assert d["c2_fnr_must_not_worsen"] is True
        assert d["c3_oscillation_max"] == 0


class TestEvolutionMetrics:
    def test_empty_metrics(self) -> None:
        em = EvolutionMetrics()
        assert em.fnr_series == []
        assert em.fpr_series == []

    def test_snapshot_empty(self) -> None:
        em = EvolutionMetrics()
        snap = em.snapshot(round_num=5)
        assert snap["round"] == 5
        assert snap["fnr"] is None

    def test_snapshot_with_data(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.1)
        em.fpr_series.append(0.05)
        em.entropy_series.append(2)
        em.transition_count_series.append(8)
        snap = em.snapshot(round_num=1)
        assert snap["fnr"] == 0.1
        assert snap["fpr"] == 0.05
        assert snap["entropy"] == 2
        assert snap["transition_count"] == 8

    def test_compute_convergence_insufficient_data(self) -> None:
        em = EvolutionMetrics()
        for _ in range(10):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        conv = em.compute_convergence(window=20)
        assert conv["fnr_std"] == -1.0
        assert conv["converged"] is False

    def test_compute_convergence_sufficient_data(self) -> None:
        em = EvolutionMetrics()
        for _ in range(30):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        conv = em.compute_convergence(window=20)
        assert conv["fnr_std"] >= 0
        assert conv["fpr_std"] >= 0

    def test_assess_acceptance_c1(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.1)
        em.fpr_series.append(0.05)
        em.halt_reasons.append("normal")
        ac = AcceptanceCriteria(c1_fnr_max=0.15, c1_fpr_max=0.10)
        result = em.assess_acceptance(ac, "c1")
        assert result["fnr_below_max"] is True
        assert result["fpr_below_max"] is True
        assert result["no_breaker_trip"] is True
        assert result["halt_only_normal"] is True

    def test_assess_acceptance_c1_fails(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.2)
        em.fpr_series.append(0.05)
        ac = AcceptanceCriteria(c1_fnr_max=0.15, c1_fpr_max=0.10)
        result = em.assess_acceptance(ac, "c1")
        assert result["fnr_below_max"] is False

    def test_assess_acceptance_c2(self) -> None:
        em = EvolutionMetrics()
        for _ in range(25):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        em.policy_weights_series.append({"w1": 0.1, "w2": 0.2})
        em.policy_weights_series.append({"w1": 0.11, "w2": 0.21})
        em.learning_rate_series = [0.02] * 24 + [0.004]
        ac = AcceptanceCriteria(c2_fnr_must_not_worsen=True, c2_fpr_budget_pp=0.05, c2_weight_std_max=0.3, c2_lr_convergence_target=0.005)
        result = em.assess_acceptance(ac, "c2")
        assert "weights_stable" in result
        assert "lr_converged" in result
        assert result["lr_converged"] is True

    def test_assess_acceptance_c3(self) -> None:
        em = EvolutionMetrics()
        for _ in range(30):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        em.halt_reasons = ["normal"] * 10
        ac = AcceptanceCriteria(c3_fnr_std_max=0.05, c3_fpr_std_max=0.03, c3_oscillation_max=0, c3_halt_anomaly_max=0)
        result = em.assess_acceptance(ac, "c3")
        assert "fnr_converged" in result
        assert "fpr_converged" in result
        assert result["no_anomalous_halt"] is True

    def test_weights_std_empty(self) -> None:
        em = EvolutionMetrics()
        assert em._weights_std() == float("inf")

    def test_weights_std_single(self) -> None:
        em = EvolutionMetrics()
        em.policy_weights_series.append({"w": 0.5})
        assert em._weights_std() == 0.0

    def test_to_dict(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.1)
        d = em.to_dict()
        assert d["fnr_series"] == [0.1]
        assert "fpr_series" in d
        assert "halt_reasons" in d

    def test_save(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.1)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            p = Path(f.name)
        try:
            em.save(p)
            with open(p) as f2:
                data = json.load(f2)
            assert data["fnr_series"] == [0.1]
        finally:
            p.unlink()

    def test_is_converged_insufficient(self) -> None:
        assert EvolutionMetrics._is_converged([0.1], 0.05) is False

    def test_is_converged_true(self) -> None:
        assert EvolutionMetrics._is_converged([0.1, 0.11, 0.09], 0.05) is True

    def test_is_converged_false(self) -> None:
        assert EvolutionMetrics._is_converged([0.1, 0.5, 0.9], 0.05) is False

    def test_assess_acceptance_c1_empty_fnr(self) -> None:
        em = EvolutionMetrics()
        ac = AcceptanceCriteria()
        result = em.assess_acceptance(ac, "c1")
        assert result["fnr_below_max"] is False
        assert result["fpr_below_max"] is False

    def test_assess_acceptance_c2_empty_weights(self) -> None:
        em = EvolutionMetrics()
        ac = AcceptanceCriteria()
        result = em.assess_acceptance(ac, "c2")
        assert result["weights_stable"] is False

    def test_assess_acceptance_c2_lr_not_converged(self) -> None:
        em = EvolutionMetrics()
        for _ in range(5):
            em.fnr_series.append(0.1)
        em.policy_weights_series.append({"w": 0.5})
        em.learning_rate_series = [0.02]
        ac = AcceptanceCriteria(c2_lr_convergence_target=0.001)
        result = em.assess_acceptance(ac, "c2")
        assert result["lr_converged"] is False

    def test_assess_acceptance_c3_no_oscillation(self) -> None:
        em = EvolutionMetrics()
        for _ in range(5):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        em.oscillation_events = [{"event": "test"}]
        ac = AcceptanceCriteria(c3_oscillation_max=0)
        result = em.assess_acceptance(ac, "c3")
        assert result["no_oscillation"] is False

    def test_assess_acceptance_c3_anomalous_halt(self) -> None:
        em = EvolutionMetrics()
        for _ in range(5):
            em.fnr_series.append(0.1)
            em.fpr_series.append(0.05)
        em.halt_reasons = ["force_halt"]
        ac = AcceptanceCriteria(c3_halt_anomaly_max=0)
        result = em.assess_acceptance(ac, "c3")
        assert result["no_anomalous_halt"] is False


class TestCycleSpec:
    def test_defaults(self) -> None:
        cs = CycleSpec(name="test", rounds=50, description="test cycle")
        assert cs.meta_learning_enabled is False
        assert cs.meta_learning_interval == 5


class TestCycleResult:
    def test_minimal(self) -> None:
        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="test", rounds_completed=10, rounds_total=50, metrics=em, acceptance={}, passed=True)
        assert cr.passed is True
        assert "PASSED" in cr.summary()

    def test_summary_failed(self) -> None:
        em = EvolutionMetrics()
        em.fnr_series.append(0.1)
        em.fpr_series.append(0.05)
        cr = CycleResult(cycle_id="c1", name="test", rounds_completed=5, rounds_total=10, metrics=em, acceptance={"fnr": False}, passed=False)
        assert "FAILED" in cr.summary()

    def test_summary_no_metrics(self) -> None:
        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="empty", rounds_completed=0, rounds_total=0, metrics=em, acceptance={}, passed=True)
        assert "N/A" in cr.summary()


class TestEvolutionResult:
    def test_summary(self) -> None:
        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="test", rounds_completed=10, rounds_total=50, metrics=em, acceptance={}, passed=True)
        result = EvolutionResult(cycles=[cr], stop_reason="normal_completion", total_rounds=10, all_passed=True)
        s = result.summary()
        assert "PASSED" in s
        assert "normal_completion" in s

    def test_summary_failed_overall(self) -> None:
        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="test", rounds_completed=10, rounds_total=50, metrics=em, acceptance={}, passed=False)
        result = EvolutionResult(cycles=[cr], stop_reason="normal_completion", total_rounds=10, all_passed=False)
        s = result.summary()
        assert "FAILED" in s
