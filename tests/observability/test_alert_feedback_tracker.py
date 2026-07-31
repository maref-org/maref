"""Tests for AlertFeedbackTracker — M2 alert→fix→verify tracking."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from maref.observability.alert_feedback_tracker import AlertFeedbackTracker, AlertRecord


class TestAlertRecord:
    def test_new_alert_is_open(self) -> None:
        record = AlertRecord(alert_id="a1", name="test", severity="critical", message="x", triggered_at=time.time())
        assert record.is_open is True
        assert record.is_acknowledged is False
        assert record.is_fixed is False

    def test_acknowledge_marks_acknowledged(self) -> None:
        record = AlertRecord(alert_id="a1", name="test", severity="critical", message="x", triggered_at=time.time())
        record.acknowledged_at = time.time()
        assert record.is_acknowledged is True
        assert record.is_open is True

    def test_full_lifecycle_closes_alert(self) -> None:
        record = AlertRecord(
            alert_id="a1", name="test", severity="critical", message="x",
            triggered_at=time.time(), acknowledged_at=time.time(),
            fixed_at=time.time(), verified_at=time.time(),
        )
        assert record.is_open is False
        assert record.time_to_fix is not None
        assert record.time_to_verify is not None

    def test_calculates_time_to_fix(self) -> None:
        now = time.time()
        record = AlertRecord(
            alert_id="a1", name="test", severity="critical", message="x",
            triggered_at=now - 3600, fixed_at=now,
        )
        assert record.time_to_fix is not None
        assert 0.9 <= record.time_to_fix / 3600 <= 1.1

    def test_to_dict_contains_all_fields(self) -> None:
        now = time.time()
        record = AlertRecord(
            alert_id="a1", name="test", severity="critical", message="x",
            triggered_at=now, repeat_count=2, subsystem="pulse",
        )
        d = record.to_dict()
        assert d["alert_id"] == "a1"
        assert d["repeat_count"] == 2
        assert d["is_open"] is True
        assert d["subsystem"] == "pulse"


class TestAlertFeedbackTracker:
    def test_empty_tracker_has_no_alerts(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        assert len(tracker.get_open_alerts()) == 0
        assert tracker.repeat_alert_rate()["total_alerts"] == 0

    def test_record_alert_creates_entry(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        record = tracker.record_alert("M0 Fail", "critical", "test failure")
        assert record.name == "M0 Fail"
        assert record.severity == "critical"
        assert len(tracker.get_open_alerts()) == 1

    def test_dedup_reuses_existing(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        r1 = tracker.record_alert("M0 Fail", "critical", "test")
        r2 = tracker.record_alert("M0 Fail", "critical", "test")
        assert r1.alert_id == r2.alert_id  # dedup returns same
        assert r2.repeat_count >= 1

    def test_acknowledge_alert(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        record = tracker.record_alert("M0 Fail", "critical", "test")
        assert tracker.acknowledge_alert(record.alert_id) is True
        assert tracker.acknowledge_alert(record.alert_id) is False  # already acked

    def test_mark_fixed_and_verified(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        record = tracker.record_alert("M0 Fail", "critical", "test")
        assert tracker.mark_fixed(record.alert_id, "restarted agent") is True
        assert tracker.mark_verified(record.alert_id) is True
        assert len(tracker.get_open_alerts()) == 0

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        tracker1 = AlertFeedbackTracker(state_path=state_path)
        tracker1.record_alert("M0 Fail", "critical", "test")
        assert len(tracker1.get_open_alerts()) == 1

        tracker2 = AlertFeedbackTracker(state_path=state_path)
        assert len(tracker2.get_open_alerts()) == 1  # loaded from disk

    def test_repeat_alert_rate(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        tracker.record_alert("A", "critical", "msg1")
        tracker.record_alert("B", "warning", "msg2")
        result = tracker.repeat_alert_rate(window_hours=24)
        assert result["total_alerts"] >= 2
        assert result["repeat_alerts"] == 0
        assert result["repeat_rate"] == 0.0

    def test_repeat_alert_rate_with_repeats(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        tracker.record_alert("C", "critical", "msg")
        # Force a second alert with same name outside dedup window
        import uuid
        from maref.observability.alert_feedback_tracker import AlertRecord as AR
        r = AR(
            alert_id=uuid.uuid4().hex[:12],
            name="C", severity="critical", message="msg",
            triggered_at=time.time(),
            repeat_count=0,
        )
        tracker._alerts[r.alert_id] = r
        tracker._alert_timestamps.append(time.time())
        tracker._save()
        result = tracker.repeat_alert_rate(window_hours=24)
        assert result["repeat_rate"] > 0

    def test_alert_disappearance_fresh(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        tracker.record_alert("A", "critical", "msg")
        result = tracker.check_alert_disappearance(silence_window=900)
        assert result["passed"] is True
        assert result["last_alert_seconds_ago"] is not None

    def test_alert_disappearance_silent(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        assert tracker.check_alert_disappearance(silence_window=0)["passed"] is False

    def test_recovery_rate_all_fixed(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        r = tracker.record_alert("A", "critical", "msg")
        tracker.mark_fixed(r.alert_id, "fixed")
        tracker.mark_verified(r.alert_id)
        result = tracker.alert_recovery_rate(window_hours=72)
        assert result["recovery_rate"] >= 0.9

    def test_summary_includes_all_metrics(self, tmp_path: Path) -> None:
        tracker = AlertFeedbackTracker(state_path=tmp_path / "state.json")
        tracker.record_alert("A", "critical", "msg")
        summary = tracker.summary()
        assert "total_tracked_alerts" in summary
        assert "open_alerts" in summary
        assert "repeat_alert_rate" in summary
        assert "alert_recovery" in summary
        assert "alert_disappearance" in summary
