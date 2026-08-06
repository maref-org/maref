---
sidebar_position: 1
title: LangGraph Integration
description: Apply MAREF governance to LangGraph agents
---

# Integrating MAREF Governance with LangGraph

This guide shows how to use MAREF governance with a LangGraph agent, wrapping it with the A2A bridge for governance enforcement.

## Overview

LangGraph provides stateful, multi-step agent workflows. MAREF governance adds safety gates, audit logging, circuit breaker protection, and human-in-the-loop oversight to every graph node transition.

## Basic Setup

```python
from langgraph.graph import StateGraph
from sidecar.adapters.langgraph import LangGraphAdapter

graph = StateGraph(MyState)
graph.add_node("process", process_node)
graph.add_edge("process", "human_review")

adapter = LangGraphAdapter(graph)

decision, reason = adapter.evaluate_node_safety("human_review", current_state)
if decision == "block":
    print(f"Transition blocked: {reason}")
else:
    adapter.observe_transition("human_review", from_state="process")
    state = adapter.inject_governance("human_review", current_state, decision, reason)
```

## Key Features

- Node-level safety evaluation before graph transitions
- Governance injection at any graph node
- Audit logging of every node transition
- Circuit breaker integration for fault isolation

## Complete Example

```python
"""full_langgraph_integration.py"""
from langgraph.graph import StateGraph
from sidecar.adapters.langgraph import LangGraphAdapter


def run_governed_langgraph():
    graph = StateGraph(MyState)
    graph.add_node("process", process_node)
    graph.add_node("human_review", review_node)
    graph.add_edge("process", "human_review")

    adapter = LangGraphAdapter(graph)

    current_state = MyState(data="Processed output")

    # Evaluate node safety before transition
    decision, reason = adapter.evaluate_node_safety("human_review", current_state)
    if decision == "block":
        print(f"Transition blocked: {reason}")
        return

    # Inject governance context
    governed_state = adapter.inject_governance(
        "human_review", current_state, decision, reason,
    )

    # Observe the transition
    adapter.observe_transition("human_review", from_state="process")

    # Continue graph execution
    result = graph.invoke(governed_state)
    print(f"Graph completed: {result}")


run_governed_langgraph()
```

## HITL via LangGraph

```python
from sidecar.adapters.langgraph import LangGraphAdapter

adapter = LangGraphAdapter(graph)

# Human-in-the-loop at specific nodes
# Governed state includes HITL metadata
state = adapter.inject_governance(
    "deploy_node",
    current_state,
    "ask_user",
    "Production deployment requires human approval",
)
# state now contains hitl_event_id for tracking
```

## State Machine Integration

```python
# LangGraph state is synchronized with MAREF's 10-state machine
# Each graph node maps to a governance state:
#   process  -> ANALYZE
#   review   -> EVALUATE
#   decide   -> DECIDE
#   execute  -> ACT
#   verify   -> VERIFY
```

See the [GitHub source](https://github.com/maref-org/maref/blob/main/docs/integrations/langgraph.md) for the latest integration code.
