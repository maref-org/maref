from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_discovery import A2ADiscovery
from maref.integration.a2a_server import create_a2a_router
from maref.integration.a2a_types import A2A_PROTOCOL_VERSION


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


def _make_bridge(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
    circuit_breaker: CircuitBreaker | None = None,
    agent_name: str = "agent-a",
) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
        circuit_breaker=circuit_breaker,
        agent_name=agent_name,
        agent_description=f"{agent_name} test agent",
    )


def _make_app(bridge: A2ABridge) -> FastAPI:
    app = FastAPI()
    app.include_router(create_a2a_router(bridge, signing_key="test-key"))
    return app


@pytest.fixture
def agent_a_bridge(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
) -> A2ABridge:
    return _make_bridge(state_machine, audit_logger)


@pytest.fixture
def agent_b_bridge(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
) -> A2ABridge:
    return _make_bridge(state_machine, audit_logger, agent_name="agent-b")


class TestTwoAgentExchange:
    def test_agent_a_sends_task_to_agent_b_via_http(
        self, agent_b_bridge: A2ABridge
    ) -> None:
        app_b = _make_app(agent_b_bridge)
        client = TestClient(app_b)
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "user-ref-1",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Analyze governance data from agent A"}],
                },
                "metadata": {"skills": ["maref-governance"]},
            },
            "id": 1,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        task_result = data.get("result", {})
        assert task_result["id"].startswith("maref-task-")
        assert task_result["status"]["state"] == "submitted"

    def test_agent_card_discovery(
        self, agent_a_bridge: A2ABridge
    ) -> None:
        app_a = _make_app(agent_a_bridge)
        client = TestClient(app_a)
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        data = resp.json()
        card = data["agentCard"]
        assert card["name"] == "agent-a"
        assert card["protocolVersion"] == A2A_PROTOCOL_VERSION
        assert card["capabilities"]["streaming"] is True
        assert card["capabilities"]["pushNotifications"] is True
        skill_ids = {s["id"] for s in card["skills"]}
        assert "maref-governance" in skill_ids
        assert "maref-delegate" in skill_ids

    def test_a2a_client_discover_then_send(
        self, agent_b_bridge: A2ABridge
    ) -> None:
        app_b = _make_app(agent_b_bridge)
        client = TestClient(app_b)
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        card_data = resp.json()
        agent_card = card_data.get("agentCard", {})
        skills = agent_card.get("skills", [])
        assert len(skills) > 0
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "discover-ref",
                "message": {"parts": [{"type": "text", "text": "Discovered task"}]},
                "metadata": {"skills": [skills[0]["id"]]},
            },
            "id": 1,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        assert "result" in resp.json()

    def test_task_lifecycle_across_agents(
        self, agent_b_bridge: A2ABridge
    ) -> None:
        app_b = _make_app(agent_b_bridge)
        client = TestClient(app_b)
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "lifecycle-ref",
                "message": {"parts": [{"type": "text", "text": "Lifecycle task"}]},
                "metadata": {"skills": ["maref-governance"]},
            },
            "id": 1,
        }
        resp = client.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        task_id = resp.json().get("result", {}).get("id", "")
        assert task_id.startswith("maref-task-")
        resp2 = client.get(f"/api/a2a/task/{task_id}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == task_id


class TestCircuitBreakerNetwork:
    def test_open_breaker_returns_503(
        self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger
    ) -> None:
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        bridge = _make_bridge(state_machine, audit_logger, circuit_breaker=cb)
        app = _make_app(bridge)
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"text": "Blocked task"}]},
            },
            "id": 1,
        }
        with TestClient(app) as c:
            resp = c.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 503

    def test_stream_blocked_by_open_breaker(
        self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger
    ) -> None:
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        bridge = _make_bridge(state_machine, audit_logger, circuit_breaker=cb)
        app = _make_app(bridge)
        with TestClient(app) as c:
            resp = c.get("/api/a2a/task/some-task/stream")
        assert resp.status_code == 503

    def test_open_breaker_all_routes_blocked(
        self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger
    ) -> None:
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        bridge = _make_bridge(state_machine, audit_logger, circuit_breaker=cb)
        app = _make_app(bridge)
        with TestClient(app) as c:
            card_resp = c.get("/.well-known/agent-card.json")
            state_resp = c.post(
                "/api/a2a/task/state",
                json={"task_id": "any", "state": "working"},
            )
        assert card_resp.status_code == 503
        assert state_resp.status_code == 503


class TestTimeoutAndUnknown:
    def test_unknown_skill_returns_error(
        self, agent_a_bridge: A2ABridge
    ) -> None:
        app_a = _make_app(agent_a_bridge)
        body = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {"parts": [{"text": "Unknown skill"}]},
                "metadata": {"skills": ["nonexistent-skill-xyz"]},
            },
            "id": 1,
        }
        with TestClient(app_a) as c:
            resp = c.post("/api/a2a/task/send", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602


class TestA2ADiscovery:
    def test_register_and_health_check(self) -> None:
        discovery = A2ADiscovery()
        discovery.register_agent("agent-x", "http://localhost:8000", capabilities=["test"])
        agent = discovery.get_agent("agent-x")
        assert agent is not None
        assert agent["agent_id"] == "agent-x"
        assert agent["healthy"] is True
        discovery.unregister_agent("agent-x")
        assert discovery.get_agent("agent-x") is None

    def test_discover_by_capability(self) -> None:
        discovery = A2ADiscovery()
        discovery.register_agent("agent-a", "http://a:8000", capabilities=["governance"])
        discovery.register_agent("agent-b", "http://b:8000", capabilities=["audit"])
        governance_agents = discovery.discover_agents(capability_filter="governance")
        assert len(governance_agents) == 1
        assert governance_agents[0]["agent_id"] == "agent-a"

    def test_list_agents(self) -> None:
        discovery = A2ADiscovery()
        discovery.register_agent("agent-a", "http://a:8000")
        discovery.register_agent("agent-b", "http://b:8000")
        agents = discovery.list_agents()
        assert len(agents) == 2


class TestA2AClient:
    def test_send_and_cancel(self) -> None:
        client = A2AClient()
        assert client.get_active_tasks() == {}
        task_id = "test-task-001"
        client._active_tasks[task_id] = {
            "agent_url": "http://localhost:8000",
            "created_at": 0,
            "status": {"state": "submitted"},
        }
        assert task_id in client.get_active_tasks()
        client.clear_active_tasks()
        assert client.get_active_tasks() == {}

    def test_send_task_error_returns_none(self) -> None:
        client = A2AClient()
        async def run() -> Any:
            result = await client.send_task(
                agent_url="http://nonexistent.local:9999",
                skill_id="test",
                input_data="test",
            )
            return result
        result = asyncio.run(run())
        assert result is None

    def test_get_task_error_returns_none(self) -> None:
        client = A2AClient()
        async def run() -> Any:
            result = await client.get_task(
                agent_url="http://nonexistent.local:9999",
                task_id="task-1",
            )
            return result
        result = asyncio.run(run())
        assert result is None

    def test_cancel_task_error_returns_false(self) -> None:
        client = A2AClient()
        async def run() -> Any:
            result = await client.cancel_task(
                agent_url="http://nonexistent.local:9999",
                task_id="task-1",
            )
            return result
        result = asyncio.run(run())
        assert result is False

    def test_discover_agent_card_error_returns_none(self) -> None:
        client = A2AClient()
        async def run() -> Any:
            result = await client.discover_agent_card(
                agent_url="http://nonexistent.local:9999",
            )
            return result
        result = asyncio.run(run())
        assert result is None

    def test_push_state_error_returns_false(self) -> None:
        client = A2AClient()
        async def run() -> Any:
            result = await client.push_state(
                agent_url="http://nonexistent.local:9999",
                task_id="task-1",
                state="completed",
            )
            return result
        result = asyncio.run(run())
        assert result is False
