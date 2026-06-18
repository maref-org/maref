# Integrating MAREF Governance with CrewAI

This guide shows how to apply MAREF governance to CrewAI crews, wrapping task execution with governance decisions, audit logging, and circuit breaker protection.

## Overview

MAREF governs *how* a CrewAI crew operates — what tasks it can execute, whether it needs human approval, and what gets logged for compliance. The integration happens by wrapping CrewAI's process execution with MAREF's governance pipeline.

```
Crew Creation
  │
  ▼
MAREF Governance (pre-flight)
  ├── Agent capability check via A2ADiscovery
  ├── Task risk assessment via SafetyGate
  ├── State machine: INIT -> OBSERVE -> ANALYZE
  │
  ▼
CrewAI Execution
  ├── Agent 1: research (governed tool calls)
  ├── Agent 2: analyze (governed tool calls)
  ├── Agent 3: summarize (governed tool calls)
  │
  ▼
MAREF Audit (post-flight)
  ├── HMAC-signed audit log
  ├── Trust score update
  └── Compliance report
```

## Installation

```bash
pip install maref crewai
```

## Step 1: Create a Governed Crew Wrapper

```python
"""governed_crew.py — MAREF-governed CrewAI crew."""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ASkillDefinition


class GovernedCrew:
    """Wraps a CrewAI crew with MAREF governance."""

    def __init__(self, crew_name: str = "governed-crew"):
        self._sm = GovernanceStateMachine()
        self._audit = AuditLogger(hmac_key="crewai-key")
        self._cb = CircuitBreaker()
        self._bridge = A2ABridge(
            state_machine=self._sm,
            audit_logger=self._audit,
            circuit_breaker=self._cb,
            agent_name=crew_name,
            agent_description="CrewAI crew under MAREF governance",
        )
        self._crew = None

    def attach_crew(self, crew) -> None:
        self._crew = crew

    def kickoff(self, inputs: dict | None = None) -> dict:
        task_id = self._bridge.create_task(
            str(inputs or {}),
            {"crew": self._crew.name if self._crew else "unknown"},
        )

        self._sm.transition(GovernanceState.OBSERVE, "crew kickoff starting")
        self._bridge.sync_state_from_a2a(task_id, "working")

        if self._cb.is_open:
            self._audit.log(
                event_type="governance_blocked",
                actor="governed-crew",
                action="kickoff_blocked",
                details="Circuit breaker is OPEN",
            )
            return {"error": "Circuit breaker open — crew execution blocked"}

        if self._crew is None:
            raise RuntimeError("No crew attached — call attach_crew() first")

        try:
            self._sm.transition(GovernanceState.ACT, "executing crew")
            result = self._crew.kickoff(inputs=inputs) if inputs else self._crew.kickoff()

            self._sm.transition(GovernanceState.VERIFY, "crew execution complete")
            self._bridge.sync_state_from_a2a(task_id, "completed")
            self._cb.record_success()

            return {
                "result": result,
                "task_id": task_id,
                "state": self._sm.current_state.name,
            }

        except Exception as e:
            self._cb.record_failure()
            self._sm.force_halt(f"Crew error: {e}")
            self._audit.log(
                event_type="crew_execution_error",
                actor="governed-crew",
                action="kickoff_failed",
                details=str(e),
            )
            return {"error": str(e), "task_id": task_id}

    @property
    def audit_trail(self) -> list[dict]:
        return [e.to_dict() for e in self._audit.read_all(max_entries=50)]

    @property
    def state(self) -> str:
        return self._sm.current_state.name


# Usage
def main():
    from crewai import Crew, Agent, Task, Process

    researcher = Agent(
        role="Researcher",
        goal="Find relevant information",
        backstory="Expert researcher",
        allow_delegation=False,
    )

    writer = Agent(
        role="Writer",
        goal="Write clear report",
        backstory="Expert writer",
        allow_delegation=False,
    )

    task1 = Task(
        description="Research the latest AI trends",
        expected_output="List of 3 key trends",
        agent=researcher,
    )

    task2 = Task(
        description="Write a summary of AI trends",
        expected_output="Brief report",
        agent=writer,
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[task1, task2],
        process=Process.sequential,
    )

    governed = GovernedCrew(crew_name="research-crew")
    governed.attach_crew(crew)
    result = governed.kickoff()
    print(f"Crew result: {result.get('result')}")
    print(f"Final governance state: {governed.state}")

    for entry in governed.audit_trail:
        print(f"  [{entry['event_type']}] {entry['actor']}: {entry['action']}")


if __name__ == "__main__":
    main()
```

## Step 2: Governance-Aware CrewAI Tools

Wrap CrewAI's tool calls with MAREF governance for fine-grained control:

```python
"""governed_tools.py — CrewAI tools with MAREF governance."""
from crewai.tools import BaseTool
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel


class GovernedTool(BaseTool):
    """Base class for CrewAI tools with governance."""

    governance: MCPGovernance = None
    agent_id: str = "crew-agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.governance is None:
            self.governance = MCPGovernance()

    def _run(self, **kwargs) -> str:
        # Pre-execution governance check
        result = self.governance.evaluate(
            tool_name=self.name,
            args=kwargs,
            trust_level=MCPTrustLevel.SEMI_TRUSTED,
            agent_id=self.agent_id,
        )

        if result.verdict.value == "deny":
            return f"GOVERNANCE_DENIED: {result.reason}"
        if result.verdict.value == "ask_user":
            return f"HITL_REQUIRED: {result.reason} — event_id={result.hitl_event_id}"

        return self._governed_run(**kwargs)

    def _governed_run(self, **kwargs) -> str:
        raise NotImplementedError


class GovernedFileReadTool(GovernedTool):
    name: str = "read_file"
    description: str = "Read file content with governance check"

    def _governed_run(self, file_path: str, **kwargs) -> str:
        with open(file_path) as f:
            return f.read()


class GovernedFileWriteTool(GovernedTool):
    name: str = "write_file"
    description: str = "Write file content with governance check"

    def _governed_run(self, file_path: str, content: str, **kwargs) -> str:
        with open(file_path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {file_path}"
```

## Step 3: Full Integration Test

```python
"""test_crewai_integration.py"""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.governance.types import GovernanceState


def test_governed_crew_lifecycle():
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    cb = CircuitBreaker()
    bridge = A2ABridge(sm, audit, cb, agent_name="test-crew")

    # Simulate crew lifecycle
    task_id = bridge.create_task("Research AI trends")
    assert task_id is not None

    sm.transition(GovernanceState.OBSERVE, "crew started")
    sm.transition(GovernanceState.ANALYZE, "analyzing inputs")
    sm.transition(GovernanceState.ACT, "agents executing")
    bridge.sync_state_from_a2a(task_id, "working")

    # Simulate errors
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()

    assert cb.is_open

    # Circuit breaker blocks further execution
    sm.force_halt("circuit breaker open")
    bridge.sync_state_from_a2a(task_id, "failed")

    assert sm.current_state == GovernanceState.HALT

    # Audit captured everything
    entries = audit.read_all(max_entries=10)
    assert len(entries) >= 4  # create, transitions, halt

    integrity = audit.verify_integrity()
    assert integrity["integrity_intact"]

    print("Governed CrewAI lifecycle test passed!")
```
