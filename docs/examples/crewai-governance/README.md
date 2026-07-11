# MAREF Governance for CrewAI Workflows

> **Case study code**: How to wrap a CrewAI crew with MAREF's governance primitives — no LLM API key required for governance validation.

## Quick Start

```bash
# Install MAREF (and CrewAI for production use)
pip install maref
pip install crewai  # optional: only needed for real LLM execution

# Run the demo (no API key needed — governance runs locally)
cd docs/examples/crewai-governance
python demo.py
```

## What This Demonstrates

This example shows how MAREF's governance layer wraps a CrewAI crew to provide:

| Governance Primitive | CrewAI Hook | What It Guards Against |
|---------------------|-------------|----------------------|
| **SafetyGateV2** | Pre-flight validation | Subtask explosion, dangerous capabilities |
| **CircuitBreaker** | Wraps `Crew.kickoff()` | Recursive depth, consecutive failures |
| **SubgoalInterceptor** | `Agent.step_callback` | Goal hijacking, control subgoals, delegation creep |
| **BehaviorMonitor** | `Agent.step_callback` | Rogue agent detection (3-sigma anomaly) |
| **GovernanceStateMachine** | Tracks crew lifecycle | 10-state Gray Code FSM (INIT→...→HALT) |
| **Audit trail** | All governance events | Tamper-evident SHA-256 hash chain |

## Demo Scenarios

The demo (`demo.py`) runs 4 scenarios:

1. **Benign crew** — A normal research + writing crew. Governance passes, crew executes.
2. **Dangerous crew** — A crew with "halt" and "delete" capabilities. Governance blocks it in pre-flight.
3. **Goal hijack** — An agent reasons about "bypassing safety constraints" and "elevating permissions". SubgoalInterceptor HALTs execution.
4. **Behavior anomaly** — An agent spikes to 100x normal ops count. BehaviorMonitor detects the 3-sigma anomaly.

## Files

| File | Description |
|------|-------------|
| [`maref_crewai_governor.py`](maref_crewai_governor.py) | The `MAREFGovernedCrew` adapter class |
| [`demo.py`](demo.py) | Runnable demo with 4 scenarios (uses mock CrewAI objects) |
| [`demo-output.txt`](demo-output.txt) | Sample output from a demo run |

## Integration Architecture

```
┌─────────────────────────────────────────────────┐
│              MAREFGovernedCrew                    │
│                                                   │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │ Governance  │  │     CrewAI Crew           │  │
│  │  StateMachine│  │  ┌──────┐  ┌──────┐     │  │
│  │  (10-state  │  │  │Agent │  │Agent │     │  │
│  │   Gray Code)│  │  │  1   │  │  2   │     │  │
│  └──────┬──────┘  │  └──┬───┘  └──┬───┘     │  │
│         │         │     │         │          │  │
│  ┌──────┴──────┐  │     │ step_callback       │  │
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
│  │  validate() │  │                          │  │
│  │  kickoff()  │  │                          │  │
│  └─────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Using with Real CrewAI

Replace the mock objects in `demo.py` with real CrewAI classes:

```python
from crewai import Agent, Task, Crew
from maref_crewai_governor import MAREFGovernedCrew, GovernanceConfig

researcher = Agent(
    role="Researcher",
    goal="Find accurate information",
    backstory="An experienced research analyst.",
    llm="gpt-4o",  # or your preferred LLM
)

writer = Agent(
    role="Writer",
    goal="Write a clear report",
    backstory="A professional technical writer.",
    llm="gpt-4o",
)

research_task = Task(
    description="Research agent governance frameworks",
    expected_output="Key findings with sources",
    agent=researcher,
)

write_task = Task(
    description="Write a summary report",
    expected_output="A 500-word report",
    agent=writer,
)

crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])

# Wrap with MAREF governance
governed = MAREFGovernedCrew(crew, config=GovernanceConfig(max_recursion_depth=3))

# Pre-flight governance check (runs without LLM)
report = governed.validate()
print(report.summary())

if report.passed:
    # Run with governance enforcement (LLM required)
    result = governed.kickoff()
    governed.print_governance_report()
```

## Governance Configuration

```python
config = GovernanceConfig(
    max_recursion_depth=3,          # CircuitBreaker max agent depth
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

1. **Pre-flight validation is free** — `validate()` checks crew structure without any model calls
2. **Per-step interception is sub-15μs** — the CoT scanning + goal inference + safety gate adds negligible latency
3. **Audit trails are tamper-evident** — SHA-256 hash chains can be verified offline

The LLM is only needed for the actual crew execution (`kickoff()`). Governance wraps around it.
