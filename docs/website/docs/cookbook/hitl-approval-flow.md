---
sidebar_position: 4
title: HITL Approval Flow
description: Human-in-the-Loop approval configuration
---

# Cookbook: HITL Approval Flow

This guide covers configuring Human-in-the-Loop (HITL) approval for high-risk agent operations, escalation proposals with deadlines, and the 5% spot check system.

## Human Involvement Modes

| Mode | Decision Authority | Typical Use |
|------|-------------------|-------------|
| HITL | Human must approve every action | High-risk operations |
| HOTL | Agent acts, human can interrupt | Routine operations |
| HATL | Agent acts, human spot-checks | Low-risk operations |

## Step 1: Basic HITL Configuration

```python
from maref.integration.hitl import HITLRouter

hitl = HITLRouter()
event = hitl.route(
    severity="critical",
    anomaly_type="file_deletion_production",
    description="Agent deleting /etc/prod/config.yaml",
    risk_score=0.95,
    agent_id="agent-42",
)
print(f"Event: {event.event_id}, Tier: {event.tier.value}")
```

## Step 2: HITL with MCP Governance

```python
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel

governance = MCPGovernance()
result = governance.evaluate(
    tool_name="delete_file",
    args={"path": "/etc/prod/config.yaml"},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
)
if result.verdict.value == "ask_user":
    approved = governance.approve_tool_call(
        event_id=result.hitl_event_id,
        reviewer="ops-admin",
    )
```

## Step 3: Escalation Proposal with Deadlines

```python
from maref.recursive.hitl_v2 import EscalationProposal, DeadlineNegotiator

negotiator = DeadlineNegotiator()
proposal = EscalationProposal(
    agent_id="agent-42", risk_level="high",
    description="Deploy to production",
    proposed_action="deploy",
)
proposal = negotiator.set_deadline(
    proposal=proposal,
    deadline_seconds=300,
    auto_escalate=True,
    escalate_after_seconds=120,
)
```

## Step 4: 5% Spot Check

```python
from maref.recursive.carbon_silicon_symbiosis import CarbonSiliconSymbiosis, TaskDomain

symbiosis = CarbonSiliconSymbiosis(
    human_id="ops-user",
    spot_check_rate=0.05,
)
result = symbiosis.run_full_cycle(
    agent_id="browser-agent",
    domain=TaskDomain.CODE_GENERATION,
    title="Generate API endpoint",
)
```

See the [full cookbook on GitHub](https://github.com/maref-org/maref/blob/main/docs/cookbook/hitl-approval-flow.md) for GaaS API integration, custom tier mappings, and integration tests.
