from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.executor.api import create_task_router
from maref.executor.notifications import NotificationChannel, NotificationManager
from maref.executor.queue import TaskQueue
from maref.executor.types import Task, TaskPriority, TaskStatus
from maref.integration.mcp_client import ConnectionState, MCPClient, MCPConnection
from maref.integration.mcp_governance import MCPDecisionVerdict, MCPGovernance
from maref.integration.mcp_transport import JSONRPCResponse, MCPTransport, TransportState


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


class TestE2ETaskLifecycle:
    """E2E-1: Task Lifecycle - full create -> get -> update -> verify cycle"""

    def test_full_lifecycle(self, client: TestClient, queue: TaskQueue) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={
                "name": "lifecycle-task",
                "description": "E2E lifecycle test",
                "priority": 2,
            },
        )
        assert response.status_code == 201
        create_data = response.json()
        task_id = create_data["task_id"]
        assert create_data["status"] == "queued"
        assert "created_at" in create_data

        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "lifecycle-task"
        assert data["description"] == "E2E lifecycle test"
        assert data["priority"] == 2

        result = queue.update_status(task_id, TaskStatus.RUNNING)
        assert result is True
        result = queue.update_status(task_id, TaskStatus.COMPLETED)
        assert result is True

        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"


class TestE2ETaskCancel:
    """E2E-2: Task Cancel Flow - create -> cancel -> verify"""

    def test_cancel_flow(self, client: TestClient, queue: TaskQueue) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "cancel-test", "priority": 1},
        )
        assert response.status_code == 201
        task_id = response.json()["task_id"]

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 200
        cancel_data = response.json()
        assert cancel_data["task_id"] == task_id
        assert cancel_data["status"] == "cancelled"

        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"


class TestE2ETaskListFilters:
    """E2E-3: Task List with Filters"""

    def test_list_with_filters(self, client: TestClient, queue: TaskQueue) -> None:
        t1 = Task(name="queued-low", priority=TaskPriority.LOW)
        t2 = Task(name="queued-medium", priority=TaskPriority.MEDIUM)
        t3 = Task(name="queued-high", priority=TaskPriority.HIGH)
        t4 = Task(name="running-task", priority=TaskPriority.MEDIUM)
        t5 = Task(name="completed-task", priority=TaskPriority.HIGH)

        ids = [
            queue.enqueue(t1),
            queue.enqueue(t2),
            queue.enqueue(t3),
            queue.enqueue(t4),
            queue.enqueue(t5),
        ]
        queue.update_status(ids[3], TaskStatus.RUNNING)
        queue.update_status(ids[4], TaskStatus.COMPLETED)

        response = client.get("/api/v1/tasks?status=queued")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 3
        assert data["total"] == 3

        response = client.get("/api/v1/tasks?priority=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2
        assert data["total"] == 2

        response = client.get("/api/v1/tasks?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2
        assert data["total"] == 5


class TestE2EErrorHandling:
    """E2E-4: Error Handling"""

    def test_get_nonexistent_task(self, client: TestClient) -> None:
        response = client.get("/api/v1/tasks/nonexistent")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_create_with_invalid_priority(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "bad-priority", "priority": 5},
        )
        assert response.status_code == 422

    def test_cancel_completed_task(self, client: TestClient, queue: TaskQueue) -> None:
        task = Task(name="already-done")
        task_id = queue.enqueue(task)
        queue.update_status(task_id, TaskStatus.COMPLETED)

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 409


class TestE2ENotificationIntegration:
    """E2E-5: Notification Integration with mock channel"""

    def test_notification_on_task_completion(self, client: TestClient, queue: TaskQueue) -> None:
        mock_channel = MagicMock(spec=NotificationChannel)
        mock_channel.send.return_value = True

        notifier = NotificationManager()
        notifier.register_channel("mock", mock_channel)

        response = client.post(
            "/api/v1/tasks",
            json={"name": "notify-task", "priority": 2},
        )
        assert response.status_code == 201
        task_id = response.json()["task_id"]

        queue.update_status(task_id, TaskStatus.COMPLETED)
        task = queue.get(task_id)
        assert task is not None

        results = notifier.notify_all(
            title="Task Completed",
            message=f"Task {task_id} completed successfully",
        )

        mock_channel.send.assert_called_once()
        assert results["mock"] is True


class TestE2EConcurrentOperations:
    """E2E-6: Concurrent Task Operations"""

    def test_concurrent_operations(self, client: TestClient, queue: TaskQueue) -> None:
        task_ids = []
        for i in range(10):
            response = client.post(
                "/api/v1/tasks",
                json={"name": f"concurrent-{i}", "priority": 1},
            )
            assert response.status_code == 201
            task_ids.append(response.json()["task_id"])

        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 10
        assert data["total"] == 10

        cancelled_ids = task_ids[3:6]
        for tid in cancelled_ids:
            response = client.post(f"/api/v1/tasks/{tid}/cancel")
            assert response.status_code == 200

        response = client.get("/api/v1/tasks?status=cancelled")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 3
        assert data["total"] == 3

        response = client.get("/api/v1/tasks?status=queued")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 7
        assert data["total"] == 7


class TestE2EMetadataSource:
    """E2E-7: Metadata Source Tracking"""

    def test_metadata_source_tracking(self, client: TestClient, queue: TaskQueue) -> None:
        response = client.post(
            "/api/v1/tasks",
            json={"name": "source-task", "priority": 2},
        )
        assert response.status_code == 201
        task_id = response.json()["task_id"]

        task = queue.get(task_id)
        assert task is not None
        assert "source" in task.metadata
        assert task.metadata["source"] == "testclient"


class TestE2EMCPGovernanceIntegration:
    """E2E-MCP: MCP → Governance integration tests

    Tests the full MCPClient.call_tool() → MCPGovernance.evaluate() pipeline
    using mock transport to verify governance decisions are correctly enforced.
    """

    @pytest.fixture
    def mock_transport(self) -> MagicMock:
        transport = MagicMock(spec=MCPTransport)
        transport.send_tool_call.return_value = JSONRPCResponse(
            result={"status": "ok"},
            id="3",
        )
        transport.state = TransportState.CONNECTED
        return transport

    @pytest.fixture
    def mcp_governance(self) -> MCPGovernance:
        return MCPGovernance()

    @pytest.fixture
    def mcp_client(self) -> MCPClient:
        return MCPClient()

    def _connect(
        self,
        client: MCPClient,
        transport: MagicMock,
    ) -> MCPConnection:
        conn = MCPConnection(
            transport=transport,
            config_hash="e2e-mcp-test-hash",
            state=ConnectionState.CONNECTED,
            session_id="e2e-mcp-test-session",
        )
        client._connections["e2e-mcp-test-hash"] = conn
        return conn

    def test_mcp_governance_allow(
        self,
        mock_transport: MagicMock,
        mcp_client: MCPClient,
        mcp_governance: MCPGovernance,
    ) -> None:
        """E2E-MCP-1: ALLOW verdict → tool call executes on transport"""
        mcp_client.register_governance(mcp_governance)
        conn = self._connect(mcp_client, mock_transport)

        response = mcp_client.call_tool(
            conn=conn,
            tool_name="read_file",
            args={"path": "/tmp/test.txt"},
            request_id="mcp-1-req",
        )

        assert response.is_error is False
        assert response.result == {"status": "ok"}
        mock_transport.send_tool_call.assert_called_once_with(
            "read_file",
            {"path": "/tmp/test.txt"},
        )

    def test_mcp_governance_deny(
        self,
        mock_transport: MagicMock,
        mcp_client: MCPClient,
        mcp_governance: MCPGovernance,
    ) -> None:
        """E2E-MCP-2: DENY verdict → error code -32000, transport NOT called"""
        mcp_client.register_governance(mcp_governance)
        conn = self._connect(mcp_client, mock_transport)

        response = mcp_client.call_tool(
            conn=conn,
            tool_name="write_file",
            args={"command": "rm -rf /"},
            request_id="mcp-2-req",
        )

        assert response.is_error is True
        assert response.error_code == -32000
        assert response.error is not None
        assert "denied" in response.error.get("message", "").lower()
        mock_transport.send_tool_call.assert_not_called()

    def test_mcp_governance_ask_user(
        self,
        mock_transport: MagicMock,
        mcp_client: MCPClient,
        mcp_governance: MCPGovernance,
    ) -> None:
        """E2E-MCP-3: ASK_USER verdict → error code -32001 + hitl_event_id"""
        mcp_client.register_governance(mcp_governance)
        conn = self._connect(mcp_client, mock_transport)

        response = mcp_client.call_tool(
            conn=conn,
            tool_name="write_file",
            args={"path": "/tmp/test.txt", "content": "e2e test data"},
            request_id="mcp-3-req",
        )

        assert response.is_error is True
        assert response.error_code == -32001
        assert response.result is not None
        assert "hitl_event_id" in response.result
        assert isinstance(response.result["hitl_event_id"], str)
        assert len(response.result["hitl_event_id"]) > 0
        mock_transport.send_tool_call.assert_not_called()

    def test_mcp_governance_audit_integrity(
        self,
        mock_transport: MagicMock,
        mcp_client: MCPClient,
        mcp_governance: MCPGovernance,
    ) -> None:
        """E2E-MCP-4: Audit logs correctly recorded and verifiable"""
        mcp_client.register_governance(mcp_governance)
        conn = self._connect(mcp_client, mock_transport)

        mcp_client.call_tool(
            conn=conn,
            tool_name="read_file",
            args={"path": "/tmp/a.txt"},
            request_id="audit-1",
        )
        mcp_client.call_tool(
            conn=conn,
            tool_name="write_file",
            args={"command": "rm -rf /"},
            request_id="audit-2",
        )
        mcp_client.call_tool(
            conn=conn,
            tool_name="write_file",
            args={"path": "/tmp/b.txt", "content": "data"},
            request_id="audit-3",
        )

        violations = mcp_governance.verify_audit_integrity()
        assert len(violations) == 0, f"Audit integrity violations: {violations}"

        audit_log = mcp_governance.get_audit_log()
        assert len(audit_log) == 3
        assert audit_log[0].tool_name == "read_file"
        assert audit_log[0].verdict == "ALLOW"
        assert audit_log[1].tool_name == "write_file"
        assert audit_log[1].verdict == "DENY"
        assert audit_log[2].tool_name == "write_file"
        assert audit_log[2].verdict == "ASK_USER"

        decision_log = mcp_governance.get_decision_log()
        assert len(decision_log) == 3
        assert decision_log[0].verdict == MCPDecisionVerdict.ALLOW
        assert decision_log[1].verdict == MCPDecisionVerdict.DENY
        assert decision_log[2].verdict == MCPDecisionVerdict.ASK_USER
