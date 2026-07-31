# MAREF Governance for LangGraph Workflows

> **Case study code**: How to wrap a LangGraph-style state graph with MAREF's governance primitives — no LLM API key required for governance validation.

## Quick Start

```bash
# Install MAREF (and langgraph for production use)
pip install maref
pip install langgraph  # optional: only needed for real graph execution

# Run the demo (no API key needed — governance runs locally)
cd docs/examples/langgraph-governance
python demo.py
```

## What This Demonstrates

This example shows how MAREF's governance layer wraps a LangGraph-style `StateGraph` to provide:

| Governance Primitive | Graph Hook | What It Guards Against |
|---------------------|------------|----------------------|
| **SafetyGateV2** | Pre-flight validation | Subtask explosion, dangerous capabilities |
| **CircuitBreaker** | Wraps `invoke()` | Excessive depth, consecutive failures |
| **SubgoalInterceptor** | Per-node step callback | Goal hijacking, control subgoals, delegation creep |
| **BehaviorMonitor** | Per-node step callback | Rogue node detection (3-sigma anomaly) |
| **GovernanceStateMachine** | Tracks graph lifecycle | 10-state Gray Code FSM (INIT→...→HALT) |
| **Audit trail** | All governance events | Tamper-evident SHA-256 hash chain |

## Demo Scenarios

The demo (`demo.py`) runs 4 scenarios:

1. **Benign graph** — A normal search + write graph. Governance passes, graph executes.
2. **Dangerous graph** — A node whose description contains "halt" and "delete". Governance blocks it in pre-flight.
3. **Goal hijack** — A node reasons about "bypassing safety constraints" and "elevating permissions". SubgoalInterceptor HALTs execution.
4. **Behavior anomaly** — A node spikes to 100x normal ops count. BehaviorMonitor detects the 3-sigma anomaly.

## Files

| File | Description |
|------|-------------|
| [`maref_langgraph_governor.py`](maref_langgraph_governor.py) | The `MAREFGovernedGraph` adapter class |
| [`demo.py`](demo.py) | Runnable demo with 4 scenarios (uses mock LangGraph objects) |

## Integration Architecture

```
┌─────────────────────────────────────────────────┐
│            MAREFGovernedGraph                     │
│                                                   │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │ Governance  │  │  StateGraph              │  │
│  │  StateMachine│  │  ┌──────┐  ┌──────┐     │  │
│  │  (10-state  │  │  │ node │  │ node │     │  │
│  │   Gray Code)│  │  │  A   │  │  B   │     │  │
│  └──────┬──────┘  │  └──┬───┘  └──┬───┘     │  │
│         │         │     │         │          │  │
│  ┌──────┴──────┐  │     │ step_simulator      │  │
│  │CircuitBreaker│  │     │         │          │  │
│  │  (depth +   │  │     ▼         ▼          │  │
│  │   failures) │  │  ┌──────────────────┐    │  │
│  └──────┬──────┘  │  │SubgoalInterceptor│    │  │
│         │         │  │  + BehaviorMonitor│   │  │
│  ┌──────┴──────┐  │  └────────┬─────────┘    │  │
│  │ SafetyGateV2│  │           │              │  │
│  │ (pre-flight)│  │           ▼              │  │
│  └──────┬──────┘  │  ┌──────────────────┐    │  │
│         │         │  │  Audit Trail     │    │  │
│         ▼         │  │  (SHA-256 chain) │    │  │
│  ┌─────────────┐  │  └──────────────────┘    │  │
│  │ validate()  │  │                          │  │
│  │ invoke()    │  │                          │  │
│  └─────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Using with Real LangGraph

Replace the mock objects in `demo.py` with real LangGraph classes:

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from maref_langgraph_governor import MAREFGovernedGraph, GovernanceConfig

class GraphState(TypedDict):
    query: str
    findings: list[str]
    report: str

def search_fn(state: GraphState) -> dict:
    return {"findings": ["finding-1", "finding-2"]}

def write_fn(state: GraphState) -> dict:
    return {"report": "Final report"}

graph = StateGraph(GraphState)
graph.add_node("search", search_fn)
graph.add_node("write", write_fn)
graph.add_edge(START, "search")
graph.add_edge("search", "write")
graph.add_edge("write", END)

# Wrap with MAREF governance
governed = MAREFGovernedGraph(graph, config=GovernanceConfig(max_recursion_depth=3))

# Pre-flight governance check (runs without LLM)
report = governed.validate()
print(report.summary())

if report.passed:
    # Run with governance enforcement (LLM required inside nodes)
    result = governed.invoke({"query": "agent governance"})
    governed.print_governance_report()
```

## Governance Configuration

```python
config = GovernanceConfig(
    max_recursion_depth=3,          # CircuitBreaker max node depth
    max_consecutive_failures=5,     # CircuitBreaker failure threshold
    sigma_threshold=3.0,            # BehaviorMonitor anomaly threshold
    max_subtasks_per_agent=12,      # SafetyGateV2 subtask limit
    dangerous_capabilities=[        # Pre-flight capability blocklist
        "halt", "circuit_break", "delete", "rm"
    ],
    enable_audit=True,              # Tamper-evident audit trail
)
```

## Key Insight: Governance Runs Without an LLM

MAREF's governance primitives (SafetyGateV2, CircuitBreaker, SubgoalInterceptor, BehaviorMonitor) are **local Python code** — they don't call any LLM API. This means:

1. **Pre-flight validation is free** — `validate()` checks graph structure without any model calls
2. **Per-step interception is sub-15μs** — the CoT scanning + goal inference + safety gate adds negligible latency
3. **Audit trails are tamper-evident** — SHA-256 hash chains can be verified offline

The LLM is only needed for the actual node execution (`invoke()`). Governance wraps around it.
