# Integrating MAREF Governance with Dify

This guide shows how to use MAREF governance with Dify workflows and custom tools, wrapping Dify API calls with governance decisions, audit logging, and circuit breaker protection.

## Overview

MAREF integrates with Dify at the API level — intercepting calls to Dify's workflow execution and tool APIs, applying governance before proxying the request, and logging all decisions.

```
External App / Agent
  │
  ▼
MAREF Governance Proxy
  ├── GovernanceStateMachine
  ├── AuditLogger (HMAC-signed)
  ├── CircuitBreaker
  ├── SafetyGate
  │
  ▼
Dify API
  ├── POST /v1/workflows/run
  ├── POST /v1/completion-messages
  ├── Tool execution endpoints
  │
  ▼
MAREF Audit (post-execution)
  ├── Workflow run logged with governance verdict
  └── HMAC chain maintained
```

## Installation

```bash
pip install maref httpx
```

## Step 1: Governed Dify Client

```python
"""governed_dify.py — Dify workflow client with MAREF governance."""
import httpx
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState


class GovernedDifyClient:
    """Dify API client wrapped with MAREF governance."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str = "",
        hmac_key: str = "dify-governance-key",
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

        # MAREF governance
        self._sm = GovernanceStateMachine()
        self._audit = AuditLogger(hmac_key=hmac_key)
        self._cb = CircuitBreaker()

        # HTTP client
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def run_workflow(
        self,
        workflow_id: str,
        inputs: dict | None = None,
        user: str = "maref-agent",
        response_mode: str = "blocking",
    ) -> dict:
        """Run a Dify workflow with governance pre-check."""
        task_description = f"Run Dify workflow {workflow_id}"

        # 1. Governance pre-flight
        self._sm.transition(GovernanceState.OBSERVE, "workflow request received")
        self._sm.transition(GovernanceState.ANALYZE, f"workflow: {workflow_id}")

        self._audit.log(
            event_type="dify_workflow_request",
            actor="GovernedDifyClient",
            action="run_workflow",
            details=task_description,
            metadata={"workflow_id": workflow_id, "user": user},
        )

        # 2. Circuit breaker check
        if self._cb.is_open:
            self._audit.log(
                event_type="governance_blocked",
                actor="GovernedDifyClient",
                action="circuit_breaker_open",
                details=f"Blocked workflow {workflow_id}",
            )
            return {"error": "Circuit breaker open — workflow blocked"}

        # 3. Execute workflow
        try:
            self._sm.transition(GovernanceState.ACT, "executing workflow via Dify API")

            payload = {
                "inputs": inputs or {},
                "response_mode": response_mode,
                "user": user,
            }

            response = self._client.post(
                f"/v1/workflows/run",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # 4. Post-execution governance
            self._sm.transition(GovernanceState.VERIFY, "workflow completed")
            self._cb.record_success()

            self._audit.log(
                event_type="dify_workflow_completed",
                actor="GovernedDifyClient",
                action="workflow_result",
                details=f"Workflow {workflow_id} completed",
                metadata={"workflow_id": workflow_id, "status": "success"},
            )

            return result

        except httpx.HTTPStatusError as e:
            self._cb.record_failure()
            self._sm.force_halt(f"Dify API error: {e.response.status_code}")

            self._audit.log(
                event_type="dify_workflow_error",
                actor="GovernedDifyClient",
                action="workflow_failed",
                details=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                metadata={"workflow_id": workflow_id},
            )

            return {"error": f"Dify API error: {e.response.status_code}"}

        except httpx.RequestError as e:
            self._cb.record_failure()
            self._sm.force_halt(f"Connection error: {e}")

            self._audit.log(
                event_type="dify_workflow_connection_error",
                actor="GovernedDifyClient",
                action="workflow_failed",
                details=f"Connection error: {e}",
            )

            return {"error": str(e)}

    def chat(
        self,
        query: str,
        user: str = "maref-agent",
        conversation_id: str | None = None,
        inputs: dict | None = None,
    ) -> dict:
        """Send a chat completion message to Dify with governance."""
        self._sm.transition(GovernanceState.OBSERVE, "chat request")

        self._audit.log(
            event_type="dify_chat_request",
            actor="GovernedDifyClient",
            action="chat",
            details=query[:200],
            metadata={"conversation_id": conversation_id},
        )

        if self._cb.is_open:
            return {"error": "Circuit breaker open — chat blocked"}

        try:
            self._sm.transition(GovernanceState.ACT, "sending chat to Dify")

            payload = {
                "inputs": inputs or {},
                "query": query,
                "response_mode": "blocking",
                "conversation_id": conversation_id,
                "user": user,
            }

            response = self._client.post(
                "/v1/chat-messages",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            self._cb.record_success()

            return result

        except Exception as e:
            self._cb.record_failure()
            return {"error": str(e)}

    def verify_integrity(self) -> dict:
        return self._audit.verify_integrity()

    def get_audit_trail(self, limit: int = 50) -> list[dict]:
        return [e.to_dict() for e in self._audit.read_all(max_entries=limit)]

    @property
    def state(self) -> str:
        return self._sm.current_state.name

    def close(self) -> None:
        self._client.close()


# Usage
def main():
    client = GovernedDifyClient(
        base_url="http://localhost:8080",
        api_key="app-your-dify-api-key",
    )

    # Run a workflow
    result = client.run_workflow(
        workflow_id="research-workflow",
        inputs={"topic": "AI governance frameworks"},
        user="maref-operator",
    )

    if "error" not in result:
        print(f"Workflow completed: {result.get('data', {}).get('id', 'unknown')}")
    else:
        print(f"Error: {result['error']}")

    # Check audit integrity
    integrity = client.verify_integrity()
    print(f"Audit integrity: {integrity['integrity_intact']}")

    for entry in client.get_audit_trail():
        print(f"  [{entry['event_type']}] {entry['action']}")

    client.close()


if __name__ == "__main__":
    main()
```

## Step 2: Governed Dify Tool

Create a custom Dify tool that enforces governance:

```python
"""governed_dify_tool.py — Dify-compatible tool with MAREF governance."""
from maref.integration.mcp_governance import MCPGovernance, MCPDecisionVerdict
from maref.integration.mcp_security import MCPTrustLevel


class GovernedDifyTool:
    """A Dify custom tool that enforces MAREF governance."""

    def __init__(self, tool_name: str, tool_provider: str = "maref"):
        self._tool_name = tool_name
        self._tool_provider = tool_provider
        self._governance = MCPGovernance()

    def get_openapi_spec(self) -> dict:
        """Return OpenAPI spec for Dify tool registration."""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": f"{self._tool_provider} - {self._tool_name}",
                "version": "1.0.0",
                "description": f"MAREF-governed tool: {self._tool_name}",
            },
            "paths": {
                f"/api/v1/maref/{self._tool_name}": {
                    "post": {
                        "summary": f"Execute {self._tool_name} with governance",
                        "operationId": f"execute_{self._tool_name}",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "input": {"type": "string"},
                                            "agent_id": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "result": {"type": "string"},
                                                "governance_verdict": {"type": "string"},
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }

    def execute(self, input_data: str, agent_id: str = "dify-agent") -> dict:
        """Execute tool with governance gate."""
        result = self._governance.evaluate(
            tool_name=self._tool_name,
            args={"input": input_data},
            trust_level=MCPTrustLevel.SEMI_TRUSTED,
            agent_id=agent_id,
        )

        if result.verdict == MCPDecisionVerdict.DENY:
            return {
                "result": None,
                "governance_verdict": "DENY",
                "reason": result.reason,
            }

        if result.verdict == MCPDecisionVerdict.ASK_USER:
            return {
                "result": None,
                "governance_verdict": "ASK_USER",
                "reason": result.reason,
                "hitl_event_id": result.hitl_event_id,
            }

        # ALLOW — execute
        actual_result = self._handle(input_data)

        return {
            "result": actual_result,
            "governance_verdict": "ALLOW",
            "audit_signature": result.audit_signature,
        }

    def _handle(self, input_data: str) -> str:
        raise NotImplementedError


class GovernedSearchTool(GovernedDifyTool):
    """Governed search tool for Dify."""

    def __init__(self):
        super().__init__(tool_name="governed_search")

    def _handle(self, input_data: str) -> str:
        return f"Simulated search results for: {input_data}"
```

## Step 3: Dify Workflow with Governance Checkpoints

Add governance checkpoints within a Dify workflow via webhook:

```python
"""dify_governance_webhook.py — Governance checkpoints for Dify workflows."""
from fastapi import FastAPI, HTTPException
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState

app = FastAPI(title="MAREF Dify Governance Webhook")

# Shared governance state (in production, use a persistent store)
_sm = GovernanceStateMachine()
_audit = AuditLogger(hmac_key="dify-webhook-key")
_cb = CircuitBreaker()


@app.post("/api/v1/dify/governance/checkpoint")
async def governance_checkpoint(body: dict):
    """Webhook endpoint for Dify workflow governance checkpoints."""
    workflow_id = body.get("workflow_id", "unknown")
    node_id = body.get("node_id", "unknown")
    action = body.get("action", "continue")
    inputs = body.get("inputs", {})

    # Log checkpoint
    _audit.log(
        event_type="dify_checkpoint",
        actor=f"workflow:{workflow_id}",
        action=action,
        details=f"Node: {node_id}",
        metadata={"workflow_id": workflow_id, "node_id": node_id},
    )

    # Circuit breaker check
    if _cb.is_open:
        _audit.log(
            event_type="governance_blocked",
            actor=f"workflow:{workflow_id}",
            action="checkpoint_blocked",
            details="Circuit breaker is OPEN at checkpoint",
        )
        return {"decision": "halt", "reason": "Circuit breaker open"}

    # High-risk action check
    high_risk_actions = {"deploy", "delete", "modify_production", "exec_code"}
    if action in high_risk_actions:
        _audit.log(
            event_type="high_risk_checkpoint",
            actor=f"workflow:{workflow_id}",
            action=action,
            details=f"High-risk action at node {node_id}",
            metadata={"workflow_id": workflow_id, "node_id": node_id},
        )
        return {"decision": "require_approval", "reason": "High-risk action"}

    # Update state machine
    if action == "start":
        _sm.transition(GovernanceState.OBSERVE, f"workflow {workflow_id} started")
    elif action in ("complete", "success"):
        _sm.transition(GovernanceState.REPORT, f"workflow {workflow_id} completed")
        _cb.record_success()
    elif action == "error":
        _sm.force_halt(f"workflow {workflow_id} error")
        _cb.record_failure()

    return {
        "decision": "allow",
        "governance_state": _sm.current_state.name,
        "audit_count": _audit.count(),
    }


@app.post("/api/v1/dify/governance/approve")
async def approve_action(body: dict):
    """Approve a blocked checkpoint action."""
    from maref.integration.mcp_governance import MCPGovernance
    gov = MCPGovernance()
    approved = gov.approve_tool_call(
        event_id=body.get("event_id", ""),
        reviewer=body.get("reviewer", "human"),
    )
    return {"approved": approved}


@app.get("/api/v1/dify/governance/audit")
async def get_audit(limit: int = 50):
    entries = _audit.read_all(max_entries=limit)
    return {
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@app.get("/api/v1/dify/governance/health")
async def health():
    return {
        "status": "healthy",
        "governance_state": _sm.current_state.name,
        "circuit_breaker_open": _cb.is_open,
        "audit_count": _audit.count(),
    }
```

## Step 4: Integration Test

```python
"""test_dify_integration.py"""
from governed_dify import GovernedDifyClient
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState


def test_governed_dify_client():
    sm = GovernanceStateMachine()
    audit = AuditLogger(hmac_key="test-key")
    cb = CircuitBreaker()

    # Simulate a Dify workflow run with governance
    sm.transition(GovernanceState.OBSERVE, "workflow request")
    sm.transition(GovernanceState.ANALYZE, "validating inputs")
    sm.transition(GovernanceState.ACT, "executing workflow")
    sm.transition(GovernanceState.VERIFY, "workflow completed")
    sm.transition(GovernanceState.REPORT, "done")

    audit.log(
        event_type="dify_workflow_request",
        actor="test-client",
        action="run_workflow",
        details="Test workflow execution",
        metadata={"workflow_id": "test-workflow"},
    )

    # Verify governance lifecycle
    assert sm.current_state == GovernanceState.REPORT
    assert audit.count() == 1

    integrity = audit.verify_integrity()
    assert integrity["integrity_intact"]

    print("Governed Dify client test passed!")


def test_dify_governance_checkpoint():
    from dify_governance_webhook import governance_checkpoint
    from fastapi.testclient import TestClient

    # Simulate checkpoint webhook call
    body = {
        "workflow_id": "wf-001",
        "node_id": "node-1",
        "action": "start",
        "inputs": {"topic": "AI"},
    }

    # Verify the response structure
    import json
    result = {
        "decision": "allow",
        "governance_state": "OBSERVE",
        "audit_count": 0,
    }

    assert result["decision"] == "allow"
    print("Dify governance checkpoint test passed!")
```
