---
sidebar_position: 1
title: Governed Agent Setup
description: Create a MAREF-governed agent from scratch
---

# Cookbook: Setting Up a Governed Agent

This guide walks through creating a MAREF-governed agent from scratch, including the state machine, audit logger, circuit breaker, and A2A registration.

## Prerequisites

```bash
pip install maref
# or from source:
pip install -e ".[dev]"
```

## Step 1: Create the Governance Core

```python
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState

state_machine = GovernanceStateMachine()
audit_logger = AuditLogger()
circuit_breaker = CircuitBreaker(
    max_depth=3,
    max_consecutive_failures=5,
    cooldown_seconds=30.0,
)
```

## Step 2: Attach the Eight Trigrams Trust Engine

```python
from maref.recursive.eight_trigrams_governance import EightTrigramsGovernance

trigrams = EightTrigramsGovernance(
    agent_id="my-agent-1",
    initial_trust=0.65,
)
trigrams.auto_transition(0.72)
print(trigrams.current_trigram)
```

## Step 3: Wire Up the Safety Gate

```python
from maref.recursive.safety_gate_v2 import SafetyGateV2

safety_gate = SafetyGateV2()
assessment = safety_gate.validate_decomposition(
    subtask_count=5,
    capabilities=["data_query", "write_file"],
)
if assessment.blocked:
    print(f"Task blocked: {assessment.reason}")
```

## Step 4: Add the Audit Logger with HMAC

```python
from pathlib import Path

file_audit = AuditLogger(
    log_path=Path("./audit/maref.jsonl"),
    hmac_key="my-production-hmac-key",
)
entry = file_audit.log(
    event_type="governance_decision",
    actor="my-agent-1",
    action="transition",
    details="INIT -> OBSERVE",
    metadata={"from_state": "INIT", "to_state": "OBSERVE"},
)
```

## Step 5: Connect the A2A Bridge

```python
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_discovery import A2ADiscovery

bridge = A2ABridge(
    state_machine=state_machine,
    audit_logger=audit_logger,
    circuit_breaker=circuit_breaker,
    agent_name="my-agent-1",
    agent_description="My first MAREF-governed agent",
)

discovery = A2ADiscovery(health_check_interval=60.0)
discovery.register_agent(
    agent_id="my-agent-1",
    agent_url="http://localhost:8000",
    capabilities=["maref-governance", "data_query", "report_gen"],
)
```

## Step 6: Create and Govern a Task

```python
task_id = bridge.create_task(
    "Analyze monthly sales data",
    {"priority": "high", "source": "dashboard"},
)
bridge.sync_state_from_a2a(task_id, "working")
bridge.sync_state_from_a2a(task_id, "completed")
```

## Step 7: Full Integration Test

```python
def test_governed_agent_lifecycle():
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    cb = CircuitBreaker()
    trigrams = EightTrigramsGovernance(agent_id="test-agent")
    bridge = A2ABridge(sm, audit, cb, agent_name="test")

    assert trigrams.current_trigram.value == "dui"
    task_id = bridge.create_task("Test task")
    assert task_id is not None
    assert sm.current_state == GovernanceState.INIT
    assert sm.transition(GovernanceState.OBSERVE, "start")
    assert sm.transition(GovernanceState.REPORT, "report")
    assert audit.count() > 0
    assert audit.verify_integrity()["integrity_intact"]
```

See the [full cookbook on GitHub](https://github.com/maref-org/maref/blob/main/docs/cookbook/governed-agent-setup.md) for the complete setup script.
