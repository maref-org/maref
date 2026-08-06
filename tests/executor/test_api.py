from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.executor.api import create_task_router
from maref.executor.queue import TaskQueue
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


@pytest.fixture
def client(queue: TaskQueue) -> TestClient:
    app = FastAPI()
    router = create_task_router(queue)
    app.include_router(router)
    return TestClient(app)


class TestCreateTask:
    def test_create_task_success(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={
                "name": "test-task",
                "description": "A test task",
                "priority": 2,
                "payload": {"key": "value"},
                "tags": ["test", "api"],
                "session_id": "session-123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        assert "created_at" in data

    def test_create_task_defaults(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "minimal-task"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        assert "created_at" in data

    def test_create_task_invalid_priority(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "bad-priority", "priority": 5},
        )
        assert response.status_code == 422

    def test_create_task_negative_priority(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "neg-priority", "priority": -1},
        )
        assert response.status_code == 422


class TestGetTask:
    def test_get_task_success(self, client: TestClient, queue: TaskQueue) -> None:
        task = Task(
            name="fetch-me",
            description="Task to fetch",
            priority=TaskPriority.HIGH,
        )
        task_id = queue.enqueue(task)

        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["name"] == "fetch-me"
        assert data["description"] == "Task to fetch"
        assert data["priority"] == 2
        assert data["status"] == "queued"
        assert data["tags"] == []

    def test_get_task_not_found(self, client: TestClient) -> None:
        response = client.get("/api/v1/tasks/nonexistent-id")
        assert response.status_code == 404
        assert "detail" in response.json()


class TestCancelTask:
    def test_cancel_task_success(self, client: TestClient, queue: TaskQueue) -> None:
        task = Task(name="cancel-me")
        task_id = queue.enqueue(task)

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "cancelled"

        cancelled = queue.get(task_id)
        assert cancelled is not None
        assert cancelled.status == TaskStatus.CANCELLED

    def test_cancel_completed_task(self, client: TestClient, queue: TaskQueue) -> None:
        task = Task(name="already-done")
        task_id = queue.enqueue(task)
        queue.update_status(task_id, TaskStatus.COMPLETED)

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 409

    def test_cancel_failed_task(self, client: TestClient, queue: TaskQueue) -> None:
        task = Task(name="already-failed")
        task_id = queue.enqueue(task)
        queue.update_status(task_id, TaskStatus.FAILED)

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 409

    def test_cancel_not_found(self, client: TestClient) -> None:
        response = client.post("/api/v1/tasks/nonexistent-id/cancel")
        assert response.status_code == 404


class TestListTasks:
    def test_list_tasks_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
        assert data["total"] == 0

    def test_list_tasks_all(self, client: TestClient, queue: TaskQueue) -> None:
        for i in range(3):
            task = Task(name=f"task-{i}")
            queue.enqueue(task)

        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 3
        assert data["total"] == 3

    def test_list_tasks_filter_by_status(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(name="queued-one")
        queue.enqueue(t1)
        t2 = Task(name="queued-two")
        queue.enqueue(t2)
        t3 = Task(name="to-cancel")
        t3_id = queue.enqueue(t3)
        queue.update_status(t3_id, TaskStatus.CANCELLED)

        response = client.get("/api/v1/tasks?status=queued")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2
        assert data["total"] == 2

        response = client.get("/api/v1/tasks?status=cancelled")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1

    def test_list_tasks_filter_by_priority(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(name="low", priority=TaskPriority.LOW)
        queue.enqueue(t1)
        t2 = Task(name="medium", priority=TaskPriority.MEDIUM)
        queue.enqueue(t2)
        t3 = Task(name="high", priority=TaskPriority.HIGH)
        queue.enqueue(t3)

        response = client.get("/api/v1/tasks?priority=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1
        assert data["tasks"][0]["name"] == "medium"

        response = client.get("/api/v1/tasks?priority=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1
        assert data["tasks"][0]["name"] == "low"

    def test_list_tasks_filter_by_session_id(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(name="session-a", session_id="session-A")
        queue.enqueue(t1)
        t2 = Task(name="session-b", session_id="session-B")
        queue.enqueue(t2)

        response = client.get("/api/v1/tasks?session_id=session-A")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1
        assert data["tasks"][0]["name"] == "session-a"

    def test_list_tasks_filter_by_tag(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(name="tagged-one", tags=["urgent", "backend"])
        queue.enqueue(t1)
        t2 = Task(name="tagged-two", tags=["backend"])
        queue.enqueue(t2)
        t3 = Task(name="no-tags")
        queue.enqueue(t3)

        response = client.get("/api/v1/tasks?tag=urgent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1
        assert data["tasks"][0]["name"] == "tagged-one"

    def test_list_tasks_pagination(self, client: TestClient, queue: TaskQueue) -> None:
        for i in range(10):
            task = Task(name=f"paged-{i}")
            queue.enqueue(task)

        response = client.get("/api/v1/tasks?limit=3&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 3
        assert data["total"] == 10

        response = client.get("/api/v1/tasks?limit=3&offset=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 3
        assert data["total"] == 10

        response = client.get("/api/v1/tasks?limit=1000&offset=0")
        assert response.status_code == 200

    def test_list_tasks_max_limit(self, client: TestClient, queue: TaskQueue) -> None:
        for i in range(1500):
            task = Task(name=f"bulk-{i}")
            queue.enqueue(task)

        response = client.get("/api/v1/tasks?limit=2000")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1000
        assert data["total"] == 1500

    def test_list_tasks_combined_filters(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(
            name="urgent-high",
            priority=TaskPriority.HIGH,
            tags=["urgent"],
            session_id="sess-1",
        )
        queue.enqueue(t1)
        t2 = Task(
            name="normal-medium",
            priority=TaskPriority.MEDIUM,
            tags=["normal"],
            session_id="sess-1",
        )
        queue.enqueue(t2)
        t3 = Task(
            name="urgent-medium",
            priority=TaskPriority.MEDIUM,
            tags=["urgent"],
            session_id="sess-2",
        )
        queue.enqueue(t3)

        response = client.get("/api/v1/tasks?tag=urgent&session_id=sess-1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["total"] == 1
        assert data["tasks"][0]["name"] == "urgent-high"
