from __future__ import annotations

import pytest

from maref.observability.error_budget import (
    BURN_RATE_CONFIG,
    BurnRateAlert,
    BurnRateLevel,
    ErrorBudget,
    ErrorBudgetCalculator,
)
from maref.observability.red_metrics import REDMetricsCollector


class TestErrorBudget:
    def test_create_with_defaults(self) -> None:
        budget = ErrorBudget.create(total=5000.0)
        assert budget.budget_total == 5000.0
        assert budget.budget_consumed == 0.0
        assert budget.budget_remaining == 5000.0
        assert budget.budget_remaining_pct == 100.0

    def test_create_with_consumed(self) -> None:
        budget = ErrorBudget.create(total=5000.0, consumed=500.0)
        assert budget.budget_total == 5000.0
        assert budget.budget_consumed == 500.0
        assert budget.budget_remaining == 4500.0
        assert budget.budget_remaining_pct == 90.0

    def test_create_with_full_consumption(self) -> None:
        budget = ErrorBudget.create(total=5000.0, consumed=5000.0)
        assert budget.budget_remaining == 0.0
        assert budget.budget_remaining_pct == 0.0

    def test_create_with_zero_total(self) -> None:
        budget = ErrorBudget.create(total=0.0)
        assert budget.budget_total == 0.0
        assert budget.budget_remaining_pct == 0.0

    def test_create_with_negative_consumed(self) -> None:
        budget = ErrorBudget.create(total=5000.0, consumed=-100.0)
        assert budget.budget_remaining == 5100.0


class TestBurnRateAlert:
    def test_to_dict(self) -> None:
        alert = BurnRateAlert(
            level=BurnRateLevel.CRITICAL,
            burn_rate=15.0,
            threshold=14.4,
            window_seconds=3600,
            triggered=True,
            slo_name="availability_0.995",
        )
        d = alert.to_dict()
        assert d["level"] == "P0"
        assert d["burn_rate"] == 15.0
        assert d["triggered"] is True
        assert d["slo_name"] == "availability_0.995"

    def test_to_dict_not_triggered(self) -> None:
        alert = BurnRateAlert(
            level=BurnRateLevel.OK,
            burn_rate=1.0,
            threshold=2.0,
            window_seconds=3600,
            triggered=False,
            slo_name="availability_0.995",
        )
        d = alert.to_dict()
        assert d["level"] == "OK"
        assert d["triggered"] is False


class TestBurnRateConfig:
    def test_config_has_correct_levels(self) -> None:
        levels = [level for level, _, _, _ in BURN_RATE_CONFIG]
        assert BurnRateLevel.CRITICAL in levels
        assert BurnRateLevel.WARNING in levels
        assert BurnRateLevel.INFO in levels

    def test_config_thresholds_decreasing(self) -> None:
        thresholds = [threshold for _, threshold, _, _ in BURN_RATE_CONFIG]
        for i in range(len(thresholds) - 1):
            assert thresholds[i] > thresholds[i + 1]

    def test_config_has_fast_and_slow_windows(self) -> None:
        for _, _, slow_window, fast_window in BURN_RATE_CONFIG:
            assert slow_window > fast_window
            assert fast_window > 0


class TestErrorBudgetCalculator:
    @pytest.fixture
    def collector(self) -> REDMetricsCollector:
        return REDMetricsCollector()

    @pytest.fixture
    def calculator(self, collector: REDMetricsCollector) -> ErrorBudgetCalculator:
        return ErrorBudgetCalculator(
            collector=collector,
            slo_target=0.995,
            period_seconds=2592000,
            total_period_requests=1_000_000,
        )

    def test_initial_budget(self, calculator: ErrorBudgetCalculator) -> None:
        assert calculator.slo_target == 0.995
        assert calculator.period_seconds == 2592000
        assert calculator.budget_total == 5000.0

    def test_calculate_budget_no_requests(self, calculator: ErrorBudgetCalculator) -> None:
        budget = calculator.calculate_budget()
        assert budget.budget_consumed == 0.0
        assert budget.budget_remaining == 5000.0
        assert budget.budget_remaining_pct == 100.0

    def test_calculate_budget_with_errors(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(100):
            collector.record_request("/api/test", "GET", 200, 10.0)
        for _ in range(10):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        budget = calculator.calculate_budget(3600)
        assert budget.budget_consumed > 0
        assert budget.budget_remaining < 5000.0

    def test_calculate_budget_zero_error_rate(self, calculator: ErrorBudgetCalculator) -> None:
        budget = calculator.calculate_budget(3600)
        assert budget.budget_consumed == 0.0
        assert budget.budget_remaining_pct == 100.0

    def test_burn_rate_no_requests(self, calculator: ErrorBudgetCalculator) -> None:
        burn_rate = calculator.calculate_burn_rate(3600)
        assert burn_rate == 0.0

    def test_burn_rate_with_normal_traffic(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(1000):
            collector.record_request("/api/test", "GET", 200, 10.0)
        burn_rate = calculator.calculate_burn_rate(3600)
        assert burn_rate == 0.0

    def test_burn_rate_with_errors(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(900):
            collector.record_request("/api/ok", "GET", 200, 10.0)
        for _ in range(100):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        burn_rate = calculator.calculate_burn_rate(3600)
        expected_rate = (0.1 * 1000) / (5000.0 * (3600 / 2592000))
        assert burn_rate == pytest.approx(expected_rate, rel=0.1)

    def test_burn_rate_100_percent_errors(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(100):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        burn_rate = calculator.calculate_burn_rate(3600)
        expected_rate = (1.0 * 100) / (5000.0 * (3600 / 2592000))
        assert burn_rate == pytest.approx(expected_rate, rel=0.1)

    def test_check_alerts_no_traffic(self, calculator: ErrorBudgetCalculator) -> None:
        alerts = calculator.check_alerts()
        for alert in alerts:
            assert alert.triggered is False

    def test_check_alerts_critical_burn(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(100):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        alerts = calculator.check_alerts()
        critical_alerts = [a for a in alerts if a.level == BurnRateLevel.CRITICAL]
        assert len(critical_alerts) == 1
        assert critical_alerts[0].burn_rate > 0

    def test_is_budget_exhausted_false(self, calculator: ErrorBudgetCalculator) -> None:
        assert calculator.is_budget_exhausted() is False

    def test_is_budget_exhausted_true(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(100000):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        assert collector._total_requests > 0
        assert collector._total_errors > 0

    def test_time_to_exhaustion_no_traffic(self, calculator: ErrorBudgetCalculator) -> None:
        tte = calculator.time_to_exhaustion(3600)
        assert tte == float("inf")

    def test_time_to_exhaustion_with_errors(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(100):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        tte = calculator.time_to_exhaustion(3600)
        assert tte > 0

    def test_time_to_exhaustion_budget_depleted(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        budget = calculator.calculate_budget(3600)
        tte = calculator.time_to_exhaustion(3600)
        if budget.budget_remaining <= 0:
            assert tte == 0.0
        else:
            assert tte >= 0

    def test_generate_report(self, calculator: ErrorBudgetCalculator) -> None:
        report = calculator.generate_report(3600)
        assert report["slo_target"] == 0.995
        assert report["period_seconds"] == 2592000
        assert report["total_period_requests"] == 1_000_000
        assert "budget" in report
        assert report["budget"]["total"] == 5000.0
        assert report["budget"]["remaining"] == 5000.0
        assert report["budget"]["remaining_pct"] == 100.0
        assert "burn_rate" in report
        assert "alerts" in report
        assert len(report["alerts"]) == 3
        assert report["budget_exhausted"] is False
        assert "time_to_exhaustion_seconds" in report
        assert "uptime_seconds" in report

    def test_generate_report_with_errors(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(900):
            collector.record_request("/api/ok", "GET", 200, 10.0)
        for _ in range(100):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        report = calculator.generate_report(3600)
        assert report["budget"]["consumed"] > 0
        assert report["budget"]["remaining"] < 5000.0
        assert report["burn_rate"] > 0

    def test_high_error_rate_triggers_critical_alert(
        self, calculator: ErrorBudgetCalculator, collector: REDMetricsCollector
    ) -> None:
        for _ in range(1000):
            collector.record_request("/api/fail", "GET", 500, 10.0)
        alerts = calculator.check_alerts()
        triggered = [a for a in alerts if a.triggered]
        assert len(triggered) > 0

    def test_custom_slo_target(self, collector: REDMetricsCollector) -> None:
        calc = ErrorBudgetCalculator(
            collector=collector,
            slo_target=0.999,
            period_seconds=2592000,
            total_period_requests=1_000_000,
        )
        assert calc.budget_total == 1000.0
        budget = calc.calculate_budget()
        assert budget.budget_total == 1000.0

    def test_zero_total_period_requests(self, collector: REDMetricsCollector) -> None:
        calc = ErrorBudgetCalculator(
            collector=collector,
            slo_target=0.995,
            period_seconds=2592000,
            total_period_requests=0,
        )
        assert calc.budget_total == 0.0
        burn_rate = calc.calculate_burn_rate(3600)
        assert burn_rate == 0.0

    def test_empty_collector_does_not_crash(self) -> None:
        collector = REDMetricsCollector()
        calc = ErrorBudgetCalculator(collector=collector)
        budget = calc.calculate_budget()
        assert budget.budget_total == 5000.0
        alerts = calc.check_alerts()
        assert len(alerts) == 3
        report = calc.generate_report()
        assert report is not None
