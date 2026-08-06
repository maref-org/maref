---
sidebar_position: 2
title: A2A Federation
description: Multi-agent communication via A2A protocol
---

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

## Step 1: Agent A (Task Delegator)

```python
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_discovery import A2ADiscovery

state_machine_a = GovernanceStateMachine()
audit_a = AuditLogger(hmac_key="agent-a-key")
cb_a = CircuitBreaker()
bridge_a = A2ABridge(state_machine_a, audit_a, cb_a, agent_name="agent-alpha")
discovery_a = A2ADiscovery()
client_a = A2AClient(timeout=30.0)
```

## Step 2: Agent B (Task Worker)

```python
from fastapi import FastAPI
from maref.integration.a2a_server import create_a2a_router

bridge_b = A2ABridge(
    GovernanceStateMachine(), AuditLogger(hmac_key="agent-b-key"),
    CircuitBreaker(), agent_name="agent-beta",
)
app_b = FastAPI(title="Agent Beta")
app_b.include_router(create_a2a_router(bridge_b, signing_key="my-signing-key"))
```

## Step 3: Run Both Agents

Terminal 1:
```bash
python agent_b.py
```

Terminal 2:
```bash
python agent_a.py
```

## Step 4: Monitor Audit Trails

```python
# Verify audit chain integrity on both agents
integrity_a = audit_a.verify_integrity()
integrity_b = audit_b.verify_integrity()
print(f"Agent A integrity intact: {integrity_a['integrity_intact']}")
print(f"Agent B integrity intact: {integrity_b['integrity_intact']}")
```

See the [full cookbook on GitHub](https://github.com/maref-org/maref/blob/main/docs/cookbook/a2a-federation.md) for the complete federation test script.
