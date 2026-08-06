from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_server import create_a2a_router


@pytest.fixture
def audit_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def audit_logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


@pytest.fixture
def state_machine() -> GovernanceStateMachine:
    return GovernanceStateMachine()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker()


@pytest.fixture
def bridge(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
    circuit_breaker: CircuitBreaker,
) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
        circuit_breaker=circuit_breaker,
    )


@pytest.fixture
def app(bridge: A2ABridge) -> FastAPI:
    application = FastAPI()
    router = create_a2a_router(bridge, signing_key="test-hmac-key")
    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestTaskSend:
    def test_send_task_success(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "user-ref-1",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Analyze governance data"}],
                },
                "metadata": {"skills": ["maref-governance"], "priority": "high"},
            },
            "id": 1,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        result = data["result"]
        assert "id" in result
        assert result["id"].startswith("maref-task-")
        assert result["status"]["state"] == "submitted"

    def test_send_task_no_text_fallback_to_params_id(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {"id": "fallback-ref"},
            "id": 2,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["id"].startswith("maref-task-")

    def test_send_task_unknown_skills(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "Do something"}]},
                "metadata": {"skills": ["nonexistent-skill"]},
            },
            "id": 3,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
        assert "nonexistent-skill" in data["error"]["message"]

    def test_send_task_wrong_method(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/wrong",
            "params": {"message": {"parts": [{"type": "text", "text": "test"}]}},
            "id": 4,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_send_task_invalid_body_empty(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/send", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_send_task_with_capabilities_alias(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "Audit task"}]},
                "metadata": {"capabilities": ["maref-audit"]},
            },
            "id": 5,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        assert "result" in resp.json()

    def test_send_task_capabilities_alias_unknown(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "Test"}]},
                "metadata": {"capabilities": ["bogus-cap"]},
            },
            "id": 6,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


class TestTaskGet:
    def test_get_task_found(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Get test task")
        resp = client.get(f"/api/a2a/task/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["status"]["state"] == "submitted"
        assert data["description"] == "Get test task"
        assert "maref_state" in data

    def test_get_task_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/a2a/task/nonexistent-task")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data

    def test_get_task_returns_history(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("History test")
        resp = client.get(f"/api/a2a/task/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)


class TestTaskCancel:
    def test_cancel_task_success(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Cancel me")
        resp = client.post("/api/a2a/task/cancel", json={"id": task_id, "reason": "Testing cancel"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["task_id"] == task_id
        assert data["state"] == "canceled"
        assert data["reason"] == "Testing cancel"

    def test_cancel_task_with_task_id_key(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Cancel via task_id key")
        resp = client.post("/api/a2a/task/cancel", json={"task_id": task_id})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_cancel_task_missing_id(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/cancel", json={"reason": "no id"})
        assert resp.status_code == 400

    def test_cancel_task_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/cancel", json={"id": "nonexistent"})
        assert resp.status_code == 404


class TestTaskState:
    def test_push_state_update(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("State push test")
        resp = client.post("/api/a2a/task/state", json={"task_id": task_id, "state": "working"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["state"] == "working"

        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state.value == "working"

    def test_push_state_update_using_id_field(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("State push alt")
        resp = client.post("/api/a2a/task/state", json={"id": task_id, "state": "completed"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_push_state_missing_fields(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/state", json={"task_id": ""})
        assert resp.status_code == 400

    def test_push_state_unknown_task(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/state", json={"task_id": "no-such-task", "state": "working"})
        assert resp.status_code == 404


class TestAgentCard:
    def test_agent_card_returns_signed_card(self, client: TestClient) -> None:
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "agentCard" in data
        assert "signature" in data
        assert data["signingAlgorithm"] == "hmac-sha256"
        card = data["agentCard"]
        assert card["name"] == "maref-agent"
        assert card["protocolVersion"] == "1.0"
        assert "skills" in card
        assert len(card["skills"]) > 0

    def test_agent_card_signature_verifiable(self, client: TestClient) -> None:
        import hashlib
        import hmac

        resp = client.get("/.well-known/agent-card.json")
        data = resp.json()
        card = data["agentCard"]
        signature = data["signature"]

        payload = json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hmac.new(b"test-hmac-key", payload, hashlib.sha256).hexdigest()
        assert signature == expected

    def test_agent_card_includes_skills(self, client: TestClient) -> None:
        resp = client.get("/.well-known/agent-card.json")
        card = resp.json()["agentCard"]
        skill_ids = {s["id"] for s in card["skills"]}
        assert "maref-governance" in skill_ids
        assert "maref-delegate" in skill_ids
        assert "maref-audit" in skill_ids


class TestCircuitBreakerBlocking:
    def test_circuit_breaker_blocks_task_send(
        self,
        client: TestClient,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "Should be blocked"}]},
            },
            "id": 99,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 503

    def test_circuit_breaker_blocks_task_get(
        self,
        client: TestClient,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        resp = client.get("/api/a2a/task/some-task")
        assert resp.status_code == 503

    def test_circuit_breaker_blocks_agent_card(
        self,
        client: TestClient,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 503

    def test_circuit_breaker_blocks_state_push(
        self,
        client: TestClient,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        resp = client.post(
            "/api/a2a/task/state",
            json={"task_id": "any", "state": "working"},
        )
        assert resp.status_code == 503

    def test_circuit_breaker_closed_allows_operations(
        self, client: TestClient, bridge: A2ABridge
    ) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "Normal operation"}]},
            },
            "id": 100,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        assert "result" in resp.json()


class TestSSEStream:
    def test_sse_connect_returns_stream(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("SSE test task")
        bridge.sync_state_from_a2a(task_id, "completed")
        with client.stream("GET", f"/api/a2a/task/{task_id}/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
            content = b"".join(response.iter_bytes()).decode("utf-8")
            assert "connected" in content

    def test_sse_unknown_task(self, client: TestClient) -> None:
        resp = client.get("/api/a2a/task/nonexistent/stream")
        assert resp.status_code == 404

    def test_sse_emits_state_changes(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("SSE state test")
        bridge.sync_state_from_a2a(task_id, "completed")
        with client.stream("GET", f"/api/a2a/task/{task_id}/stream") as response:
            assert response.status_code == 200
            content = b"".join(response.iter_bytes()).decode("utf-8")
            assert "connected" in content
            assert "completed" in content
            assert "[DONE]" in content

    def test_sse_circuit_breaker_blocks(self, client: TestClient, circuit_breaker: CircuitBreaker) -> None:
        circuit_breaker._state = BreakerState.OPEN
        resp = client.get("/api/a2a/task/any-task/stream")
        assert resp.status_code == 503


class TestPushNotification:
    def test_push_notification_state_update(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Push test task")
        body = {
            "task_id": task_id,
            "event": {"type": "state_update", "state": "completed"},
        }
        resp = client.post("/api/a2a/task/push_notification", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state.value == "completed"

    def test_push_notification_missing_id(self, client: TestClient) -> None:
        resp = client.post("/api/a2a/task/push_notification", json={"event": {}})
        assert resp.status_code == 400

    def test_push_notification_unknown_task(self, client: TestClient) -> None:
        body = {
            "task_id": "nonexistent",
            "event": {"type": "state_update", "state": "working"},
        }
        resp = client.post("/api/a2a/task/push_notification", json=body)
        assert resp.status_code == 404


class TestA2ASpecRoutes:
    def test_post_a2a_tasks(self, client: TestClient) -> None:
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "spec-test",
                "message": {"parts": [{"text": "Spec route test"}]},
                "metadata": {"skills": ["maref-governance"]},
            },
            "id": 1,
        }
        resp = client.post("/a2a/tasks", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data

    def test_get_a2a_tasks(self, client: TestClient, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Spec get test")
        resp = client.get(f"/a2a/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id

    def test_get_a2a_tasks_not_found(self, client: TestClient) -> None:
        resp = client.get("/a2a/tasks/nonexistent")
        assert resp.status_code == 404


class TestNoBridge:
    def test_router_without_signing_key_still_works(self) -> None:
        sm = GovernanceStateMachine()
        al = AuditLogger(tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name)
        br = A2ABridge(state_machine=sm, audit_logger=al)
        app = FastAPI()
        app.include_router(create_a2a_router(br))
        c = TestClient(app)

        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"type": "text", "text": "No key test"}]},
            },
            "id": 1,
        }
        resp = c.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        task_id = resp.json()["result"]["id"]

        resp2 = c.get(f"/api/a2a/task/{task_id}")
        assert resp2.status_code == 200

        resp3 = c.get("/.well-known/agent-card.json")
        assert resp3.status_code == 200
        card_data = resp3.json()
        assert card_data["signature"] == ""
