"""Tests for time_awareness.py — TimeContext, TimelineTracker, DeadlineNegotiator."""
from __future__ import annotations

import time

import pytest

from maref.recursive.time_awareness import (
    ConflictPair,
    DeadlineNegotiator,
    TimeContext,
    TimelineTracker,
)


class TestTimeContext:
    def test_is_expired_no_deadline(self):
        ctx = TimeContext()
        assert ctx.is_expired() is False

    def test_is_expired_with_deadline(self):
        ctx = TimeContext(deadline=time.time() - 1)
        assert ctx.is_expired() is True

    def test_is_expired_future(self):
        ctx = TimeContext(deadline=time.time() + 3600)
        assert ctx.is_expired() is False

    def test_time_pressure_no_deadline(self):
        ctx = TimeContext()
        assert ctx.time_pressure() == 0.0

    def test_time_pressure_zero_estimation(self):
        ctx = TimeContext(deadline=time.time() + 100, estimated_duration=0)
        assert ctx.time_pressure() == 0.0

    def test_time_pressure_expired(self):
        ctx = TimeContext(deadline=time.time() - 10, estimated_duration=60)
        assert ctx.time_pressure() == 1.0

    def test_time_pressure_normal(self):
        ctx = TimeContext(deadline=time.time() + 30, estimated_duration=60)
        pressure = ctx.time_pressure()
        assert 0.0 <= pressure <= 1.0

    def test_remaining_seconds_no_deadline(self):
        ctx = TimeContext()
        assert ctx.remaining_seconds() == float("inf")

    def test_remaining_seconds_with_deadline(self):
        ctx = TimeContext(deadline=time.time() + 100)
        remaining = ctx.remaining_seconds()
        assert 0 < remaining <= 100

    def test_remaining_seconds_expired(self):
        ctx = TimeContext(deadline=time.time() - 10)
        assert ctx.remaining_seconds() == 0.0

    def test_should_escalate(self):
        ctx = TimeContext(deadline=time.time() - 10, estimated_duration=60)
        assert ctx.should_escalate(0.7) is True

    def test_should_escalate_false(self):
        ctx = TimeContext(deadline=time.time() + 3600, estimated_duration=60)
        assert ctx.should_escalate(0.7) is False

    def test_progress_at_deadline_zero_duration(self):
        ctx = TimeContext(estimated_duration=0)
        assert ctx.progress_at_deadline() == 1.0

    def test_progress_at_deadline_no_deadline(self):
        ctx = TimeContext(estimated_duration=100)
        assert ctx.progress_at_deadline() == 1.0

    def test_progress_at_deadline_normal(self):
        ctx = TimeContext(deadline=time.time() + 50, started_at=time.time() - 100, estimated_duration=200)
        progress = ctx.progress_at_deadline()
        assert 0.0 <= progress <= 1.0


class TestTimelineTracker:
    def test_register_and_get(self):
        tracker = TimelineTracker()
        ctx = TimeContext(task_id="task-1", deadline=time.time() + 100)
        tracker.register("task-1", ctx)
        assert tracker.get("task-1") is ctx
        assert tracker.get("nonexistent") is None

    def test_concurrent_timelines(self):
        tracker = TimelineTracker()
        tracker.register("active", TimeContext(deadline=time.time() + 100))
        tracker.register("expired", TimeContext(deadline=time.time() - 10))
        concurrent = tracker.concurrent_timelines("agent-1")
        assert len(concurrent) == 1
        assert concurrent[0].task_id == "active"

    def test_detect_conflict(self):
        tracker = TimelineTracker()
        now = time.time()
        tracker.register("a", TimeContext(started_at=now, deadline=now + 100, estimated_duration=100))
        tracker.register("b", TimeContext(started_at=now + 50, deadline=now + 150, estimated_duration=100))
        conflicts = tracker.detect_conflict()
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "temporal_overlap"

    def test_detect_conflict_no_overlap(self):
        tracker = TimelineTracker()
        now = time.time()
        tracker.register("a", TimeContext(started_at=now, deadline=now + 10, estimated_duration=10))
        tracker.register("b", TimeContext(started_at=now + 100, deadline=now + 200, estimated_duration=100))
        assert tracker.detect_conflict() == []

    def test_merge_timelines(self):
        tracker = TimelineTracker()
        tracker.register("a", TimeContext(estimated_duration=100, started_at=time.time()))
        tracker.register("b", TimeContext(estimated_duration=200, started_at=time.time() + 10))
        merged = tracker.merge_timelines(["a", "b"])
        assert merged is not None
        assert "merged" in merged.task_id
        assert merged.estimated_duration == 300

    def test_merge_timelines_empty(self):
        tracker = TimelineTracker()
        assert tracker.merge_timelines([]) is None
        assert tracker.merge_timelines(["nonexistent"]) is None

    def test_active_count(self):
        tracker = TimelineTracker()
        assert tracker.active_count() == 0
        tracker.register("a", TimeContext(deadline=time.time() + 100))
        assert tracker.active_count() == 1

    def test_remove(self):
        tracker = TimelineTracker()
        tracker.register("a", TimeContext())
        tracker.remove("a")
        assert tracker.get("a") is None
        tracker.remove("nonexistent")  # should not raise


class TestDeadlineNegotiator:
    def test_negotiate_deadline(self):
        negotiator = DeadlineNegotiator()
        adjusted = negotiator.negotiate_deadline("task-1", time.time() + 30)
        assert adjusted >= time.time()

    def test_negotiate_deadline_with_constraints(self):
        negotiator = DeadlineNegotiator()
        now = time.time()
        deadline = now + 100
        adjusted = negotiator.negotiate_deadline("task-1", deadline, {"min_deadline": now + 200, "max_deadline": now + 1000})
        assert adjusted >= now + 200

    def test_propose_extension_no_history(self):
        negotiator = DeadlineNegotiator()
        ext = negotiator.propose_extension("new-task", time.time() + 100)
        assert ext is None

    def test_propose_extension_with_history(self):
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("task-1", 60.0)
        negotiator.record_duration("task-1", 120.0)
        ext = negotiator.propose_extension("task-1", time.time() + 50)
        if ext is not None:
            assert ext > time.time() + 50

    def test_generate_time_update(self):
        negotiator = DeadlineNegotiator()
        ctx = TimeContext(deadline=time.time() - 10, estimated_duration=60)
        msg = negotiator.generate_time_update(ctx)
        assert "CRITICAL" in msg

    def test_generate_time_update_ok(self):
        negotiator = DeadlineNegotiator()
        ctx = TimeContext(deadline=time.time() + 3600, estimated_duration=3600, current_progress=0.5)
        msg = negotiator.generate_time_update(ctx)
        assert "OK" in msg

    @pytest.mark.parametrize("duration,expected_window", [
        (10.0, 1),
        (20.0, 2),
    ])
    def test_record_and_average_duration(self, duration, expected_window):
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("task-x", duration)
        assert negotiator.average_duration("task-x") == duration

    def test_average_duration_empty(self):
        negotiator = DeadlineNegotiator()
        assert negotiator.average_duration("nonexistent") is None

    def test_record_duration_history_window(self):
        negotiator = DeadlineNegotiator(history_window=3)
        for i in range(10):
            negotiator.record_duration("task-y", float(i))
        assert len(negotiator._history["task-y"]) == 3
