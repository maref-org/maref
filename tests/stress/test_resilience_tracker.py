from __future__ import annotations

import pytest

from maref.stress.resilience_tracker import ResilienceRecord, ResilienceTracker


class TestResilienceRecord:
    def test_default_data_is_empty_dict(self):
        r = ResilienceRecord(round_id="r1", timestamp=100.0, resilience_score=0.8)
        assert r.data == {}

    def test_with_data(self):
        r = ResilienceRecord(round_id="r1", timestamp=100.0, resilience_score=0.8,
                             data={"key": "val"})
        assert r.data["key"] == "val"


class TestResilienceTracker:
    def test_initially_empty(self):
        t = ResilienceTracker()
        assert t.count == 0
        assert t.records == []
        assert t.worst() is None
        assert t.best() is None

    def test_record_round(self):
        t = ResilienceTracker()
        rec = t.record_round("r1", 0.85, {"note": "first"})
        assert isinstance(rec, ResilienceRecord)
        assert rec.round_id == "r1"
        assert rec.resilience_score == 0.85
        assert t.count == 1

    def test_record_round_empty_data(self):
        t = ResilienceTracker()
        rec = t.record_round("r1", 0.9)
        assert rec.data == {}

    def test_worst_and_best(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.5)
        t.record_round("r2", 0.9)
        t.record_round("r3", 0.3)
        assert t.worst().resilience_score == 0.3
        assert t.worst().round_id == "r3"
        assert t.best().resilience_score == 0.9
        assert t.best().round_id == "r2"

    def test_trend_with_fewer_than_two_records(self):
        t = ResilienceTracker()
        assert t.trend() == {"slope": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
        t.record_round("r1", 0.5)
        assert t.trend() == {"slope": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}

    def test_trend_with_multiple_records(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.2)
        t.record_round("r2", 0.4)
        t.record_round("r3", 0.6)
        t.record_round("r4", 0.8)
        t.record_round("r5", 1.0)
        trend = t.trend(window=5)
        assert trend["slope"] > 0
        assert trend["mean"] == 0.6
        assert trend["min"] == 0.2
        assert trend["max"] == 1.0

    def test_trend_window_smaller_than_history(self):
        t = ResilienceTracker()
        for i in range(10):
            t.record_round(f"r{i}", i * 0.1)
        trend = t.trend(window=3)
        assert trend["mean"] == 0.8
        assert trend["min"] == 0.7
        assert trend["max"] == 0.9

    def test_max_history_truncation(self):
        t = ResilienceTracker(max_history=3)
        t.record_round("r1", 0.1)
        t.record_round("r2", 0.2)
        t.record_round("r3", 0.3)
        t.record_round("r4", 0.4)
        assert t.count == 3
        assert t.records[0].round_id == "r2"

    def test_compare_existing_rounds(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.3)
        t.record_round("r2", 0.9)
        result = t.compare("r1", "r2")
        assert result["score_a"] == 0.3
        assert result["score_b"] == 0.9
        assert result["delta"] == 0.6

    def test_compare_missing_round(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.5)
        result = t.compare("r1", "nonexistent")
        assert result == {"error": "round not found"}

    def test_compare_both_missing(self):
        t = ResilienceTracker()
        result = t.compare("a", "b")
        assert result == {"error": "round not found"}

    def test_records_property_returns_copy(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.5)
        recs = t.records
        recs.clear()
        assert t.count == 1

    def test_identical_scores_worst_best(self):
        t = ResilienceTracker()
        t.record_round("r1", 0.5)
        t.record_round("r2", 0.5)
        assert t.best().resilience_score == 0.5
        assert t.worst().resilience_score == 0.5
