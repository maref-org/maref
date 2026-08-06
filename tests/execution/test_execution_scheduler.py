from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.execution.scheduler import Harness
from maref.execution.types import LoopTask, LoopTaskStatus
from maref.loop.base import LoopBase
from maref.loop.bridge import LoopGovernanceBridge


@pytest.fixture
def mock_loop() -> MagicMock:
    loop = MagicMock(spec=LoopBase)
    type(loop).__name__ = "MockLoop"
    return loop


@pytest.fixture
def mock_bridge() -> AsyncMock:
    bridge = AsyncMock(spec=LoopGovernanceBridge)
    result = MagicMock()
    result.rounds_completed = 5
    result.stop_reason = MagicMock()
    result.stop_reason.value = "max_rounds"
    bridge.run_governed.return_value = result
    return bridge


@pytest.fixture
def harness(mock_bridge: AsyncMock) -> Harness:
    return Harness(max_concurrent=2, bridge=mock_bridge)


class TestHarness:
    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self, harness: Harness, mock_loop: MagicMock) -> None:
        task_id = await harness.submit(mock_loop, {"key": "value"}, name="test-task")
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    @pytest.mark.asyncio
    async def test_submit_stores_task(self, harness: Harness, mock_loop: MagicMock) -> None:
        task_id = await harness.submit(mock_loop, {"key": "value"}, name="test-task")
        task = harness.get_status(task_id)
        assert task is not None
        assert task.name == "test-task"
        assert task.loop_type == "MockLoop"
        assert task.status == LoopTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_submit_default_name(self, harness: Harness, mock_loop: MagicMock) -> None:
        task_id = await harness.submit(mock_loop, {"key": "value"})
        task = harness.get_status(task_id)
        assert task is not None
        assert task.name.startswith("MockLoop-")
        assert task_id[:8] in task.name

    @pytest.mark.asyncio
    async def test_submit_and_run_completes(
        self, harness: Harness, mock_loop: MagicMock, mock_bridge: AsyncMock
    ) -> None:
        task_id = await harness.submit(mock_loop, {"key": "value"}, name="test-task")
        await harness.wait_all()
        task = harness.get_status(task_id)
        assert task is not None
        assert task.status == LoopTaskStatus.COMPLETED
        assert task.rounds_completed == 5
        assert task.stop_reason == "max_rounds"

    @pytest.mark.asyncio
    async def test_cancel_pending_task(
        self, harness: Harness, mock_loop: MagicMock
    ) -> None:
        task_id = await harness.submit(mock_loop, {"key": "value"}, name="to-cancel")
        cancelled = await harness.cancel(task_id)
        assert cancelled
        task = harness.get_status(task_id)
        assert task is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, harness: Harness) -> None:
        cancelled = await harness.cancel("nonexistent")
        assert not cancelled

    @pytest.mark.asyncio
    async def test_cancel_all(self, harness: Harness, mock_loop: MagicMock) -> None:
        await harness.submit(mock_loop, {"k": "v"}, name="t1")
        await harness.submit(mock_loop, {"k": "v"}, name="t2")
        count = await harness.cancel_all()
        assert count >= 0

    @pytest.mark.asyncio
    async def test_get_status_nonexistent(self, harness: Harness) -> None:
        assert harness.get_status("nope") is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, harness: Harness, mock_loop: MagicMock) -> None:
        await harness.submit(mock_loop, {"k": "v"}, name="t1")
        await harness.submit(mock_loop, {"k": "v"}, name="t2")
        tasks = harness.list_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(
        self, harness: Harness, mock_loop: MagicMock
    ) -> None:
        await harness.submit(mock_loop, {"k": "v"}, name="t1")
        pending = harness.list_tasks(LoopTaskStatus.PENDING)
        assert len(pending) >= 1
        running = harness.list_tasks(LoopTaskStatus.RUNNING)
        assert len(running) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, harness: Harness, mock_loop: MagicMock) -> None:
        await harness.submit(mock_loop, {"k": "v"}, name="t1")
        stats = harness.get_stats()
        assert stats["max_concurrent"] == 2
        assert stats["total_submitted"] == 1
        assert stats["pending"] == 1

    @pytest.mark.asyncio
    async def test_get_stats_after_completion(
        self, harness: Harness, mock_loop: MagicMock, mock_bridge: AsyncMock
    ) -> None:
        await harness.submit(mock_loop, {"k": "v"}, name="t1")
        await harness.wait_all()
        stats = harness.get_stats()
        assert stats["completed"] == 1

    @pytest.mark.asyncio
    async def test_run_governed_failure(
        self, harness: Harness, mock_loop: MagicMock, mock_bridge: AsyncMock
    ) -> None:
        mock_bridge.run_governed.side_effect = RuntimeError("execution failed")
        task_id = await harness.submit(mock_loop, {"k": "v"}, name="fail-task")
        await harness.wait_all()
        task = harness.get_status(task_id)
        assert task is not None
        assert task.status == LoopTaskStatus.FAILED
        assert "execution failed" in (task.error or "")

    @pytest.mark.asyncio
    async def test_max_concurrent_property(self) -> None:
        h = Harness(max_concurrent=10)
        assert h.max_concurrent == 10

    @pytest.mark.asyncio
    async def test_default_bridge(self) -> None:
        harness = Harness()
        assert harness._bridge is not None
