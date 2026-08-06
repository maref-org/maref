"""
Tests for cycle acceptance criteria — validates each cycle's pass/fail logic.
"""

from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    EvolutionMetrics,
)


class TestC1BaselineAcceptance:
    def test_all_metrics_in_range_passes(self):
        metrics = EvolutionMetrics()
        for _ in range(50):
            metrics.fnr_series.append(0.08)
            metrics.fpr_series.append(0.04)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["fnr_below_max"] is True
        assert result["fpr_below_max"] is True

    def test_single_fnr_spike_fails(self):
        metrics = EvolutionMetrics()
        for i in range(50):
            fnr = 0.20 if i == 25 else 0.08
            metrics.fnr_series.append(fnr)
            metrics.fpr_series.append(0.04)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["fnr_below_max"] is False

    def test_single_fpr_spike_fails(self):
        metrics = EvolutionMetrics()
        for i in range(50):
            fpr = 0.15 if i == 25 else 0.04
            metrics.fpr_series.append(fpr)
            metrics.fnr_series.append(0.08)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["fpr_below_max"] is False

    def test_no_breaker_events_passes(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series = [0.08] * 10
        metrics.fpr_series = [0.04] * 10
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["no_breaker_trip"] is True


class TestC2OptimizationAcceptance:
    def test_stable_weights_passes(self):
        metrics = EvolutionMetrics()
        for _ in range(20):
            metrics.policy_weights_series.append(
                {
                    "entropy_penalty": -0.1,
                    "stability_bonus": 0.2,
                    "transition_efficiency": 0.05,
                }
            )
            metrics.learning_rate_series.append(0.004)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c2")
        assert result["weights_stable"] is True

    def test_divergent_weights_fails(self):
        metrics = EvolutionMetrics()
        for i in range(20):
            metrics.policy_weights_series.append(
                {
                    "entropy_penalty": -0.1 + 0.1 * i,
                    "stability_bonus": 0.2 + 0.1 * i,
                    "transition_efficiency": 0.05 + 0.05 * i,
                }
            )
        criteria = AcceptanceCriteria(c2_weight_std_max=0.05)
        result = metrics.assess_acceptance(criteria, "c2")
        assert result["weights_stable"] is False

    def test_lr_convergence_passes(self):
        metrics = EvolutionMetrics()
        for _ in range(10):
            metrics.learning_rate_series.append(0.004)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c2")
        assert result["lr_converged"] is True

    def test_lr_not_converged_fails(self):
        metrics = EvolutionMetrics()
        for _ in range(10):
            metrics.learning_rate_series.append(0.01)
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c2")
        assert result["lr_converged"] is False

    def test_empty_series_fails(self):
        metrics = EvolutionMetrics()
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c2")
        assert result["weights_stable"] is False
        assert result["lr_converged"] is False


class TestC3ConvergenceAcceptance:
    def test_tightly_converged_passes(self):
        metrics = EvolutionMetrics()
        for _ in range(25):
            metrics.fnr_series.append(0.05 + 0.0001)
            metrics.fpr_series.append(0.02 + 0.0001)
            metrics.halt_reasons.append("normal_path_completion")
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c3")
        assert result["fnr_converged"] is True
        assert result["fpr_converged"] is True
        assert result["no_anomalous_halt"] is True

    def test_diverged_fnr_fails(self):
        metrics = EvolutionMetrics()
        for i in range(25):
            metrics.fnr_series.append(0.05 + 0.01 * i)
            metrics.fpr_series.append(0.02)
            metrics.halt_reasons.append("normal_path_completion")
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c3")
        assert result["fnr_converged"] is False

    def test_no_oscillation_passes(self):
        metrics = EvolutionMetrics()
        for _ in range(25):
            metrics.fnr_series.append(0.05)
            metrics.fpr_series.append(0.02)
            metrics.halt_reasons.append("normal_completion")
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c3")
        assert result["no_oscillation"] is True

    def test_oscillation_detected_fails(self):
        metrics = EvolutionMetrics()
        for _ in range(25):
            metrics.fnr_series.append(0.05)
            metrics.fpr_series.append(0.02)
            metrics.halt_reasons.append("normal_completion")
        for _ in range(5):
            metrics.oscillation_events.append({"event": "detected"})
        criteria = AcceptanceCriteria(c3_oscillation_max=0)
        result = metrics.assess_acceptance(criteria, "c3")
        assert result["no_oscillation"] is False

    def test_anomalous_halt_detected(self):
        metrics = EvolutionMetrics()
        for _ in range(25):
            metrics.fnr_series.append(0.05)
            metrics.fpr_series.append(0.02)
        for _ in range(3):
            metrics.halt_reasons.append("force_halt_critical")
        criteria = AcceptanceCriteria(c3_halt_anomaly_max=0)
        result = metrics.assess_acceptance(criteria, "c3")
        assert result["no_anomalous_halt"] is False
        assert metrics.fnr_series[-1] == 0.05


class TestConvergenceComputation:
    def test_perfectly_constant_converges(self):
        metrics = EvolutionMetrics()
        for _ in range(25):
            metrics.fnr_series.append(0.05)
            metrics.fpr_series.append(0.02)
        conv = metrics.compute_convergence(window=20)
        assert conv["converged"] is True
        assert conv["fnr_std"] < 0.01

    def test_insufficient_data_not_converged(self):
        metrics = EvolutionMetrics()
        for _ in range(5):
            metrics.fnr_series.append(0.05)
            metrics.fpr_series.append(0.02)
        conv = metrics.compute_convergence(window=20)
        assert conv["converged"] is False

    def test_drift_is_not_converged(self):
        metrics = EvolutionMetrics()
        for i in range(25):
            metrics.fnr_series.append(0.05 + 0.01 * i)
            metrics.fpr_series.append(0.02 + 0.01 * i)
        conv = metrics.compute_convergence(window=20)
        assert conv["converged"] is False
        assert conv["fnr_std"] > 0.05


class TestCycleResultFormatting:
    def test_cycle_result_summary(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series = [0.05, 0.04]
        metrics.fpr_series = [0.02, 0.01]
        result = CycleResult(
            cycle_id="c1",
            name="Baseline",
            rounds_completed=2,
            rounds_total=2,
            metrics=metrics,
            acceptance={"fnr_below_max": True},
            passed=True,
        )
        summary = result.summary()
        assert "PASSED" in summary
        assert "Baseline" in summary

    def test_failed_cycle_summary(self):
        metrics = EvolutionMetrics()
        result = CycleResult(
            cycle_id="c1",
            name="Baseline",
            rounds_completed=0,
            rounds_total=50,
            metrics=metrics,
            acceptance={"fnr_below_max": False},
            passed=False,
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "Baseline" in summary
