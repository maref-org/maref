# Cookbook: A2A Agent Federation

This guide demonstrates running two MAREF agents that communicate via the A2A protocol, including agent card discovery, task delegation, and audit trail monitoring.

## Architecture

```
Agent A (port 8001)                  Agent B (port 8002)
  ┌────────────────────┐              ┌────────────────────┐
  │ A2ABridge          │              │ A2ABridge          │
  │ A2ADiscovery       │◄────A2A─────►│ A2ADiscovery       │
  │ A2AClient          │              │ A2AClient          │
  │ GovernanceStateMchn│              │ GovernanceStateMchn│
  │ AuditLogger        │              │ AuditLogger        │
  └────────────────────┘              └────────────────────┘
```

## Setup

Install dependencies:

```bash
pip install maref httpx uvicorn fastapi
```

## Step 1: Agent A (Task Delegator)

```python
"""agent_a.py — Delegates tasks to Agent B."""
import asyncio
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_discovery import A2ADiscovery

# Governance components
state_machine_a = GovernanceStateMachine()
audit_a = AuditLogger(hmac_key="agent-a-key")
cb_a = CircuitBreaker()

# A2A bridge
bridge_a = A2ABridge(
    state_machine=state_machine_a,
    audit_logger=audit_a,
    circuit_breaker=cb_a,
    agent_name="agent-alpha",
    agent_description="Task delegator with MAREF governance",
)

# Discovery service
discovery_a = A2ADiscovery()

# A2A HTTP client for outbound calls
client_a = A2AClient(timeout=30.0)


async def delegate_data_analysis():
    agent_b_url = "http://localhost:8002"

    # 1. Discover Agent B's capabilities
    card = await client_a.discover_agent_card(agent_b_url)
    if card is None:
        print("Agent B not reachable")
        return

    agent_card = card.get("agentCard", {})
    print(f"Discovered: {agent_card.get('name')}")
    print(f"Skills: {[s['id'] for s in agent_card.get('skills', [])]}")

    # 2. Create local task
    task_id = bridge_a.create_task(
        "Analyze Q2 financial data and generate report",
        {"type": "analysis", "urgency": "high"},
    )

    # 3. Delegate to Agent B via A2A
    bridge_a.delegate_task(task_id, agent_b_url)

    # 4. Poll for completion
    for _ in range(10):
        result = await client_a.get_task(agent_b_url, task_id)
        if result:
            state = result.get("status", {}).get("state", "")
            print(f"Task {task_id}: {state}")
            if state in ("completed", "canceled", "failed"):
                break
        await asyncio.sleep(1)

    # 5. Sync final state
    bridge_a.sync_state_from_a2a(task_id, "completed")

    # 6. Check audit trail
    print("\nAgent A Audit Trail:")
    for entry in audit_a.read_all(max_entries=5):
        print(f"  [{entry.event_type}] {entry.actor}: {entry.action}")


if __name__ == "__main__":
    asyncio.run(delegate_data_analysis())
```

## Step 2: Agent B (Task Worker)

```python
"""agent_b.py — Receives and processes delegated tasks."""
from fastapi import FastAPI
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_server import create_a2a_router

# Governance components
state_machine_b = GovernanceStateMachine()
audit_b = AuditLogger(hmac_key="agent-b-key")
cb_b = CircuitBreaker()

# A2A bridge
bridge_b = A2ABridge(
    state_machine=state_machine_b,
    audit_logger=audit_b,
    circuit_breaker=cb_b,
    agent_name="agent-beta",
    agent_description="Task worker with MAREF governance",
)

# FastAPI app with A2A endpoints
app_b = FastAPI(title="Agent Beta")
app_b.include_router(create_a2a_router(bridge_b, signing_key="my-signing-key"))


@app_b.get("/api/health")
def health():
    return {"status": "healthy", "agent": "beta", "tasks": len(bridge_b._tasks)}


@app_b.get("/api/audit")
def audit_trail(limit: int = 10):
    entries = audit_b.read_all(max_entries=limit)
    return {
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_b, host="0.0.0.0", port=8002)
```

## Step 3: Run Both Agents

Terminal 1:
```bash
python agent_b.py
# INFO: Uvicorn running on http://0.0.0.0:8002
```

Terminal 2:
```bash
python agent_a.py
# Discovered: agent-beta
# Skills: ['maref-governance', 'maref-delegate', 'maref-audit']
# Task maref-task-abc123: submitted -> working -> completed
# Agent A Audit Trail:
#   [a2a_task_created] agent-alpha: create_task
#   [a2a_task_delegated] agent-alpha: delegate_task
#   [a2a_state_sync] agent-alpha: sync_state_from_a2a
```

## Step 4: Monitor Audit Trails

Verify audit chain integrity on both agents:

```python
"""audit_check.py — Check both agents' audit trails."""
import httpx


async def check_audit():
    async with httpx.AsyncClient() as client:
        # Agent A audit
        resp_a = await client.get(
            "http://localhost:8001/api/audit",
            params={"limit": 20},
        )
        data_a = resp_a.json()
        print(f"Agent A: {data_a['count']} entries")

        # Agent B audit (via agent_b.py endpoint)
        resp_b = await client.get(
            "http://localhost:8002/api/audit",
            params={"limit": 20},
        )
        data_b = resp_b.json()
        print(f"Agent B: {data_b['count']} entries")

        # Verify cross-agent correlation
        for entry in data_a.get("entries", []):
            if entry["event_type"] == "a2a_task_delegated":
                print(f"Delegated task: {entry['metadata']['task_id']}")
                print(f"  to: {entry['metadata']['target_agent_url']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_audit())
```

## Step 5: Full Federation Test

```python
"""test_federation.py — Test two-agent A2A federation."""
import asyncio
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_discovery import A2ADiscovery


async def test_federation():
    sm_a = GovernanceStateMachine()
    sm_b = GovernanceStateMachine()
    audit_a = AuditLogger()
    audit_b = AuditLogger()

    bridge_a = A2ABridge(sm_a, audit_a, agent_name="test-a")
    bridge_b = A2ABridge(sm_b, audit_b, agent_name="test-b")

    discovery = A2ADiscovery()
    discovery.register_agent("test-a", "http://localhost:8001")
    discovery.register_agent("test-b", "http://localhost:8002")

    # Verify discovery
    agents = discovery.discover_agents()
    assert len(agents) == 2

    # Bridge A creates and delegates a task
    task_id = bridge_a.create_task("Federation test task")
    assert task_id is not None

    # Simulate delegation
    success = bridge_a.delegate_task(task_id, "http://localhost:8002")
    assert success

    # Check delegated tasks on A
    delegated = bridge_a.get_delegated_tasks()
    assert len(delegated) == 1
    assert delegated[0]["target_agent_url"] == "http://localhost:8002"

    # Sync states between agents
    bridge_a.sync_state_from_a2a(task_id, "working")
    bridge_a.sync_state_from_a2a(task_id, "completed")

    # Verify audit logging
    assert audit_a.count() >= 3  # create, delegate, sync
    integrity_a = audit_a.verify_integrity()
    assert integrity_a["integrity_intact"]

    print("Federation test passed!")


if __name__ == "__main__":
    asyncio.run(test_federation())
```
