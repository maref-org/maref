# Cookbook: Disaster Recovery — Circuit Breaker, Saga, Self-Healing

This guide covers circuit breaker patterns for fault isolation, saga orchestration for distributed transactions, and self-healing recovery for MAREF governance agents.

## Scenario

An MCP backend is failing, causing cascading governance failures. You need to isolate the fault, orchestrate recovery across agents, and enable self-healing.

## Prerequisites

```bash
pip install maref
```

## Step 1: Circuit Breaker Configuration

```python
from maref.governance.circuit_breaker import CircuitBreaker

cb = CircuitBreaker(
    max_depth=10,               # Max delegation depth
    max_consecutive_failures=5, # Trip after 5 failures
    cooldown_seconds=30.0,      # Wait 30s before half-open
)

# Trip on failure
for i in range(6):
    cb.record_failure()

print(f"Is open: {cb.is_open}")  # True
print(f"State: {cb.state}")      # OPEN

# Check depth
if not cb.check_depth(15):
    print("Depth exceeded — blocking call")

# Half-open after cooldown
import time
time.sleep(30)
print(f"State: {cb.state}")  # HALF_OPEN

# Recovery
cb.record_success()
print(f"State: {cb.state}")  # CLOSED
```

## Step 2: Circuit Breaker Monitor (Per-Tool)

```python
from maref.integration.mcp_governance import MCPCircuitBreakerMonitor

cb_monitor = MCPCircuitBreakerMonitor(
    max_error_rate=0.3,       # Trip at 30% error rate
    max_avg_latency_ms=30000, # Trip if latency > 30s
    min_calls_for_metrics=3,  # Minimum samples before evaluation
)

# Simulate failing calls
for i in range(10):
    cb_monitor.record_call("faulty_tool", latency=0.5, success=False)

should_trip, reason = cb_monitor.should_trip("faulty_tool")
print(f"Trip: {should_trip}, Reason: {reason}")

# Reset after recovery
cb_monitor.reset_tool("faulty_tool")
```

## Step 3: Saga Orchestration

```python
"""saga_orchestrator.py — Compensating transactions for multi-agent ops."""


class SagaStep:
    def __init__(self, name: str, action, compensate):
        self.name = name
        self.action = action
        self.compensate = compensate


class SagaOrchestrator:
    def __init__(self):
        self._history: list[str] = []

    def execute(self, steps: list[SagaStep], context: dict) -> bool:
        completed = []
        for step in steps:
            try:
                step.action(context)
                completed.append(step)
                self._history.append(f"{step.name}: committed")
            except Exception as e:
                self._history.append(f"{step.name}: failed — {e}")
                # Compensate in reverse order
                for prev in reversed(completed):
                    try:
                        prev.compensate(context)
                        self._history.append(f"{prev.name}: compensated")
                    except Exception as ce:
                        self._history.append(f"{prev.name}: compensate failed — {ce}")
                return False
        return True


# Example usage
def deploy_action(ctx):
    print(f"Deploying {ctx['version']} to {ctx['env']}")


def deploy_compensate(ctx):
    print(f"Rolling back {ctx['version']} from {ctx['env']}")


saga = SagaOrchestrator()
success = saga.execute([
    SagaStep("deploy", deploy_action, deploy_compensate),
], {"version": "v2.0", "env": "production"})
print(f"Saga success: {success}")
```

## Step 4: Self-Healing Recovery

```python
"""self_healing.py — Automatic agent recovery."""
from maref.governance.state_machine import GovernanceStateMachine, GovernanceState
from maref.governance.circuit_breaker import CircuitBreaker


class SelfHealingRecovery:
    def __init__(
        self,
        state_machine: GovernanceStateMachine,
        circuit_breaker: CircuitBreaker,
        max_retries: int = 3,
    ):
        self._sm = state_machine
        self._cb = circuit_breaker
        self._max_retries = max_retries
        self._attempts: dict[str, int] = {}

    def handle_failure(self, agent_id: str, error: str) -> str:
        attempts = self._attempts.get(agent_id, 0) + 1
        self._attempts[agent_id] = attempts

        if attempts >= self._max_retries:
            self._sm.force_halt(f"Max retries ({self._max_retries}) exceeded: {error}")
            return "HALT"

        self._cb.record_failure()
        if self._cb.is_open:
            self._sm.transition(GovernanceState.STABILIZE, f"CB open: {error}")
            return "STABILIZE"

        self._sm.transition(GovernanceState.OBSERVE, f"Retry {attempts}: {error}")
        return f"RETRY ({attempts}/{self._max_retries})"


# Usage
sm = GovernanceStateMachine()
cb = CircuitBreaker()
recovery = SelfHealingRecovery(sm, cb)

print(recovery.handle_failure("agent-42", "Connection timeout"))
print(recovery.handle_failure("agent-42", "Connection timeout"))
print(recovery.handle_failure("agent-42", "Connection timeout"))  # HALT
```

## Step 5: Verify

```python
cb = CircuitBreaker()
for i in range(5):
    cb.record_failure()
assert cb.is_open
assert cb.state == "open"

# Recovery
cb.record_success()
assert cb.state == "closed"

# Self-healing saga test
saga = SagaOrchestrator()
steps = [
    SagaStep("step1", lambda ctx: None, lambda ctx: None),
    SagaStep("step2", lambda ctx: (_ for _ in ()).throw(Exception("fail")), lambda ctx: None),
]
assert not saga.execute(steps, {})
assert "step2: failed" in saga._history[-2]
assert "step1: compensated" in saga._history[-1]
print("All DR tests passed!")
```
