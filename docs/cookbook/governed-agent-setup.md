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

# Create governance components
state_machine = GovernanceStateMachine()
audit_logger = AuditLogger()  # in-memory mode
circuit_breaker = CircuitBreaker(
    max_depth=3,
    max_consecutive_failures=5,
    cooldown_seconds=30.0,
)
```

## Step 2: Attach the Eight Trigrams Trust Engine

```python
from maref.recursive.eight_trigrams_governance import EightTrigramsGovernance

# Start at DUI (interconnection) with trust score 0.65
trigrams = EightTrigramsGovernance(
    agent_id="my-agent-1",
    initial_trust=0.65,
)

# Trust score determines current trigram automatically
trigrams.auto_transition(0.72)
print(trigrams.current_trigram)  # e.g., TrigramsGovernance.DUI

# On violation, trust decreases
trigrams.update_trust_and_adapt(new_trust=0.72, violation=True)
# trust drops to 0.62, may transition to lower trigram
```

## Step 3: Wire Up the Safety Gate

```python
from maref.recursive.safety_gate_v2 import SafetyGateV2

safety_gate = SafetyGateV2()

# Validate a task decomposition before execution
assessment = safety_gate.validate_decomposition(
    subtask_count=5,
    capabilities=["data_query", "write_file"],
)
if assessment.blocked:
    print(f"Task blocked: {assessment.reason}")
    # Handle: reduce subtasks, add missing capabilities

# Validate an agent handoff
assessment = safety_gate.validate_handoff(
    from_agent="agent-a",
    to_agent="agent-b",
    from_capabilities=["read"],
    to_capabilities=["read", "write", "exec"],
)
if assessment.threat_detected:
    print(f"Handoff blocked: {assessment.reason}")
```

## Step 4: Add the Audit Logger with HMAC

```python
# File-based audit with HMAC signing
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
print(f"Audit entry: {entry.id}, signature: {entry.hmac_signature}")

# Verify integrity later
result = file_audit.verify_integrity()
print(f"Integrity intact: {result['integrity_intact']}")
```

## Step 5: Connect the A2A Bridge

```python
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_discovery import A2ADiscovery

# Wrap governance in A2A bridge
bridge = A2ABridge(
    state_machine=state_machine,
    audit_logger=audit_logger,
    circuit_breaker=circuit_breaker,
    agent_name="my-agent-1",
    agent_description="My first MAREF-governed agent",
)

# Register with discovery service
discovery = A2ADiscovery(health_check_interval=60.0)
discovery.register_agent(
    agent_id="my-agent-1",
    agent_url="http://localhost:8000",
    capabilities=["maref-governance", "data_query", "report_gen"],
)

# Build A2A agent card for external discovery
card = bridge.build_agent_card(base_url="http://localhost:8000")
```

## Step 6: Create and Govern a Task

```python
import asyncio

# Create a governed task
task_id = bridge.create_task(
    task_description="Analyze monthly sales data",
    context={"priority": "high", "source": "dashboard"},
)

# Check task status
task = bridge.get_task(task_id)
print(f"Task state: {task.a2a_state}, MAREF state: {task.maref_state}")

# Simulate task progression with state sync
bridge.sync_state_from_a2a(task_id, "working")
bridge.sync_state_from_a2a(task_id, "completed")

# List all governed tasks
tasks = bridge.list_governed_tasks()
for t in tasks:
    print(f"{t['task_id']}: {t['maref_state']}")

# Force halt if something goes wrong
bridge.force_halt_task(task_id, reason="data integrity concern")
```

## Step 7: Run the State Machine

```python
# Manual state transitions
sm = GovernanceStateMachine()

sm.transition(GovernanceState.OBSERVE, "start monitoring")
sm.transition(GovernanceState.ANALYZE, "data collected")
sm.transition(GovernanceState.EVALUATE, "analysis complete")
sm.transition(GovernanceState.DECIDE, "evaluation complete")

# Force stabilize if entropy too high
if sm.current_entropy >= 3:
    sm.force_stabilize("entropy threshold exceeded")

# Force halt in emergency
sm.force_halt("manual override")

# Snapshot and restore
snap = sm.snapshot()
sm2 = GovernanceStateMachine.restore(snap)
print(sm2.current_state)  # HALT
```

## Step 8: Full Integration Test

```python
import pytest

def test_governed_agent_lifecycle():
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    cb = CircuitBreaker()
    trigrams = EightTrigramsGovernance(agent_id="test-agent")
    bridge = A2ABridge(sm, audit, cb, agent_name="test")

    # Agent starts in DUI with trust 0.65
    assert trigrams.current_trigram.value == "dui"
    assert trigrams.trust_score == 0.65

    # Create task
    task_id = bridge.create_task("Test task")
    assert task_id is not None

    # State machine starts in INIT
    assert sm.current_state == GovernanceState.INIT

    # Transition through lifecycle
    assert sm.transition(GovernanceState.OBSERVE, "start")
    assert sm.transition(GovernanceState.ANALYZE, "analyze")
    assert sm.transition(GovernanceState.EVALUATE, "evaluate")
    assert sm.transition(GovernanceState.DECIDE, "decide")
    assert sm.transition(GovernanceState.ACT, "act")
    assert sm.transition(GovernanceState.VERIFY, "verify")
    assert sm.transition(GovernanceState.STABILIZE, "stabilize")
    assert sm.transition(GovernanceState.REPORT, "report")

    # Audit log has entries
    assert audit.count() > 0

    # Integrity check passes
    result = audit.verify_integrity()
    assert result["integrity_intact"]

    # Circuit breaker is closed
    assert not cb.is_open
```

## Complete Setup Script

```python
"""Complete governed agent setup."""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_discovery import A2ADiscovery
from maref.integration.a2a_types import A2ASkillDefinition


def create_governed_agent(
    agent_id: str,
    agent_url: str = "http://localhost:8000",
    audit_path: str = "./audit/maref.jsonl",
    hmac_key: str | None = None,
) -> tuple[GovernanceStateMachine, AuditLogger, A2ABridge, A2ADiscovery]:
    state_machine = GovernanceStateMachine()
    audit_logger = AuditLogger(
        log_path=audit_path,
        hmac_key=hmac_key,
    )
    circuit_breaker = CircuitBreaker()

    bridge = A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
        circuit_breaker=circuit_breaker,
        agent_name=agent_id,
        agent_description=f"MAREF-governed agent: {agent_id}",
    )

    # Register custom capabilities
    bridge.register_capability(
        A2ASkillDefinition(
            id="custom-analysis",
            name="Data Analysis",
            description="Analyze structured data and generate reports",
            tags=["analysis", "reporting"],
            examples=["Analyze quarterly sales trends"],
        )
    )

    discovery = A2ADiscovery()
    discovery.register_agent(
        agent_id=agent_id,
        agent_url=agent_url,
        capabilities=["maref-governance", "custom-analysis"],
    )

    return state_machine, audit_logger, bridge, discovery


if __name__ == "__main__":
    sm, audit, bridge, discovery = create_governed_agent("prod-agent-1")
    print(f"Agent '{bridge._name}' ready with {len(bridge._capabilities)} capabilities")
    print(f"Discovery has {len(discovery.list_agents())} registered agents")
    print(f"State machine at: {sm.current_state.name}")
    print(f"Circuit breaker: {'CLOSED' if not audit._hmac_key else 'HMAC ready'}")
```
