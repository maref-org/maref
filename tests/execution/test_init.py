from __future__ import annotations

from maref.execution import Harness, LoopTask, LoopTaskStatus, ScheduleSpec, ScheduleType


class TestExecutionInit:
    def test_exports_harness(self) -> None:
        assert Harness is not None

    def test_exports_loop_task(self) -> None:
        assert LoopTask is not None

    def test_exports_loop_task_status(self) -> None:
        assert LoopTaskStatus is not None

    def test_exports_schedule_spec(self) -> None:
        assert ScheduleSpec is not None

    def test_exports_schedule_type(self) -> None:
        assert ScheduleType is not None

    def test_all_defined(self) -> None:
        from maref.execution import __all__

        assert "Harness" in __all__
        assert "LoopTask" in __all__
        assert "LoopTaskStatus" in __all__
        assert "ScheduleSpec" in __all__
        assert "ScheduleType" in __all__
