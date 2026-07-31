# MAREF Governance for AutoGen Conversations

> **Case study code**: How to wrap an AutoGen-style multi-agent conversation with MAREF's governance primitives — no LLM API key required for governance validation.

## Quick Start

```bash
# Install MAREF (and pyautogen for production use)
pip install maref
pip install pyautogen  # optional: only needed for real LLM execution

# Run the demo (no API key needed — governance runs locally)
cd docs/examples/autogen-governance
python demo.py
```

## What This Demonstrates

This example shows how MAREF's governance layer wraps an AutoGen-style group chat to provide:

| Governance Primitive | Conversation Hook | What It Guards Against |
|---------------------|-------------------|----------------------|
| **SafetyGateV2** | Pre-flight validation | Agent roster explosion, dangerous capabilities |
| **CircuitBreaker** | Wraps `run()` | Excessive turns, consecutive failures |
| **SubgoalInterceptor** | Per-message callback | Goal hijacking, control subgoals, delegation creep |
| **BehaviorMonitor** | Per-message callback | Rogue agent detection (3-sigma anomaly) |
| **GovernanceStateMachine** | Tracks conversation lifecycle | 10-state Gray Code FSM (INIT→...→HALT) |
| **Audit trail** | All governance events | Tamper-evident SHA-256 hash chain |

## Demo Scenarios

The demo (`demo.py`) runs 4 scenarios:

1. **Benign conversation** — A normal researcher + writer chat. Governance passes, all messages intercepted.
2. **Dangerous roster** — An agent whose system message contains "halt" and "delete". Governance blocks it in pre-flight.
3. **Goal hijack** — An agent sends a message about "bypassing safety constraints" and "elevating permissions". SubgoalInterceptor HALTs the conversation.
4. **Behavior anomaly** — An agent spikes to 100x normal message size. BehaviorMonitor detects the 3-sigma anomaly.

## Files

| File | Description |
|------|-------------|
| [`maref_autogen_governor.py`](maref_autogen_governor.py) | The `MAREFGovernedConversation` adapter class |
| [`demo.py`](demo.py) | Runnable demo with 4 scenarios (uses mock AutoGen objects) |

## Integration Architecture

```
┌──────────────────────────────────────────────────────┐
│         MAREFGovernedConversation                      │
│                                                        │
│  ┌─────────────┐  ┌───────────────────────────────┐   │
│  │ Governance  │  │  GroupChat                    │   │
│  │  StateMachine│  │  ┌─────────┐  ┌─────────┐    │   │
│  │  (10-state  │  │  │researcher│  │ writer  │    │   │
│  │   Gray Code)│  │  └────┬────┘  └────┬────┘    │   │
│  └──────┬──────┘  │       │            │          │   │
│         │         │       │  generate_reply       │   │
│  ┌──────┴──────┐  │       ▼            ▼          │   │
│  │CircuitBreaker│  │  ┌─────────────────────┐     │   │
│  │  (depth +   │  │  │SubgoalInterceptor    │     │   │
│  │   failures) │  │  │  + BehaviorMonitor   │     │   │
│  └──────┬──────┘  │  └─────────┬───────────┘     │   │
│         │         │            │                  │   │
│  ┌──────┴──────┐  │            ▼                  │   │
│  │ SafetyGateV2│  │  ┌─────────────────────┐      │   │
│  │ (pre-flight)│  │  │  Audit Trail        │      │   │
│  └──────┬──────┘  │  │  (SHA-256 chain)    │      │   │
│         │         │  └─────────────────────┘      │   │
│         ▼         │                                │   │
│  ┌─────────────┐  │                                │   │
│  │ validate()  │  │                                │   │
│  │ run()       │  │                                │   │
│  └─────────────┘  └───────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

## Using with Real AutoGen

Replace the mock objects in `demo.py` with real AutoGen classes:

```python
from autogen import ConversableAgent
from maref_autogen_governor import MAREFGovernedConversation, GovernanceConfig

researcher = ConversableAgent(
    name="researcher",
    system_message="You find accurate information about a topic.",
    llm_config={"config_list": [{"model": "gpt-4o", "api_key": "..."}]},
)

writer = ConversableAgent(
    name="writer",
    system_message="You write clear factual reports from research.",
    llm_config={"config_list": [{"model": "gpt-4o", "api_key": "..."}]},
)

# Wrap with MAREF governance
governed = MAREFGovernedConversation(
    chat=group_chat_or_agents,
    config=GovernanceConfig(max_recursion_depth=3),
)

# Pre-flight governance check (runs without LLM)
report = governed.validate()
print(report.summary())

if report.passed:
    # Run the conversation (LLM required for real replies)
    transcript = governed.run(max_turns=4)
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

1. **Pre-flight validation is free** — `validate()` checks the agent roster without any model calls
2. **Per-message interception is sub-15μs** — the CoT scanning + goal inference + safety gate adds negligible latency
3. **Audit trails are tamper-evident** — SHA-256 hash chains can be verified offline

The LLM is only needed for the actual agent replies (`run()`). Governance wraps around it.
