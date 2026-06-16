from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone

import pytest

from maref.executor.queue import TaskQueue
from maref.executor.scheduler import CronExpression, CronJob, Scheduler
from maref.executor.types import Task, TaskPriority


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def queue(db_path: str) -> TaskQueue:
    q = TaskQueue(db_path)
    yield q
    q.close()


@pytest.fixture
def scheduler(queue: TaskQueue) -> Scheduler:
    s = Scheduler(queue)
    yield s
    if s._running:
        s.stop()


class TestCronExpression:
    def test_every_minute(self) -> None:
        cron = CronExpression("* * * * *")
        assert cron._minutes == [("any",)]
        assert cron._hours == [("any",)]
        assert cron._days_of_month == [("any",)]
        assert cron._months == [("any",)]
        assert cron._days_of_week == [("any",)]

    def test_specific_values(self) -> None:
        cron = CronExpression("30 14 15 6 0")
        assert cron._minutes == [("exact", 30)]
        assert cron._hours == [("exact", 14)]
        assert cron._days_of_month == [("exact", 15)]
        assert cron._months == [("exact", 6)]
        assert cron._days_of_week == [("exact", 0)]

    def test_step_values(self) -> None:
        cron = CronExpression("*/15 */2 */3 */4 */5")
        assert cron._minutes == [("every", 15)]
        assert cron._hours == [("every", 2)]
        assert cron._days_of_month == [("every", 3)]
        assert cron._months == [("every", 4)]
        assert cron._days_of_week == [("every", 5)]

    def test_comma_list(self) -> None:
        cron = CronExpression("0,15,30,45 0,12 1,15 1,6,12 0,3,6")
        assert ("exact", 0) in cron._minutes
        assert ("exact", 15) in cron._minutes
        assert ("exact", 45) in cron._minutes
        assert ("exact", 0) in cron._hours
        assert ("exact", 12) in cron._hours
        assert ("exact", 1) in cron._days_of_month
        assert ("exact", 15) in cron._days_of_month

    def test_range_values(self) -> None:
        cron = CronExpression("0 9-17 1-5 1-3 1-5")
        assert cron._hours == [("range", 9, 17)]
        assert cron._days_of_month == [("range", 1, 5)]
        assert cron._months == [("range", 1, 3)]
        assert cron._days_of_week == [("range", 1, 5)]

    def test_mixed_field(self) -> None:
        cron = CronExpression("0,*/15 9-17,0 1,15,*/5 1-6,12 0-4,6")
        assert ("exact", 0) in cron._minutes
        assert ("every", 15) in cron._minutes
        assert ("range", 9, 17) in cron._hours
        assert ("exact", 0) in cron._hours

    def test_invalid_field_count(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron"):
            CronExpression("* * * *")

    def test_invalid_field_count_too_many(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron"):
            CronExpression("* * * * * *")

    def test_empty_expression(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron"):
            CronExpression("")

    def test_out_of_range_value(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            CronExpression("60 * * * *")

    def test_out_of_range_hour(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            CronExpression("* 24 * * *")

    def test_invalid_step_zero(self) -> None:
        with pytest.raises(ValueError, match="Invalid step"):
            CronExpression("*/0 * * * *")

    def test_invalid_range_order(self) -> None:
        with pytest.raises(ValueError, match="Invalid range"):
            CronExpression("* * * * 5-1")

    def test_repr(self) -> None:
        cron = CronExpression("* * * * *")
        assert repr(cron) == "CronExpression('* * * * *')"


class TestCronExpressionMatch:
    def test_every_minute_matches(self) -> None:
        cron = CronExpression("* * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        assert cron.matches(dt)

    def test_exact_minute_matches(self) -> None:
        cron = CronExpression("30 * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        assert cron.matches(dt)

    def test_exact_minute_no_match(self) -> None:
        cron = CronExpression("0 * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        assert not cron.matches(dt)

    def test_exact_hour_and_minute(self) -> None:
        cron = CronExpression("0 14 * * *")
        dt = datetime(2026, 5, 21, 14, 0, 0, tzinfo=timezone.utc)
        assert cron.matches(dt)
        dt2 = datetime(2026, 5, 21, 15, 0, 0, tzinfo=timezone.utc)
        assert not cron.matches(dt2)

    def test_step_minutes(self) -> None:
        cron = CronExpression("*/15 * * * *")
        assert cron.matches(datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 10, 15, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 10, 45, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 5, 21, 10, 7, 0, tzinfo=timezone.utc))

    def test_range_hours(self) -> None:
        cron = CronExpression("0 9-17 * * *")
        assert cron.matches(datetime(2026, 5, 21, 9, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 17, 0, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 5, 21, 8, 0, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 5, 21, 18, 0, 0, tzinfo=timezone.utc))

    def test_comma_list_match(self) -> None:
        cron = CronExpression("0,30 0,12 * * *")
        assert cron.matches(datetime(2026, 5, 21, 0, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 0, 30, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 5, 21, 6, 0, 0, tzinfo=timezone.utc))

    def test_specific_month(self) -> None:
        cron = CronExpression("* * * 6 *")
        assert cron.matches(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_specific_day_of_week(self) -> None:
        cron = CronExpression("* * * * 0")
        sunday = datetime(2026, 5, 24, 10, 0, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
        assert cron.matches(sunday)
        assert not cron.matches(monday)

    def test_specific_day_of_week_monday(self) -> None:
        cron = CronExpression("* * * * 1")
        monday = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 5, 24, 10, 0, 0, tzinfo=timezone.utc)
        assert cron.matches(monday)
        assert not cron.matches(sunday)

    def test_weekday_cron_mon_to_fri(self) -> None:
        cron = CronExpression("* * * * 1-5")
        monday = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
        friday = datetime(2026, 5, 29, 10, 0, 0, tzinfo=timezone.utc)
        saturday = datetime(2026, 5, 30, 10, 0, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 5, 31, 10, 0, 0, tzinfo=timezone.utc)
        assert cron.matches(monday)
        assert cron.matches(friday)
        assert not cron.matches(saturday)
        assert not cron.matches(sunday)


class TestCronExpressionNextAfter:
    def test_next_every_minute(self) -> None:
        cron = CronExpression("* * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 21, 10, 31, 0, tzinfo=timezone.utc)

    def test_next_exact_minute_later_same_hour(self) -> None:
        cron = CronExpression("45 * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 21, 10, 45, 0, tzinfo=timezone.utc)

    def test_next_exact_minute_next_hour(self) -> None:
        cron = CronExpression("15 * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 21, 11, 15, 0, tzinfo=timezone.utc)

    def test_next_step_minutes(self) -> None:
        cron = CronExpression("*/30 * * * *")
        dt = datetime(2026, 5, 21, 10, 15, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 21, 10, 30, 0, tzinfo=timezone.utc)

    def test_next_specific_hour(self) -> None:
        cron = CronExpression("0 14 * * *")
        dt = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 21, 14, 0, 0, tzinfo=timezone.utc)

    def test_next_specific_hour_next_day(self) -> None:
        cron = CronExpression("0 8 * * *")
        dt = datetime(2026, 5, 21, 14, 0, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)

    def test_next_specific_day_of_week(self) -> None:
        cron = CronExpression("0 0 * * 0")
        dt = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 5, 24, 0, 0, 0, tzinfo=timezone.utc)

    def test_next_cross_year_boundary(self) -> None:
        cron = CronExpression("0 0 1 1 *")
        dt = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_next_end_of_month(self) -> None:
        cron = CronExpression("0 0 1 * *")
        dt = datetime(2026, 5, 31, 10, 0, 0, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_next_no_match_raises(self) -> None:
        cron = CronExpression("0 0 30 2 *")
        dt = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="No matching time"):
            cron.next_after(dt)


class TestSchedulerCreate:
    def test_create_scheduler(self, scheduler: Scheduler) -> None:
        assert scheduler._queue is not None
        assert scheduler._tick_interval == 60.0
        assert scheduler._jobs == {}
        assert not scheduler._running
        assert scheduler._thread is None

    def test_create_with_custom_tick(self, queue: TaskQueue) -> None:
        s = Scheduler(queue, tick_interval=0.5)
        assert s._tick_interval == 0.5
        s.stop()


class TestSchedulerAddCronJob:
    def test_add_job_returns_id(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test-job", "* * * * *", task)
        assert job_id is not None
        assert isinstance(job_id, str)

    def test_add_job_stores_job(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test-job", "* * * * *", task)
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.name == "test-job"
        assert job.cron_expression == "* * * * *"
        assert job.task_template.name == "test"
        assert job.enabled is True
        assert job.run_count == 0

    def test_add_job_validates_cron(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        with pytest.raises(ValueError, match="Invalid cron"):
            scheduler.add_cron_job("bad", "invalid", task)

    def test_add_multiple_jobs(self, scheduler: Scheduler) -> None:
        ids = []
        for i in range(5):
            task = Task(name=f"task-{i}")
            jid = scheduler.add_cron_job(f"job-{i}", "* * * * *", task)
            ids.append(jid)
        assert len(scheduler.list_jobs()) == 5
        assert all(jid is not None for jid in ids)


class TestSchedulerRemoveJob:
    def test_remove_existing_job(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test", "* * * * *", task)
        result = scheduler.remove_job(job_id)
        assert result is True
        assert scheduler.get_job(job_id) is None

    def test_remove_nonexistent_job(self, scheduler: Scheduler) -> None:
        result = scheduler.remove_job("nonexistent")
        assert result is False

    def test_remove_job_reduces_count(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test", "* * * * *", task)
        scheduler.remove_job(job_id)
        assert len(scheduler.list_jobs()) == 0


class TestSchedulerListJobs:
    def test_list_empty(self, scheduler: Scheduler) -> None:
        assert scheduler.list_jobs() == []

    def test_list_returns_copies(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        scheduler.add_cron_job("a", "* * * * *", task)
        scheduler.add_cron_job("b", "* * * * *", task)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        names = {j.name for j in jobs}
        assert names == {"a", "b"}


class TestSchedulerGetJob:
    def test_get_existing_job(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test", "* * * * *", task)
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.name == "test"

    def test_get_nonexistent_job(self, scheduler: Scheduler) -> None:
        job = scheduler.get_job("nonexistent")
        assert job is None


class TestSchedulerRegisterEvent:
    def test_register_event_returns_id(self, scheduler: Scheduler) -> None:
        def handler(data: dict) -> None:
            pass

        event_id = scheduler.register_event("test_event", handler)
        assert event_id is not None
        assert isinstance(event_id, str)

    def test_register_multiple_events(self, scheduler: Scheduler) -> None:
        results: list[str] = []

        def handler_a(data: dict) -> None:
            results.append("a")

        def handler_b(data: dict) -> None:
            results.append("b")

        id_a = scheduler.register_event("type_a", handler_a)
        id_b = scheduler.register_event("type_b", handler_b)
        assert id_a != id_b
        scheduler.trigger_event("type_a", {})
        scheduler.trigger_event("type_b", {})
        assert results == ["a", "b"]


class TestSchedulerTriggerEvent:
    def test_trigger_existing_event(self, scheduler: Scheduler) -> None:
        captured: list[dict] = []

        def handler(data: dict) -> None:
            captured.append(data)

        scheduler.register_event("test", handler)
        result = scheduler.trigger_event("test", {"key": "value"})
        assert result is True
        assert captured == [{"key": "value"}]

    def test_trigger_nonexistent_event(self, scheduler: Scheduler) -> None:
        result = scheduler.trigger_event("nonexistent", {})
        assert result is False

    def test_trigger_overwritten_event(self, scheduler: Scheduler) -> None:
        captured: list[str] = []

        def handler1(data: dict) -> None:
            captured.append("old")

        def handler2(data: dict) -> None:
            captured.append("new")

        scheduler.register_event("test", handler1)
        scheduler.register_event("test", handler2)
        scheduler.trigger_event("test", {})
        assert captured == ["new"]


class TestSchedulerStartStop:
    def test_start_sets_running_flag(self, scheduler: Scheduler) -> None:
        assert not scheduler._running
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()

    def test_stop_clears_running_flag(self, scheduler: Scheduler) -> None:
        scheduler.start()
        scheduler.stop()
        assert scheduler._running is False

    def test_start_idempotent(self, scheduler: Scheduler) -> None:
        scheduler.start()
        thread_id = id(scheduler._thread)
        scheduler.start()
        assert id(scheduler._thread) == thread_id
        scheduler.stop()

    def test_stop_when_not_running(self, scheduler: Scheduler) -> None:
        scheduler.stop()
        assert scheduler._thread is None

    def test_start_stop_cycle(self, scheduler: Scheduler) -> None:
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()

    def test_thread_is_daemon(self, scheduler: Scheduler) -> None:
        scheduler.start()
        assert scheduler._thread is not None
        assert scheduler._thread.daemon is True
        scheduler.stop()


class TestSchedulerIntegration:
    def test_get_next_run_on_job(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test", "0 0 * * *", task)
        next_run = scheduler.get_next_run(job_id)
        assert next_run is not None
        assert isinstance(next_run, str)

    def test_get_next_run_nonexistent_job(self, scheduler: Scheduler) -> None:
        result = scheduler.get_next_run("nonexistent")
        assert result is None

    def test_full_lifecycle(self, scheduler: Scheduler) -> None:
        task = Task(name="lifecycle")
        job_id = scheduler.add_cron_job("lifecycle", "30 14 * * *", task)
        assert scheduler.get_job(job_id) is not None
        assert len(scheduler.list_jobs()) == 1
        scheduler.start()
        time.sleep(0.05)
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False
        assert scheduler.remove_job(job_id) is True
        assert scheduler.get_job(job_id) is None
        assert len(scheduler.list_jobs()) == 0

    def test_tick_does_not_fire_unmatched_cron(self, queue: TaskQueue) -> None:
        s = Scheduler(queue, tick_interval=0.1)
        task = Task(name="no-fire")
        s.add_cron_job("no-fire", "0 0 * * *", task)
        s.start()
        time.sleep(0.25)
        s.stop()
        tasks = queue.list_tasks()
        assert len(tasks) == 0
        s.stop()


class TestSchedulerEdgeCases:
    def test_add_job_with_empty_name(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("", "* * * * *", task)
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.name == ""

    def test_add_job_with_high_priority_task(self, scheduler: Scheduler) -> None:
        task = Task(name="critical", priority=TaskPriority.CRITICAL)
        job_id = scheduler.add_cron_job("critical", "* * * * *", task)
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.task_template.priority == TaskPriority.CRITICAL

    def test_register_event_called_with_data(self, scheduler: Scheduler) -> None:
        captured: list[dict] = []

        def handler(data: dict) -> None:
            captured.append(data)

        scheduler.register_event("data_test", handler)
        scheduler.trigger_event("data_test", {"a": 1, "b": [2, 3]})
        assert captured[0] == {"a": 1, "b": [2, 3]}

    def test_remove_job_then_re_add(self, scheduler: Scheduler) -> None:
        task = Task(name="test")
        job_id = scheduler.add_cron_job("test", "* * * * *", task)
        scheduler.remove_job(job_id)
        task2 = Task(name="test2")
        job_id2 = scheduler.add_cron_job("test2", "* * * * *", task2)
        assert job_id2 != job_id
        job = scheduler.get_job(job_id2)
        assert job is not None
        assert job.name == "test2"

    def test_scheduler_with_minimal_tick(self, queue: TaskQueue) -> None:
        s = Scheduler(queue, tick_interval=0.01)
        s.start()
        time.sleep(0.05)
        s.stop()
        assert s._running is False

    def test_disabled_job_does_not_fire(self, queue: TaskQueue) -> None:
        s = Scheduler(queue, tick_interval=0.1)
        task = Task(name="disabled")
        job_id = s.add_cron_job("disabled", "* * * * *", task)
        job = s.get_job(job_id)
        assert job is not None
        job.enabled = False
        s.start()
        time.sleep(0.25)
        s.stop()
        tasks = queue.list_tasks()
        assert len(tasks) == 0
        s.stop()

    def test_cron_job_default_fields(self) -> None:
        job = CronJob()
        assert job.id is not None
        assert job.name == ""
        assert job.cron_expression == ""
        assert job.enabled is True
        assert job.last_run is None
        assert job.next_run is None
        assert job.run_count == 0
        assert job.created_at is not None

    def test_cron_job_with_custom_values(self) -> None:
        task = Task(name="custom")
        job = CronJob(
            name="my-job",
            cron_expression="*/5 * * * *",
            task_template=task,
            enabled=False,
        )
        assert job.name == "my-job"
        assert job.cron_expression == "*/5 * * * *"
        assert job.task_template.name == "custom"
        assert job.enabled is False

    def test_dow_value_7_accepted_as_sunday(self) -> None:
        cron = CronExpression("* * * * 7")
        dt = datetime(2026, 5, 24, 10, 0, 0, tzinfo=timezone.utc)
        assert cron.matches(dt)

    def test_matches_with_seconds_not_zero(self) -> None:
        cron = CronExpression("* * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 45, tzinfo=timezone.utc)
        assert cron.matches(dt)

    def test_next_after_returns_minute_rounded(self) -> None:
        cron = CronExpression("* * * * *")
        dt = datetime(2026, 5, 21, 10, 30, 45, tzinfo=timezone.utc)
        next_dt = cron.next_after(dt)
        assert next_dt.second == 0
        assert next_dt.microsecond == 0
        assert next_dt == datetime(2026, 5, 21, 10, 31, 0, tzinfo=timezone.utc)
