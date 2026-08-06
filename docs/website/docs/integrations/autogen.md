---
sidebar_position: 3
title: AutoGen Integration
description: Apply MAREF governance to AutoGen agents
---

# Integrating MAREF Governance with AutoGen

This guide shows how to apply MAREF governance to AutoGen agents, wrapping conversations with audit logging, risk assessment, and circuit breaker protection.

## Overview

AutoGen enables multi-agent conversations with flexible agent teams. MAREF governance adds message-level observation, governance injection, and comprehensive audit trails to every agent interaction.

## Basic Setup

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision

team = RoundRobinGroupChat(agents=[agent1, agent2])
adapter = AutoGenAdapter(team)

async for msg in adapter.observe_stream(team.run_stream(task="...")):
    if isinstance(msg, TaskResult):
        break

msg = {"content": "rm -rf /important"}
msg = adapter.inject_governance(msg, GovernanceDecision.BLOCK, "destructive command")
```

## Key Features

- Real-time message stream observation
- Governance injection into agent messages
- Automatic safety checks on all content
- Integration with MAREF's state machine and audit logger

## Complete Example

```python
"""full_autogen_integration.py"""
import asyncio
from autogen_agentchat.teams import RoundRobinGroupChat
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision


async def run_governed_conversation():
    # Create agents
    agent1 = ...  # your AutoGen agent
    agent2 = ...  # your AutoGen agent

    # Wrap with MAREF governance
    team = RoundRobinGroupChat(agents=[agent1, agent2])
    adapter = AutoGenAdapter(team)

    # Observe all messages with governance
    async for msg in adapter.observe_stream(team.run_stream(task="Analyze data")):
        if isinstance(msg, TaskResult):
            break
        decision = adapter.inject_governance(msg, GovernanceDecision.AUDIT, "default")
        if decision == GovernanceDecision.BLOCK:
            print(f"Blocked message: {msg}")

    # Verify audit trail
    print(f"Audit entries: {adapter.get_audit_count()}")

asyncio.run(run_governed_conversation())
```

## HITL Integration

```python
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision

adapter = AutoGenAdapter(team)
msg = {"content": "delete /important/data"}
decision = adapter.inject_governance(msg, GovernanceDecision.BLOCK, "destructive command")
if decision == GovernanceDecision.BLOCK:
    print(f"Message blocked. Reason: destructive command")
    # HITL flow: human reviews and overrides
    adapter.override_decision(msg, GovernanceDecision.ALLOW, reviewer="admin")
```

## Circuit Breaker Protection

```python
from maref.governance.circuit_breaker import CircuitBreaker

adapter = AutoGenAdapter(team, circuit_breaker=CircuitBreaker(max_consecutive_failures=3))
# If agent fails 3+ times consecutively, AutoGenAdapter will stop forwarding messages
```

See the [GitHub source](https://github.com/maref-org/maref/blob/main/docs/integrations/autogen.md) for the latest integration code.
