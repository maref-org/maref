from __future__ import annotations

import time

from maref.recursive.time_awareness import (
    DeadlineNegotiator,
    TimeContext,
    TimelineTracker,
)


class TestTimeContext:
    def test_create_context(self) -> None:
        ctx = TimeContext(
            task_id="task_1",
            deadline=time.time() + 3600,
            estimated_duration=1800,
        )
        assert not ctx.is_expired()
        assert ctx.time_pressure() >= 0

    def test_expired(self) -> None:
        ctx = TimeContext(
            task_id="task_1",
            deadline=time.time() - 1,
            estimated_duration=10,
        )
        assert ctx.is_expired()

    def test_no_deadline_not_expired(self) -> None:
        ctx = TimeContext(task_id="task_1")
        assert not ctx.is_expired()

    def test_time_pressure_near_deadline(self) -> None:
        ctx = TimeContext(
            task_id="task_1",
            deadline=time.time() + 5,
            estimated_duration=60,
            started_at=time.time() - 55,
        )
        pressure = ctx.time_pressure()
        assert pressure > 0.8

    def test_time_pressure_no_pressure(self) -> None:
        ctx = TimeContext(
            task_id="task_1",
            deadline=time.time() + 3600,
            estimated_duration=60,
        )
        pressure = ctx.time_pressure()
        assert pressure < 0.2

    def test_should_escalate(self) -> None:
        ctx = TimeContext(
            task_id="task_1",
            deadline=time.time() + 1,
            estimated_duration=100,
        )
        assert ctx.should_escalate(pressure_threshold=0.5)

    def test_remaining_seconds(self) -> None:
        deadline = time.time() + 100
        ctx = TimeContext(task_id="t1", deadline=deadline)
        remaining = ctx.remaining_seconds()
        assert 0 < remaining <= 100

    def test_remaining_infinite_no_deadline(self) -> None:
        ctx = TimeContext(task_id="t1")
        assert ctx.remaining_seconds() == float("inf")

    def test_progress_at_deadline(self) -> None:
        ctx = TimeContext(
            task_id="t1",
            deadline=time.time() + 60,
            estimated_duration=120,
        )
        progress = ctx.progress_at_deadline()
        assert 0 <= progress <= 1.0


class TestTimelineTracker:
    def test_register_and_get(self) -> None:
        tracker = TimelineTracker()
        ctx = TimeContext(task_id="t1")
        tracker.register("t1", ctx)
        assert tracker.get("t1") is ctx

    def test_concurrent_timelines(self) -> None:
        tracker = TimelineTracker()
        tracker.register("t1", TimeContext(task_id="t1", deadline=time.time() + 3600))
        tracker.register("t2", TimeContext(task_id="t2", deadline=time.time() + 3600))
        active = tracker.concurrent_timelines("")
        assert len(active) >= 2

    def test_detect_conflict_overlapping(self) -> None:
        tracker = TimelineTracker()
        now = time.time()
        tracker.register(
            "t1",
            TimeContext(
                task_id="t1",
                deadline=now + 100,
                started_at=now,
                estimated_duration=50,
            ),
        )
        tracker.register(
            "t2",
            TimeContext(
                task_id="t2",
                deadline=now + 80,
                started_at=now + 20,
                estimated_duration=50,
            ),
        )
        conflicts = tracker.detect_conflict()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "temporal_overlap"

    def test_no_conflict_sequential(self) -> None:
        tracker = TimelineTracker()
        now = time.time()
        tracker.register(
            "t1",
            TimeContext(
                task_id="t1",
                deadline=now + 50,
                started_at=now,
                estimated_duration=50,
            ),
        )
        tracker.register(
            "t2",
            TimeContext(
                task_id="t2",
                deadline=now + 150,
                started_at=now + 51,
                estimated_duration=50,
            ),
        )
        conflicts = tracker.detect_conflict()
        assert len(conflicts) == 0

    def test_merge_timelines(self) -> None:
        tracker = TimelineTracker()
        now = time.time()
        tracker.register(
            "t1",
            TimeContext(
                task_id="t1",
                deadline=now + 60,
                estimated_duration=30,
                started_at=now,
            ),
        )
        tracker.register(
            "t2",
            TimeContext(
                task_id="t2",
                deadline=now + 120,
                estimated_duration=60,
                started_at=now + 10,
            ),
        )
        merged = tracker.merge_timelines(["t1", "t2"])
        assert merged is not None
        assert merged.estimated_duration == 90
        assert merged.started_at == now

    def test_remove_timeline(self) -> None:
        tracker = TimelineTracker()
        tracker.register("t1", TimeContext(task_id="t1"))
        tracker.remove("t1")
        assert tracker.get("t1") is None


class TestDeadlineNegotiator:
    def test_negotiate_deadline(self) -> None:
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("test_task", 30.0)
        negotiator.record_duration("test_task", 32.0)
        proposed = time.time() + 20
        result = negotiator.negotiate_deadline("test_task", proposed)
        assert result >= proposed

    def test_negotiate_with_constraints(self) -> None:
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("task", 10.0)
        proposed = time.time() + 5
        constraints = {"min_deadline": time.time() + 50, "max_deadline": time.time() + 200}
        result = negotiator.negotiate_deadline("task", proposed, constraints)
        assert result >= constraints["min_deadline"]

    def test_propose_extension(self) -> None:
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("task", 30.0)
        extension = negotiator.propose_extension("task", time.time() + 10)
        assert extension is not None
        assert extension > time.time() + 10

    def test_propose_extension_no_history(self) -> None:
        negotiator = DeadlineNegotiator()
        extension = negotiator.propose_extension("unknown_task", time.time() + 10)
        assert extension is None

    def test_generate_time_update(self) -> None:
        negotiator = DeadlineNegotiator()
        ctx = TimeContext(
            task_id="t1",
            deadline=time.time() + 300,
            estimated_duration=600,
            current_progress=0.3,
        )
        update = negotiator.generate_time_update(ctx)
        assert len(update) > 0

    def test_generate_critical_update(self) -> None:
        negotiator = DeadlineNegotiator()
        ctx = TimeContext(
            task_id="t1",
            deadline=time.time() + 1,
            estimated_duration=600,
            current_progress=0.1,
        )
        update = negotiator.generate_time_update(ctx)
        assert "CRITICAL" in update

    def test_average_duration(self) -> None:
        negotiator = DeadlineNegotiator()
        negotiator.record_duration("task", 10.0)
        negotiator.record_duration("task", 20.0)
        assert negotiator.average_duration("task") == 15.0
