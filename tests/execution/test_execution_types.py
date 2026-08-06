from __future__ import annotations

from maref.execution.types import LoopTask, LoopTaskStatus, ScheduleSpec, ScheduleType


class TestLoopTaskStatus:
    def test_values(self) -> None:
        assert LoopTaskStatus.PENDING.value == "pending"
        assert LoopTaskStatus.RUNNING.value == "running"
        assert LoopTaskStatus.COMPLETED.value == "completed"
        assert LoopTaskStatus.FAILED.value == "failed"
        assert LoopTaskStatus.CANCELLED.value == "cancelled"
        assert LoopTaskStatus.TIMEOUT.value == "timeout"
        assert len(LoopTaskStatus) == 6


class TestScheduleType:
    def test_values(self) -> None:
        assert ScheduleType.IMMEDIATE.value == "immediate"
        assert ScheduleType.DELAYED.value == "delayed"
        assert ScheduleType.CRON.value == "cron"
        assert ScheduleType.INTERVAL.value == "interval"
        assert len(ScheduleType) == 4


class TestScheduleSpec:
    def test_defaults(self) -> None:
        spec = ScheduleSpec()
        assert spec.type == ScheduleType.IMMEDIATE
        assert spec.delay_seconds == 0.0
        assert spec.cron_expression == ""
        assert spec.interval_seconds == 0.0
        assert spec.max_runs == 0

    def test_to_dict(self) -> None:
        spec = ScheduleSpec(
            type=ScheduleType.CRON,
            cron_expression="0 6 * * *",
            max_runs=10,
        )
        d = spec.to_dict()
        assert d["type"] == "cron"
        assert d["cron_expression"] == "0 6 * * *"
        assert d["max_runs"] == 10
        assert d["delay_seconds"] == 0.0

    def test_custom_values(self) -> None:
        spec = ScheduleSpec(
            type=ScheduleType.DELAYED,
            delay_seconds=30.0,
            max_runs=5,
        )
        assert spec.type == ScheduleType.DELAYED
        assert spec.delay_seconds == 30.0
        assert spec.max_runs == 5


class TestLoopTask:
    def test_defaults(self) -> None:
        task = LoopTask()
        assert task.id is not None
        assert len(task.id) == 12
        assert task.name == ""
        assert task.loop_type == ""
        assert task.status == LoopTaskStatus.PENDING
        assert task.rounds_completed == 0
        assert task.error is None

    def test_custom_values(self) -> None:
        task = LoopTask(
            id="abc123",
            name="test-loop",
            loop_type="FeedbackLoop",
            status=LoopTaskStatus.RUNNING,
            input_preview="some input",
            rounds_completed=3,
            stop_reason="max_rounds",
        )
        assert task.id == "abc123"
        assert task.name == "test-loop"
        assert task.loop_type == "FeedbackLoop"
        assert task.status == LoopTaskStatus.RUNNING
        assert task.rounds_completed == 3
        assert task.stop_reason == "max_rounds"

    def test_to_dict(self) -> None:
        task = LoopTask(
            id="t1",
            name="my-task",
            status=LoopTaskStatus.COMPLETED,
            rounds_completed=5,
            stop_reason="converged",
            error=None,
        )
        d = task.to_dict()
        assert d["id"] == "t1"
        assert d["name"] == "my-task"
        assert d["status"] == "completed"
        assert d["rounds_completed"] == 5
        assert d["stop_reason"] == "converged"
        assert d["error"] is None

    def test_to_dict_truncates_input(self) -> None:
        long_input = "x" * 200
        task = LoopTask(input_preview=long_input)
        d = task.to_dict()
        assert len(d["input_preview"]) <= 100

    def test_auto_id(self) -> None:
        task1 = LoopTask()
        task2 = LoopTask()
        assert task1.id != task2.id

    def test_timestamps(self) -> None:
        import time

        task = LoopTask()
        assert task.created_at > 0
        assert task.started_at is None
        assert task.completed_at is None
