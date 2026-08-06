from __future__ import annotations

import pytest

from maref.recursive.coverage_tracker import CoverageTracker


class TestCoverageTracker:
    @pytest.fixture
    def tracker(self) -> CoverageTracker:
        return CoverageTracker(max_history=10)

    def test_record_creates_snapshot(self, tracker: CoverageTracker) -> None:
        snapshot = tracker.record("r67_baseline", 82.5)
        assert snapshot.coverage_pct == 82.5
        assert tracker.count == 1

    def test_record_with_per_module(self, tracker: CoverageTracker) -> None:
        tracker.record("s1", 80.0, per_module={"mod_a": 90.0, "mod_b": 70.0})
        latest = tracker.latest()
        assert latest is not None
        assert latest.per_module["mod_a"] == 90.0

    def test_trend_empty(self, tracker: CoverageTracker) -> None:
        t = tracker.trend()
        assert t["slope"] == 0.0

    def test_trend_increasing(self, tracker: CoverageTracker) -> None:
        for i in range(6):
            tracker.record(f"s{i}", 80.0 + i)
        t = tracker.trend(window=5)
        assert t["slope"] > 0

    def test_trend_decreasing(self, tracker: CoverageTracker) -> None:
        for i in range(6):
            tracker.record(f"s{i}", 85.0 - i)
        t = tracker.trend(window=5)
        assert t["slope"] < 0

    def test_low_coverage_modules(self, tracker: CoverageTracker) -> None:
        tracker.record("s1", 80.0, per_module={"a": 95.0, "b": 75.0, "c": 60.0})
        low = tracker.low_coverage_modules(threshold=80.0)
        assert len(low) == 2
        assert low[0][0] == "c"

    def test_low_coverage_modules_empty(self, tracker: CoverageTracker) -> None:
        tracker.record("s1", 85.0, per_module={"a": 95.0, "b": 90.0})
        low = tracker.low_coverage_modules(threshold=80.0)
        assert low == []

    def test_compare_snapshots(self, tracker: CoverageTracker) -> None:
        tracker.record("s1", 80.0, per_module={"a": 85.0})
        tracker.record("s2", 83.0, per_module={"a": 90.0})
        diff = tracker.compare("s1", "s2")
        assert diff["coverage_delta"] == 3.0
        assert "a" in diff["per_module_deltas"]

    def test_compare_not_found(self, tracker: CoverageTracker) -> None:
        diff = tracker.compare("s1", "s2")
        assert "error" in diff

    def test_max_history(self) -> None:
        tracker = CoverageTracker(max_history=3)
        for i in range(6):
            tracker.record(f"s{i}", 80.0 + i)
        assert tracker.count == 3
        assert tracker.latest().snapshot_id == "s5"

    def test_latest_empty(self, tracker: CoverageTracker) -> None:
        assert tracker.latest() is None

    def test_snapshot_has_test_count(self, tracker: CoverageTracker) -> None:
        tracker.record("s1", 82.0, test_count=650)
        assert tracker.latest().test_count == 650
