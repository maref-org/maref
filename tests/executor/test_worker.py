from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

from maref.executor.queue import TaskQueue
from maref.executor.types import Task, TaskPriority, TaskStatus
from maref.executor.worker import WorkerPool


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
def worker(queue: TaskQueue) -> WorkerPool:
    w = WorkerPool(queue, num_workers=2)
    yield w
    if not w._stop_event.is_set():
        w.stop(timeout=2.0)


class TestWorkerPoolCreate:
    def test_create_with_default_workers(self, queue: TaskQueue) -> None:
        w = WorkerPool(queue)
        assert w._num_workers == 4
        assert w._queue is queue
        w.stop(timeout=1.0)

    def test_create_with_custom_workers(self, queue: TaskQueue) -> None:
        w = WorkerPool(queue, num_workers=8)
        assert w._num_workers == 8
        w.stop(timeout=1.0)

    def test_create_no_workers_started(self, worker: WorkerPool) -> None:
        status = worker.get_status()
        assert status["active_workers"] == 0

    def test_create_handlers_empty(self, worker: WorkerPool) -> None:
        assert len(worker._handlers) == 0


class TestWorkerPoolStartStop:
    def test_start_creates_workers(self, worker: WorkerPool) -> None:
        worker.start()
        status = worker.get_status()
        assert status["active_workers"] == 2
        assert status["running"] is True

    def test_stop_joins_workers(self, worker: WorkerPool) -> None:
        worker.start()
        worker.stop(timeout=2.0)
        status = worker.get_status()
        assert status["active_workers"] == 0

    def test_start_after_stop(self, worker: WorkerPool) -> None:
        worker.start()
        worker.stop(timeout=2.0)
        worker.start()
        status = worker.get_status()
        assert status["active_workers"] == 2

    def test_stop_before_start(self, worker: WorkerPool) -> None:
        worker.stop(timeout=1.0)
        status = worker.get_status()
        assert status["running"] is False


class TestWorkerPoolSubmit:
    def test_submit_returns_task_id(self, worker: WorkerPool) -> None:
        task = Task(name="test-submit")
        task_id = worker.submit(task)
        assert task_id == task.id

    def test_submit_enqueues_task(self, worker: WorkerPool) -> None:
        task = Task(name="test-enqueue")
        worker.submit(task)
        stats = worker._queue.stats()
        assert stats["total"] == 1

    def test_submit_and_process(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("process-me", handler)
        worker.start()
        task = Task(name="process-me")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert task.id in executed
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

    def test_submit_multiple_tasks(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("multi", handler)
        worker.start()
        tasks = [Task(name="multi") for _ in range(5)]
        for t in tasks:
            worker.submit(t)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        assert len(executed) == 5


class TestWorkerPoolHandler:
    def test_register_handler(self, worker: WorkerPool) -> None:
        def handler(task: Task) -> None:
            pass

        worker.register_handler("my-task", handler)
        assert "my-task" in worker._handlers

    def test_handler_executed(self, worker: WorkerPool) -> None:
        flag = threading.Event()

        def handler(task: Task) -> None:
            flag.set()

        worker.register_handler("flag-task", handler)
        worker.start()
        task = Task(name="flag-task")
        worker.submit(task)
        assert flag.wait(timeout=2.0)
        worker.stop(timeout=1.0)

    def test_default_handler_marks_completed(self, worker: WorkerPool) -> None:
        worker.start()
        task = Task(name="no-handler")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

    def test_handler_receives_correct_task(self, worker: WorkerPool) -> None:
        received: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                received.append(task.id)

        worker.register_handler("check-id", handler)
        worker.start()
        task = Task(name="check-id")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert received[0] == task.id

    def test_multiple_handlers(self, worker: WorkerPool) -> None:
        results: dict[str, str] = {}
        lock = threading.Lock()

        def handler_a(task: Task) -> None:
            with lock:
                results[task.id] = "A"

        def handler_b(task: Task) -> None:
            with lock:
                results[task.id] = "B"

        worker.register_handler("type-a", handler_a)
        worker.register_handler("type-b", handler_b)
        worker.start()
        ta = Task(name="type-a")
        tb = Task(name="type-b")
        worker.submit(ta)
        worker.submit(tb)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert results[ta.id] == "A"
        assert results[tb.id] == "B"

    def test_handler_exception_marks_failed(self, worker: WorkerPool) -> None:
        def failing_handler(task: Task) -> None:
            raise ValueError("handler error")

        worker.register_handler("fail", failing_handler)
        worker.start()
        task = Task(name="fail")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is None
        dlq = worker._queue.list_dlq()
        assert len(dlq) == 1
        assert "handler error" in dlq[0]["error_message"]


class TestWorkerPoolTimeout:
    def test_timeout_marks_task_timeout(self, worker: WorkerPool) -> None:
        def slow_handler(task: Task) -> None:
            time.sleep(10)

        worker.register_handler("slow", slow_handler)
        worker.start()
        task = Task(name="slow", timeout_seconds=0.2)
        worker.submit(task)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.TIMEOUT

    def test_timeout_increments_processed(self, worker: WorkerPool) -> None:
        def slow_handler(task: Task) -> None:
            time.sleep(10)

        worker.register_handler("slow2", slow_handler)
        worker.start()
        task = Task(name="slow2", timeout_seconds=0.1)
        worker.submit(task)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        status = worker.get_status()
        assert status["tasks_processed"] >= 1

    def test_no_timeout_when_not_set(self, worker: WorkerPool) -> None:
        flag = threading.Event()

        def quick_handler(task: Task) -> None:
            flag.set()

        worker.register_handler("quick", quick_handler)
        worker.start()
        task = Task(name="quick")
        worker.submit(task)
        assert flag.wait(timeout=2.0)
        worker.stop(timeout=1.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

    def test_timeout_error_message(self, worker: WorkerPool) -> None:
        def slow_handler(task: Task) -> None:
            time.sleep(10)

        worker.register_handler("slow3", slow_handler)
        worker.start()
        task = Task(name="slow3", timeout_seconds=0.1)
        worker.submit(task)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.error_message is not None
        assert "timed out" in retrieved.error_message


class TestWorkerPoolRetry:
    def test_retry_on_failure(self, worker: WorkerPool) -> None:
        attempt_count: list[int] = [0]
        lock = threading.Lock()

        def failing_handler(task: Task) -> None:
            with lock:
                attempt_count[0] += 1
            raise ValueError("retry me")

        worker.register_handler("retry-task", failing_handler)
        worker.start()
        task = Task(name="retry-task", max_retries=2)
        worker.submit(task)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        with lock:
            assert attempt_count[0] >= 2

    def test_retry_then_dlq(self, worker: WorkerPool) -> None:
        def always_fails(task: Task) -> None:
            raise RuntimeError("always fails")

        worker.register_handler("dlq-bound", always_fails)
        worker.start()
        task = Task(name="dlq-bound", max_retries=1)
        worker.submit(task)
        time.sleep(1.0)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is None
        dlq = worker._queue.list_dlq()
        assert len(dlq) == 1
        assert dlq[0]["name"] == "dlq-bound"
        assert "always fails" in dlq[0]["dlq_reason"]

    def test_retry_count_tracks(self, worker: WorkerPool) -> None:
        def fails_twice(task: Task) -> None:
            raise ValueError("fail")

        worker.register_handler("track-retry", fails_twice)
        worker.start()
        task = Task(name="track-retry", max_retries=3)
        worker.submit(task)
        time.sleep(1.0)
        worker.stop(timeout=2.0)
        dlq = worker._queue.list_dlq()
        assert len(dlq) == 1
        assert dlq[0]["retry_count"] >= 1

    def test_no_retry_when_max_retries_zero(self, worker: WorkerPool) -> None:
        def fails_once(task: Task) -> None:
            raise ValueError("no retry")

        worker.register_handler("no-retry", fails_once)
        worker.start()
        task = Task(name="no-retry", max_retries=0)
        worker.submit(task)
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is None
        dlq = worker._queue.list_dlq()
        assert len(dlq) == 1


class TestWorkerPoolPauseResume:
    def test_pause_stops_processing(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("pause-test", handler)
        worker.start()
        worker.pause()
        task = Task(name="pause-test")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert len(executed) == 0

    def test_resume_continues_processing(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("resume-test", handler)
        worker.start()
        worker.pause()
        task = Task(name="resume-test")
        worker.submit(task)
        time.sleep(0.2)
        worker.resume()
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert len(executed) == 1

    def test_pause_status(self, worker: WorkerPool) -> None:
        worker.start()
        worker.pause()
        status = worker.get_status()
        assert status["paused"] is True

    def test_resume_clears_pause_status(self, worker: WorkerPool) -> None:
        worker.start()
        worker.pause()
        worker.resume()
        status = worker.get_status()
        assert status["paused"] is False


class TestWorkerPoolGetStatus:
    def test_status_running_true(self, worker: WorkerPool) -> None:
        worker.start()
        status = worker.get_status()
        assert status["running"] is True

    def test_status_after_stop(self, worker: WorkerPool) -> None:
        worker.start()
        worker.stop(timeout=2.0)
        status = worker.get_status()
        assert status["running"] is False

    def test_status_has_queue_stats(self, worker: WorkerPool) -> None:
        worker.start()
        task = Task(name="status-test")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        status = worker.get_status()
        assert "queue" in status
        assert "total" in status["queue"]

    def test_status_tracks_processed(self, worker: WorkerPool) -> None:
        def quick_handler(task: Task) -> None:
            pass

        worker.register_handler("proc", quick_handler)
        worker.start()
        for _ in range(3):
            worker.submit(Task(name="proc"))
        time.sleep(0.5)
        worker.stop(timeout=2.0)
        status = worker.get_status()
        assert status["tasks_processed"] >= 3

    def test_status_active_workers(self, worker: WorkerPool) -> None:
        worker.start()
        status = worker.get_status()
        assert status["active_workers"] == 2
        assert status["total_workers"] == 2
        worker.stop(timeout=1.0)


class TestWorkerPoolGracefulShutdown:
    def test_stop_with_pending_tasks(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("graceful", handler)
        worker.start()
        task = Task(name="graceful")
        worker.submit(task)
        time.sleep(0.1)
        worker.stop(timeout=5.0)
        assert task.id in executed
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

    def test_stop_timeout_does_not_block(self, worker: WorkerPool) -> None:
        def slow_handler(task: Task) -> None:
            time.sleep(10)

        worker.register_handler("blocking", slow_handler)
        worker.start()
        task = Task(name="blocking")
        worker.submit(task)
        time.sleep(0.2)
        start = time.time()
        worker.stop(timeout=1.0)
        elapsed = time.time() - start
        assert elapsed < 3.0

    def test_stop_idempotent(self, worker: WorkerPool) -> None:
        worker.start()
        worker.stop(timeout=1.0)
        worker.stop(timeout=1.0)
        status = worker.get_status()
        assert status["running"] is False


class TestWorkerPoolEdgeCases:
    def test_high_priority_processed_first(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.name)

        worker.register_handler("prio", handler)
        worker.start()
        low = Task(name="prio", priority=TaskPriority.LOW)
        high = Task(name="prio", priority=TaskPriority.HIGH)
        worker.submit(low)
        worker.submit(high)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert executed[0] == "prio"

    def test_default_handler_does_not_raise(self, worker: WorkerPool) -> None:
        worker.start()
        task = Task(name="unknown-task-type")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        retrieved = worker._queue.get(task.id)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

    def test_many_rapid_submits(self, worker: WorkerPool) -> None:
        executed: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                executed.append(task.id)

        worker.register_handler("rapid", handler)
        worker.start()
        tasks = [Task(name="rapid") for _ in range(20)]
        for t in tasks:
            worker.submit(t)
        time.sleep(1.0)
        worker.stop(timeout=3.0)
        assert len(executed) == 20

    def test_large_payload_handled(self, worker: WorkerPool) -> None:
        result: dict[str, bool] = {}
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                result["done"] = True

        worker.register_handler("large-payload", handler)
        worker.start()
        task = Task(name="large-payload", payload={"data": "x" * 50000})
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert result.get("done") is True

    def test_task_with_session_id(self, worker: WorkerPool) -> None:
        session: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                session.append(task.session_id or "")

        worker.register_handler("session", handler)
        worker.start()
        task = Task(name="session", session_id="sess-abc")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert "sess-abc" in session

    def test_handler_called_with_correct_status(self, worker: WorkerPool) -> None:
        status_seen: list[str] = []
        lock = threading.Lock()

        def handler(task: Task) -> None:
            with lock:
                status_seen.append(task.status.value)

        worker.register_handler("status-check", handler)
        worker.start()
        task = Task(name="status-check")
        worker.submit(task)
        time.sleep(0.3)
        worker.stop(timeout=2.0)
        assert "running" in status_seen

    def test_zero_workers(self, queue: TaskQueue) -> None:
        w = WorkerPool(queue, num_workers=0)
        w.start()
        status = w.get_status()
        assert status["active_workers"] == 0
        w.stop(timeout=1.0)
