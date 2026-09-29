"""ObservationCoverage / IncidentLedger 单元测试 — 静默失败可观测性 (P2-10)."""

from __future__ import annotations

import pytest

from maref.observability.coverage import (
    IncidentLedger,
    IncidentRecord,
    ObservationCoverage,
)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class TestObservationCoverage:
    def test_full_coverage(self) -> None:
        coverage = ObservationCoverage()
        coverage.record_actual(5)
        coverage.record_observed(5)
        assert coverage.coverage() == 1.0
        assert coverage.blind_spot() is False

    def test_partial_coverage(self) -> None:
        coverage = ObservationCoverage()
        coverage.record_actual(10)
        coverage.record_observed(7)
        assert coverage.coverage() == pytest.approx(0.7)
        assert coverage.blind_spot() is True

    def test_no_actions_is_fully_covered(self) -> None:
        assert ObservationCoverage().coverage() == 1.0

    def test_coverage_capped_at_one(self) -> None:
        coverage = ObservationCoverage()
        coverage.record_actual(2)
        coverage.record_observed(9)
        assert coverage.coverage() == 1.0

    def test_window_expiry_resets_samples(self) -> None:
        clock = _Clock()
        coverage = ObservationCoverage(window_seconds=100.0, clock=clock)
        coverage.record_actual(3)
        coverage.record_observed(3)
        assert coverage.coverage() == 1.0
        clock.t = 500.0
        # 旧样本过期；此刻无实际动作 -> 视为全覆盖
        assert coverage.coverage() == 1.0
        coverage.record_actual(4)
        assert coverage.coverage() == 0.0

    def test_snapshot(self) -> None:
        coverage = ObservationCoverage()
        coverage.record_actual(4)
        coverage.record_observed(2)
        snap = coverage.snapshot()
        assert snap["actual"] == 4
        assert snap["observed"] == 2
        assert snap["blind_spot"] is True

    def test_invalid_config(self) -> None:
        with pytest.raises(ValueError):
            ObservationCoverage(window_seconds=0)
        with pytest.raises(ValueError):
            ObservationCoverage(threshold=1.5)


class TestIncidentRecord:
    def test_silent_duration(self) -> None:
        record = IncidentRecord("inc-1", started_at=100.0, detected_at=250.0, discovered_by="audit")
        assert record.silent_duration == 150.0
        payload = record.to_dict()
        assert payload["silent_duration"] == 150.0
        assert payload["discovered_by"] == "audit"

    def test_negative_silence_floored(self) -> None:
        record = IncidentRecord("inc-2", started_at=200.0, detected_at=100.0)
        assert record.silent_duration == 0.0


class TestIncidentLedger:
    def test_empty_summary(self) -> None:
        summary = IncidentLedger().summary()
        assert summary["count"] == 0
        assert summary["max_silent"] == 0.0

    def test_summary_aggregates(self) -> None:
        ledger = IncidentLedger()
        ledger.record(IncidentRecord("a", 0.0, 100.0, discovered_by="audit"))
        ledger.record(IncidentRecord("b", 0.0, 300.0, discovered_by="human"))
        ledger.record(IncidentRecord("c", 0.0, 50.0, discovered_by="audit"))
        summary = ledger.summary()
        assert ledger.count == 3
        assert summary["max_silent"] == 300.0
        assert summary["by_discoverer"] == {"audit": 2, "human": 1}
        assert summary["mean_silent"] == pytest.approx((100 + 300 + 50) / 3)

    def test_all_returns_copy(self) -> None:
        ledger = IncidentLedger()
        ledger.record(IncidentRecord("a", 0.0, 1.0))
        records = ledger.all()
        records.clear()
        assert ledger.count == 1
