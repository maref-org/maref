---
sidebar_position: 2
title: CrewAI Integration
description: Apply MAREF governance to CrewAI crews
---

# Integrating MAREF Governance with CrewAI

This guide shows how to apply MAREF governance to CrewAI crews, wrapping task execution with governance decisions, audit logging, and circuit breaker protection.

## Overview

CrewAI enables collaborative AI agent teams. MAREF governance adds task-level safety evaluation, agent activity observation, and tamper-evident audit trails to every crew operation.

## Basic Setup

```python
from crewai import Crew, Agent, Task
from sidecar.adapters.crewai import CrewAIAdapter

crew = Crew(agents=[agent], tasks=[task])
adapter = CrewAIAdapter(crew)

decision, reason = adapter.evaluate_task_safety(task.description)
if decision == "block":
    print(f"Task blocked: {reason}")
else:
    task = adapter.inject_governance(task, decision, reason)
    crew.kickoff()

adapter.observe_agent_activity(agent.role, task.description)
state = await adapter.get_state(AgentId(name=agent.role, namespace="crewai"))
```

## Key Features

- Pre-execution task safety evaluation
- Post-execution agent activity observation
- Governance injection into task context
- Automatic state machine integration

## Complete Example

```python
"""full_crewai_integration.py"""
from crewai import Crew, Agent, Task
from sidecar.adapters.crewai import CrewAIAdapter


def run_governed_crew():
    agent = Agent(role="Analyst", goal="Analyze data", backstory="Data analyst")
    task = Task(description="Analyze Q2 revenue data", agent=agent)
    crew = Crew(agents=[agent], tasks=[task])

    adapter = CrewAIAdapter(crew)

    # Evaluate safety before execution
    decision, reason = adapter.evaluate_task_safety(task.description)
    if decision == "block":
        print(f"Task blocked: {reason}")
        return

    # Inject governance context
    task = adapter.inject_governance(task, decision, reason)

    # Execute with observation
    result = crew.kickoff()
    adapter.observe_agent_activity(agent.role, task.description)

    # Verify audit
    state = adapter.get_state(agent.role)
    print(f"Agent state: {state}")
    print(f"Task completed: {result}")


run_governed_crew()
```

## HITL with CrewAI

```python
from sidecar.adapters.crewai import CrewAIAdapter

adapter = CrewAIAdapter(crew)
decision, reason = adapter.evaluate_task_safety("Deploy to production")

if decision == "ask_user":
    event_id = adapter.request_human_approval("deploy_to_prod", "Deploy to production env")
    print(f"HITL event: {event_id}, awaiting approval...")
    # Human approves via dashboard/API
    adapter.approve_operation(event_id, reviewer="ops-admin")
```

## Multi-Crew Governance

```python
# Single adapter for multiple crews
adapter = CrewAIAdapter(crew1)
adapter.watch(crew2)
adapter.watch(crew3)

# All crews share the same governance state machine and audit log
```

See the [GitHub source](https://github.com/maref-org/maref/blob/main/docs/integrations/crewai.md) for the latest integration code.
