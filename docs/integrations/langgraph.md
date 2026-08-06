# Integrating MAREF Governance with LangGraph

This guide shows how to use MAREF governance with a LangGraph agent, wrapping it with the A2A bridge for governance enforcement.

## Overview

MAREF sits *above* LangGraph, adding governance (state machine, audit, circuit breaker) to LangGraph agent runs. The integration happens via the `A2ABridge`, which wraps any agent (including LangGraph) with governance before and after each step.

```
User Request
  │
  ▼
MAREF Governance
  ├── GovernanceStateMachine (INIT -> OBSERVE -> ANALYZE -> ...)
  ├── AuditLogger (HMAC-signed)
  ├── CircuitBreaker (failure detection)
  ├── SafetyGate (threat detection)
  │
  ▼
LangGraph Agent
  ├── StateGraph.compile()
  ├── Node execution
  └── Tool calls (via MCP with governance)
  │
  ▼
MAREF Audit (post-execution)
```

## Installation

```bash
pip install maref langgraph langchain
```

## Step 1: Create a LangGraph Agent

```python
"""langgraph_agent.py — Standard LangGraph agent."""
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage


class AgentState(TypedDict):
    messages: list
    next_step: str


def call_model(state: AgentState) -> dict:
    """Simulate model call (replace with your LLM)."""
    messages = state["messages"]
    last = messages[-1]
    if isinstance(last, HumanMessage):
        return {
            "messages": [AIMessage(content=f"Processed: {last.content}")],
            "next_step": "end",
        }
    return {"messages": messages, "next_step": "end"}


def route_decision(state: AgentState) -> str:
    return state.get("next_step", "end")


# Compile graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    route_decision,
    {"end": END},
)
graph = workflow.compile()


def run_agent(input_text: str) -> dict[str, Any]:
    result = graph.invoke({
        "messages": [HumanMessage(content=input_text)],
        "next_step": "agent",
    })
    return {"output": result["messages"][-1].content}
```

## Step 2: Wrap with MAREF Governance

```python
"""governed_langgraph.py — LangGraph agent with MAREF governance."""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ASkillDefinition


class GovernedLangGraphAgent:
    """LangGraph agent with MAREF governance overlay."""

    def __init__(self, agent_name: str = "langgraph-agent"):
        # Governance components
        self._sm = GovernanceStateMachine()
        self._audit = AuditLogger(hmac_key="langgraph-key")
        self._cb = CircuitBreaker()

        # A2A bridge wraps governance
        self._bridge = A2ABridge(
            state_machine=self._sm,
            audit_logger=self._audit,
            circuit_breaker=self._cb,
            agent_name=agent_name,
            agent_description="LangGraph agent under MAREF governance",
        )

        # Internal LangGraph runner
        self._graph = None

        # Register capability
        self._bridge.register_capability(
            A2ASkillDefinition(
                id="langgraph-reasoning",
                name="LangGraph Reasoning",
                description="Multi-step reasoning using LangGraph state machine",
                tags=["langgraph", "reasoning", "chain-of-thought"],
                examples=["Solve multi-step research questions"],
            )
        )

    def attach_graph(self, graph) -> None:
        self._graph = graph

    def run(self, input_text: str, context: dict | None = None) -> dict:
        # 1. Create governed task
        task_id = self._bridge.create_task(input_text, context)

        # 2. Transition through governance lifecycle
        self._sm.transition(GovernanceState.OBSERVE, "starting langgraph run")
        self._sm.transition(GovernanceState.ANALYZE, "input received")

        # 3. Circuit breaker check
        if self._cb.is_open:
            self._audit.log(
                event_type="circuit_breaker_blocked",
                actor=self._bridge._name,
                action="blocked_langgraph_run",
                details="Circuit breaker is OPEN",
            )
            return {"error": "Circuit breaker open", "task_id": task_id}

        try:
            # 4. Execute LangGraph
            self._sm.transition(GovernanceState.ACT, "executing langgraph")
            self._bridge.sync_state_from_a2a(task_id, "working")

            if self._graph is None:
                raise RuntimeError("No graph attached — call attach_graph() first")

            from langchain_core.messages import HumanMessage
            result = self._graph.invoke({
                "messages": [HumanMessage(content=input_text)],
                "next_step": "agent",
            })

            output = result["messages"][-1].content

            # 5. Verify and report
            self._sm.transition(GovernanceState.VERIFY, "langgraph completed")
            self._bridge.sync_state_from_a2a(task_id, "completed")

            self._cb.record_success()

            return {"output": output, "task_id": task_id}

        except Exception as e:
            self._cb.record_failure()
            self._sm.force_halt(f"LangGraph error: {e}")
            self._audit.log(
                event_type="langgraph_error",
                actor=self._bridge._name,
                action="run_failed",
                details=str(e),
            )
            return {"error": str(e), "task_id": task_id}

    @property
    def state(self) -> str:
        return self._sm.current_state.name

    @property
    def audit_trail(self) -> list:
        return [e.to_dict() for e in self._audit.read_all(max_entries=20)]


# Usage
def main():
    from langgraph_agent import graph  # from step 1

    agent = GovernedLangGraphAgent(agent_name="research-agent")
    agent.attach_graph(graph)

    result = agent.run("Analyze the impact of climate change on agriculture")
    print(f"Result: {result.get('output')}")
    print(f"Final state: {agent.state}")

    # Check audit
    for entry in agent.audit_trail:
        print(f"  [{entry['event_type']}] {entry['action']}: {entry['details']}")


if __name__ == "__main__":
    main()
```

## Step 3: Full Integration Test

```python
"""test_langgraph_integration.py"""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from langgraph.graph import StateGraph, END
from typing import TypedDict
from langchain_core.messages import HumanMessage, AIMessage


class TestState(TypedDict):
    messages: list
    next_step: str


def test_node(state: TestState) -> dict:
    return {
        "messages": [AIMessage(content="processed")],
        "next_step": "end",
    }


def router(state: TestState) -> str:
    return state.get("next_step", "end")


def test_governed_langgraph():
    # Build mini graph
    builder = StateGraph(TestState)
    builder.add_node("agent", test_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", router, {"end": END})
    graph = builder.compile()

    # Wire governance
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    cb = CircuitBreaker()
    bridge = A2ABridge(sm, audit, cb, agent_name="test-langgraph")

    # Execute through governance
    task_id = bridge.create_task("Test input")
    sm.transition("observe", "start")
    bridge.sync_state_from_a2a(task_id, "working")

    result = graph.invoke({
        "messages": [HumanMessage(content="Test")],
        "next_step": "agent",
    })

    bridge.sync_state_from_a2a(task_id, "completed")
    sm.transition("verify", "langgraph done")

    # Verify governance tracked everything
    assert len(audit.read_all(max_entries=10)) > 0
    assert not cb.is_open

    print("Governed LangGraph test passed!")
```

## Key Points

- MAREF governance wraps LangGraph execution, not replaces it
- Each LangGraph run becomes a MAREF governed task with full audit trail
- Circuit breaker prevents runaway LangGraph loops
- A2A bridge allows other agents to delegate tasks to the LangGraph agent
- Use `sync_state_from_a2a` to keep LangGraph status visible to the federation
