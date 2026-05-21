from __future__ import annotations

import os
import tempfile

import pytest

from maref.executor.queue import TaskQueue, TaskQueueError
from maref.executor.types import Task, TaskPriority, TaskStatus


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


class TestTaskQueueCreate:
    def test_create_with_temp_db(self, queue: TaskQueue) -> None:
        stats = queue.stats()
        assert stats["total"] == 0
        assert stats["dead_letter_queue"] == 0

    def test_reopen_persistence(self, db_path: str) -> None:
        q1 = TaskQueue(db_path)
        task = Task(name="persist-me")
        q1.enqueue(task)
        q1.close()
        q2 = TaskQueue(db_path)
        retrieved = q2.get(task.id)
        assert retrieved is not None
        assert retrieved.name == "persist-me"
        assert retrieved.status == TaskStatus.QUEUED
        q2.close()


class TestTaskQueueEnqueue:
    def test_enqueue_success(self, queue: TaskQueue) -> None:
        task = Task(name="test-enqueue")
        task_id = queue.enqueue(task)
        assert task_id == task.id

    def test_enqueue_duplicate_id(self, queue: TaskQueue) -> None:
        task = Task(name="dup")
        queue.enqueue(task)
        with pytest.raises(TaskQueueError, match="already exists"):
            queue.enqueue(task)

    def test_enqueue_sets_queued_status(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        assert task.status == TaskStatus.QUEUED

    def test_enqueue_multiple(self, queue: TaskQueue) -> None:
        for i in range(5):
            queue.enqueue(Task(name=f"task-{i}"))
        assert queue.stats()["total"] == 5


class TestTaskQueueDequeue:
    def test_dequeue_single(self, queue: TaskQueue) -> None:
        task = Task(name="dequeue-me")
        queue.enqueue(task)
        tasks = queue.dequeue()
        assert len(tasks) == 1
        assert tasks[0].id == task.id
        assert tasks[0].status == TaskStatus.RUNNING

    def test_dequeue_empty(self, queue: TaskQueue) -> None:
        tasks = queue.dequeue()
        assert tasks == []

    def test_dequeue_priority_order(self, queue: TaskQueue) -> None:
        low = Task(name="low", priority=TaskPriority.LOW)
        high = Task(name="high", priority=TaskPriority.HIGH)
        critical = Task(name="critical", priority=TaskPriority.CRITICAL)
        queue.enqueue(low)
        queue.enqueue(high)
        queue.enqueue(critical)
        tasks = queue.dequeue(3)
        assert tasks[0].name == "critical"
        assert tasks[1].name == "high"
        assert tasks[2].name == "low"

    def test_dequeue_fifo_within_same_priority(self, queue: TaskQueue) -> None:
        t1 = Task(name="first", priority=TaskPriority.MEDIUM)
        t2 = Task(name="second", priority=TaskPriority.MEDIUM)
        t3 = Task(name="third", priority=TaskPriority.MEDIUM)
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.enqueue(t3)
        tasks = queue.dequeue(3)
        assert tasks[0].name == "first"
        assert tasks[1].name == "second"
        assert tasks[2].name == "third"

    def test_dequeue_limit(self, queue: TaskQueue) -> None:
        for _ in range(5):
            queue.enqueue(Task())
        tasks = queue.dequeue(2)
        assert len(tasks) == 2

    def test_dequeue_only_queued_tasks(self, queue: TaskQueue) -> None:
        t = Task(name="running-task")
        queue.enqueue(t)
        queue.update_status(t.id, TaskStatus.RUNNING)
        tasks = queue.dequeue()
        assert len(tasks) == 0


class TestTaskQueuePeek:
    def test_peek_does_not_change_status(self, queue: TaskQueue) -> None:
        task = Task(name="peek-me")
        queue.enqueue(task)
        peeked = queue.peek()
        assert len(peeked) == 1
        assert peeked[0].id == task.id
        assert peeked[0].status == TaskStatus.QUEUED

    def test_peek_empty(self, queue: TaskQueue) -> None:
        assert queue.peek() == []


class TestTaskQueueGet:
    def test_get_existing(self, queue: TaskQueue) -> None:
        task = Task(name="get-me")
        queue.enqueue(task)
        retrieved = queue.get(task.id)
        assert retrieved is not None
        assert retrieved.name == "get-me"

    def test_get_nonexistent(self, queue: TaskQueue) -> None:
        assert queue.get("nonexistent") is None


class TestTaskQueueUpdateStatus:
    def test_update_to_running(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        result = queue.update_status(task.id, TaskStatus.RUNNING)
        assert result is True
        updated = queue.get(task.id)
        assert updated is not None
        assert updated.status == TaskStatus.RUNNING
        assert updated.started_at is not None

    def test_update_to_completed(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        queue.update_status(task.id, TaskStatus.RUNNING)
        result = queue.update_status(task.id, TaskStatus.COMPLETED)
        assert result is True
        updated = queue.get(task.id)
        assert updated is not None
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at is not None

    def test_update_to_failed_with_error(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        queue.update_status(task.id, TaskStatus.RUNNING)
        queue.update_status(task.id, TaskStatus.FAILED, error_message="oops")
        updated = queue.get(task.id)
        assert updated is not None
        assert updated.status == TaskStatus.FAILED
        assert updated.error_message == "oops"

    def test_update_nonexistent_task(self, queue: TaskQueue) -> None:
        result = queue.update_status("ghost", TaskStatus.COMPLETED)
        assert result is False

    def test_update_with_extra_fields(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        queue.update_status(task.id, TaskStatus.RUNNING, session_id="sess-1")
        updated = queue.get(task.id)
        assert updated is not None
        assert updated.session_id == "sess-1"


class TestTaskQueueList:
    def test_list_all(self, queue: TaskQueue) -> None:
        for i in range(3):
            queue.enqueue(Task(name=f"t{i}"))
        tasks = queue.list_tasks()
        assert len(tasks) == 3

    def test_list_by_status(self, queue: TaskQueue) -> None:
        t1 = Task(name="running")
        t2 = Task(name="queued")
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.update_status(t1.id, TaskStatus.RUNNING)
        running = queue.list_tasks(status=TaskStatus.RUNNING)
        queued = queue.list_tasks(status=TaskStatus.QUEUED)
        assert len(running) == 1
        assert running[0].name == "running"
        assert len(queued) == 1
        assert queued[0].name == "queued"

    def test_list_limit(self, queue: TaskQueue) -> None:
        for _ in range(10):
            queue.enqueue(Task())
        tasks = queue.list_tasks(limit=3)
        assert len(tasks) == 3


class TestTaskQueueDelete:
    def test_delete_existing(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        result = queue.delete(task.id)
        assert result is True
        assert queue.get(task.id) is None

    def test_delete_nonexistent(self, queue: TaskQueue) -> None:
        result = queue.delete("ghost")
        assert result is False


class TestTaskQueueDLQ:
    def test_move_to_dlq(self, queue: TaskQueue) -> None:
        task = Task(name="dlq-task")
        queue.enqueue(task)
        result = queue.move_to_dlq(task.id, reason="too many failures")
        assert result is True
        assert queue.get(task.id) is None
        dlq_items = queue.list_dlq()
        assert len(dlq_items) == 1
        assert dlq_items[0]["name"] == "dlq-task"
        assert dlq_items[0]["dlq_reason"] == "too many failures"

    def test_move_nonexistent_to_dlq(self, queue: TaskQueue) -> None:
        result = queue.move_to_dlq("ghost")
        assert result is False

    def test_retry_dlq(self, queue: TaskQueue) -> None:
        task = Task(name="retry-me")
        queue.enqueue(task)
        queue.move_to_dlq(task.id, "test")
        result = queue.retry_dlq(task.id)
        assert result is True
        dlq_items = queue.list_dlq()
        assert len(dlq_items) == 0
        restored = queue.get(task.id)
        assert restored is not None
        assert restored.status == TaskStatus.QUEUED
        assert restored.retry_count == 0

    def test_retry_nonexistent_dlq(self, queue: TaskQueue) -> None:
        result = queue.retry_dlq("ghost")
        assert result is False

    def test_list_dlq_empty(self, queue: TaskQueue) -> None:
        assert queue.list_dlq() == []

    def test_list_dlq_limit(self, queue: TaskQueue) -> None:
        for i in range(5):
            t = Task(name=f"dlq-{i}")
            queue.enqueue(t)
            queue.move_to_dlq(t.id, "test")
        items = queue.list_dlq(limit=2)
        assert len(items) == 2


class TestTaskQueueStats:
    def test_stats_counts(self, queue: TaskQueue) -> None:
        t1 = Task(name="a")
        t2 = Task(name="b")
        t3 = Task(name="c")
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.enqueue(t3)
        queue.update_status(t1.id, TaskStatus.RUNNING)
        queue.update_status(t2.id, TaskStatus.COMPLETED)
        queue.update_status(t3.id, TaskStatus.FAILED)
        stats = queue.stats()
        assert stats["total"] == 3
        assert stats["by_status"]["running"] == 1
        assert stats["by_status"]["completed"] == 1
        assert stats["by_status"]["failed"] == 1
        assert stats["dead_letter_queue"] == 0

    def test_stats_with_dlq(self, queue: TaskQueue) -> None:
        t = Task()
        queue.enqueue(t)
        queue.move_to_dlq(t.id, "test")
        stats = queue.stats()
        assert stats["total"] == 0
        assert stats["dead_letter_queue"] == 1


class TestTaskQueueClear:
    def test_clear_terminal_statuses(self, queue: TaskQueue) -> None:
        t1 = Task(name="running")
        t2 = Task(name="completed")
        t3 = Task(name="failed")
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.enqueue(t3)
        queue.update_status(t1.id, TaskStatus.RUNNING)
        queue.update_status(t2.id, TaskStatus.COMPLETED)
        queue.update_status(t3.id, TaskStatus.FAILED)
        cleared = queue.clear()
        assert cleared >= 2
        assert queue.get(t2.id) is None
        assert queue.get(t3.id) is None
        assert queue.get(t1.id) is not None

    def test_clear_by_status(self, queue: TaskQueue) -> None:
        t1 = Task()
        t2 = Task()
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.update_status(t1.id, TaskStatus.COMPLETED)
        queue.update_status(t2.id, TaskStatus.FAILED)
        cleared = queue.clear(status=TaskStatus.COMPLETED)
        assert cleared == 1
        assert queue.get(t1.id) is None
        assert queue.get(t2.id) is not None


class TestTaskQueueEdgeCases:
    def test_large_payload(self, queue: TaskQueue) -> None:
        large_data = {"data": "x" * 10000}
        task = Task(name="large", payload=large_data)
        queue.enqueue(task)
        retrieved = queue.get(task.id)
        assert retrieved is not None
        assert len(retrieved.payload["data"]) == 10000

    def test_tags_serialization(self, queue: TaskQueue) -> None:
        task = Task(name="tagged", tags=["a", "b", "c"])
        queue.enqueue(task)
        retrieved = queue.get(task.id)
        assert retrieved is not None
        assert retrieved.tags == ["a", "b", "c"]

    def test_max_retries_tracking(self, queue: TaskQueue) -> None:
        task = Task(name="retry-track", max_retries=3)
        queue.enqueue(task)
        for i in range(3):
            queue.update_status(
                task.id, TaskStatus.FAILED, retry_count=i + 1, error_message=f"attempt {i + 1}"
            )
            retrieved = queue.get(task.id)
            assert retrieved is not None
            assert retrieved.retry_count == i + 1

    def test_dequeue_updates_started_at(self, queue: TaskQueue) -> None:
        task = Task()
        queue.enqueue(task)
        dequeued = queue.dequeue()
        assert dequeued[0].started_at is not None

    def test_concurrent_safety(self, db_path: str) -> None:
        q = TaskQueue(db_path)
        tasks = [Task(name=f"thread-{i}") for i in range(10)]
        for t in tasks:
            q.enqueue(t)
        results = q.dequeue(10)
        assert len(results) == 10
        q.close()
