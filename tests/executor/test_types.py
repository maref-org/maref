from __future__ import annotations

import json

from maref.executor.types import Task, TaskPriority, TaskResult, TaskStatus


class TestTaskPriority:
    def test_int_values(self) -> None:
        assert TaskPriority.LOW.value == 0
        assert TaskPriority.MEDIUM.value == 1
        assert TaskPriority.HIGH.value == 2
        assert TaskPriority.CRITICAL.value == 3

    def test_ordering(self) -> None:
        assert TaskPriority.LOW < TaskPriority.MEDIUM < TaskPriority.HIGH < TaskPriority.CRITICAL


class TestTaskStatus:
    def test_values(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.TIMEOUT.value == "timeout"


class TestTaskResult:
    def test_values(self) -> None:
        assert TaskResult.SUCCESS.value == "success"
        assert TaskResult.FAILURE.value == "failure"
        assert TaskResult.TIMEOUT.value == "timeout"
        assert TaskResult.CANCELLED.value == "cancelled"
        assert TaskResult.SKIPPED.value == "skipped"


class TestTask:
    def test_default_creation(self) -> None:
        task = Task()
        assert task.id is not None
        assert task.name == ""
        assert task.priority == TaskPriority.MEDIUM
        assert task.status == TaskStatus.PENDING
        assert task.payload == {}
        assert task.metadata == {}
        assert task.tags == []
        assert task.max_retries == 0
        assert task.retry_count == 0
        assert task.started_at is None
        assert task.completed_at is None
        assert task.error_message is None
        assert task.session_id is None

    def test_to_dict(self) -> None:
        task = Task(
            name="test-task",
            description="A test task",
            priority=TaskPriority.HIGH,
            payload={"cmd": "echo hello"},
            tags=["urgent", "test"],
            timeout_seconds=30.0,
            max_retries=3,
        )
        d = task.to_dict()
        assert d["name"] == "test-task"
        assert d["description"] == "A test task"
        assert d["priority"] == 2
        assert d["status"] == "pending"
        assert d["payload"] == {"cmd": "echo hello"}
        assert d["tags"] == ["urgent", "test"]
        assert d["timeout_seconds"] == 30.0
        assert d["max_retries"] == 3
        assert d["started_at"] is None
        assert d["completed_at"] is None

    def test_from_dict_roundtrip(self) -> None:
        original = Task(
            name="roundtrip",
            priority=TaskPriority.CRITICAL,
            payload={"key": "value"},
            metadata={"source": "test"},
            tags=["a", "b"],
            max_retries=2,
            timeout_seconds=60.0,
        )
        d = original.to_dict()
        restored = Task.from_dict(d)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.priority == original.priority
        assert restored.status == original.status
        assert restored.payload == original.payload
        assert restored.metadata == original.metadata
        assert restored.tags == original.tags
        assert restored.max_retries == original.max_retries
        assert restored.timeout_seconds == original.timeout_seconds

    def test_from_dict_minimal(self) -> None:
        task = Task.from_dict({"name": "minimal"})
        assert task.name == "minimal"
        assert task.priority == TaskPriority.MEDIUM
        assert task.status == TaskStatus.PENDING
        assert task.payload == {}

    def test_serialization_json_compatible(self) -> None:
        task = Task(name="json-safe", payload={"nested": {"list": [1, 2, 3]}})
        d = task.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)
        restored = Task.from_dict(loaded)
        assert restored.name == "json-safe"
        assert restored.payload == {"nested": {"list": [1, 2, 3]}}

    def test_id_is_unique(self) -> None:
        t1 = Task()
        t2 = Task()
        assert t1.id != t2.id

    def test_status_transition_running_sets_started(self) -> None:
        task = Task()
        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING

    def test_session_id(self) -> None:
        task = Task(session_id="sess-123")
        assert task.session_id == "sess-123"

    def test_error_message(self) -> None:
        task = Task(error_message="Something went wrong")
        assert task.error_message == "Something went wrong"
