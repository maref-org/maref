# Cookbook: HITL Approval Flow

This guide covers configuring Human-in-the-Loop (HITL) approval for high-risk agent operations, setting up escalation proposals with deadlines, handling approvals and rejections, and configuring the 5% spot check system.

## Overview

MAREF supports three human involvement modes:

| Mode | Decision Authority | Typical Use |
|------|-------------------|-------------|
| HITL (Human-In-The-Loop) | Human must approve every action | High-risk, first-time operations |
| HOTL (Human-On-The-Loop) | Agent acts autonomously, human can interrupt | Routine operations |
| HATL (Human-Across-The-Loop) | Agent acts autonomously, human spot-checks | Established, low-risk operations |

## Step 1: Basic HITL Configuration

```python
from maref.integration.hitl import HITLRouter, HITLTier, HITLStatus

# Create HITL router
hitl = HITLRouter()

# Tier config:
# - critical  -> P0_RESPONSE (synchronous, blocking, requires human)
# - warning   -> P1_ESCALATE (30s auto-approve window)
# - info      -> P2_LOG (log only, no human interaction)
# - normal    -> P3_OBSERVE (observe only, to knowledge graph)

# Route a critical anomaly
event = hitl.route(
    severity="critical",
    anomaly_type="file_deletion_production",
    description="Agent attempting to delete /etc/prod/config.yaml",
    tool_name="delete_file",
    risk_score=0.95,
    request_id="req-001",
    agent_id="agent-42",
)
print(f"Event: {event.event_id}, Tier: {event.tier.value}, Status: {event.status.value}")
```

## Step 2: HITL with MCP Governance

When an MCP tool call triggers ASK_USER, the governance pipeline automatically creates a HITL event that requires human approval before the tool executes.

```python
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel

# Full governance pipeline
governance = MCPGovernance()

# Simulate a dangerous tool call
result = governance.evaluate(
    tool_name="delete_file",
    args={"path": "/etc/prod/config.yaml", "recursive": True},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
)

if result.verdict.value == "ask_user":
    print(f"Action blocked, awaiting human approval")
    print(f"HITL event: {result.hitl_event_id}")

    # Human approves (simulated)
    approved = governance.approve_tool_call(
        event_id=result.hitl_event_id,
        reviewer="ops-admin",
    )

    if approved:
        print("Human approved — proceeding with tool call")
        # Now actually call the tool (with audit trail)
    else:
        print("Human rejected — tool call canceled")
```

## Step 3: Escalation Proposal with Deadlines

Use `EscalationProposal` from hitl_v2 for time-bounded approvals with auto-approve/reject fallback.

```python
from maref.recursive.hitl_v2 import EscalationProposal, DeadlineNegotiator

negotiator = DeadlineNegotiator()

# Create an escalation for a high-risk operation
proposal = EscalationProposal(
    proposal_id="esc-001",
    agent_id="agent-42",
    risk_level="high",
    description="Deploy to production with config changes",
    proposed_action="deploy",
    impact="Production deployment of new feature",
    rollback_plan="Run rollback.sh",
)

# Set deadline with negotiation
proposal = negotiator.set_deadline(
    proposal=proposal,
    deadline_seconds=300,  # 5 minutes
    auto_escalate=True,     # Escalate to next tier if timeout
    escalate_after_seconds=120,
)
print(f"Deadline set: {proposal.deadline_at}")

# Send approval request to human
# (In production, this would be via Slack/email/dashboard)

# Human responds
proposal.status = "approved"
proposal.responded_by = "ops-admin"
proposal.response_note = "Looks good, proceed"
print(f"Proposal {proposal.proposal_id}: {proposal.status}")

# Use the approval
if proposal.status == "approved":
    # Execute the operation
    pass
```

## Step 4: Complete HITL Flow via GaaS API

The GaaS (Governance as a Service) API provides REST endpoints for HITL.

```python
"""Complete HITL flow using GaaS API."""
import httpx

GaaS_URL = "http://localhost:8000/api/v1/gaas"
API_KEY = "tenant-api-key"


def request_human_approval(action: str, description: str) -> str:
    """Request human approval and return event ID."""
    resp = httpx.post(
        f"{GaaS_URL}/hitl/request",
        headers={"X-API-Key": API_KEY},
        json={
            "agent_id": "agent-42",
            "action": action,
            "description": description,
            "parameters": {
                "file_path": "/etc/prod/config.yaml",
            },
            "tier": "p0",
            "auto_approve_seconds": 30.0,
        },
    )
    data = resp.json()
    return data["event_id"]


def check_pending_approvals() -> list[dict]:
    """List all pending approval requests."""
    resp = httpx.get(
        f"{GaaS_URL}/hitl/pending",
        headers={"X-API-Key": API_KEY},
    )
    data = resp.json()
    return data["events"]


def approve_action(event_id: str) -> bool:
    """Approve a pending action."""
    resp = httpx.post(
        f"{GaaS_URL}/hitl/{event_id}/approve",
        headers={"X-API-Key": API_KEY},
    )
    data = resp.json()
    return data.get("approved", False)


def deny_action(event_id: str) -> bool:
    """Deny a pending action."""
    resp = httpx.post(
        f"{GaaS_URL}/hitl/{event_id}/deny",
        headers={"X-API-Key": API_KEY},
    )
    data = resp.json()
    return not data.get("approved", True)


# Full flow
event_id = request_human_approval("file.delete", "Delete production config")
print(f"Requested approval: {event_id}")

pending = check_pending_approvals()
print(f"Pending approvals: {len(pending)}")

# Human reviews and approves
approved = approve_action(event_id)
print(f"Approved: {approved}")
```

## Step 5: 5% Spot Check Configuration

The Carbon-Silicon Symbiosis system implements randomized spot checks for agent-only tasks.

```python
from maref.recursive.carbon_silicon_symbiosis import (
    CarbonSiliconSymbiosis,
    TaskDomain,
    TaskAllocation,
)

# Create symbiosis with 5% spot check rate
symbiosis = CarbonSiliconSymbiosis(
    human_id="ops-user",
    spot_check_rate=0.05,  # 5% random sampling
)

# Agent-only task — may trigger spot check
result = symbiosis.run_full_cycle(
    agent_id="browser-agent",
    domain=TaskDomain.CODE_GENERATION,
    title="Generate API endpoint",
    description="Create a new REST endpoint for user management",
)

if result.status == "rejected":
    print(f"Spot check rejected: {result.human_interactions} human interactions")
elif result.status == "completed":
    print(f"Completed (spot checked: {result.spot_checked})")

# The spot check rate is configurable per domain:
from maref.recursive.carbon_silicon_symbiosis import DOMAIN_ALLOCATION

for domain, allocation in DOMAIN_ALLOCATION.items():
    print(f"{domain.value}: {allocation.value}")
    # CODE_GENERATION -> agent_only
    # ARCHITECTURE_DESIGN -> collaborative
    # SECURITY_REVIEW -> human_required
    # DEPLOYMENT -> collaborative
    # MONITORING -> agent_only
    # GOVERNANCE -> human_required
```

## Step 6: Carbon-Silicon Symbiosis with Custom Spot Check

```python
from maref.recursive.carbon_silicon_symbiosis import (
    CarbonSiliconSymbiosis,
    TaskDomain,
)

symbiosis = CarbonSiliconSymbiosis(human_id="admin")

# High confidence domains can have lower spot check rates
symbiosis.HUMAN_SPOT_CHECK_RATE = 0.05  # 5%

# For security review, every task requires human
result = symbiosis.run_full_cycle(
    agent_id="audit-agent",
    domain=TaskDomain.SECURITY_REVIEW,
    title="Review access logs",
    description="Check for unauthorized access attempts",
)
# This will always trigger human review (HUMAN_REQUIRED allocation)

print(f"Workflow stages: {[s.stage.value for s in result.steps]}")
# ['identify', 'propose', 'human_confirm', 'agent_execute', 'agent_self_review', 'human_spot_check', 'complete']
```

## Step 7: HITL via the HITL Middleware in Integration Layer

```python
from maref.integration.hitl import HITLRouter, HITLTier, HITLStatus

router = HITLRouter()

# Custom tier mapping (override defaults)
router.DEFAULT_TIER_MAP = {
    "critical": HITLTier.P0_RESPONSE,
    "warning": HITLTier.P1_ESCALATE,
    "info": HITLTier.P2_LOG,
}

# Route a warning-level event
event = router.route(
    severity="warning",
    anomaly_type="high_cpu_usage",
    description="Agent CPU usage > 90% for 5 minutes",
    tool_name="scale_compute",
    risk_score=0.6,
    request_id="req-002",
    agent_id="agent-42",
)
print(f"Event: {event.event_id}, Tier: {event.tier.value}")

# Escalated to P1 — auto-approves after 30s if no human response

# Check pending
pending = router.get_pending()
print(f"Pending events: {len(pending)}")

# Check timeouts
auto_approved = router.check_timeouts()
print(f"Auto-approved (timeout): {auto_approved}")
```

## Step 8: Integration Test

```python
"""test_hitl_flow.py"""
from maref.integration.hitl import HITLRouter, HITLStatus, HITLTier
from maref.recursive.hitl_v2 import EscalationProposal, DeadlineNegotiator


def test_hitl_flow():
    router = HITLRouter()

    # Route a critical event
    event = router.route(
        severity="critical",
        anomaly_type="test_anomaly",
        description="Test HITL flow",
        tool_name="test_tool",
        risk_score=0.9,
        request_id="test-001",
        agent_id="test-agent",
    )
    assert event.tier == HITLTier.P0_RESPONSE
    assert event.status == HITLStatus.PENDING

    # Approve
    result = router.approve(event.event_id, "test-reviewer")
    assert result == HITLStatus.APPROVED

    # Check event status
    updated = router.get_event(event.event_id)
    assert updated.status == HITLStatus.APPROVED

    # Stats
    stats = router.get_stats()
    assert stats["pending_count"] == 0
    assert stats["approved_count"] >= 1

    print("HITL flow test passed!")


def test_escalation_proposal():
    negotiator = DeadlineNegotiator()
    proposal = EscalationProposal(
        proposal_id="test-esc",
        agent_id="test-agent",
        risk_level="high",
        description="Test escalation",
        proposed_action="test_deploy",
        impact="Testing",
        rollback_plan="Undo",
    )

    proposal = negotiator.set_deadline(
        proposal=proposal,
        deadline_seconds=60,
        auto_escalate=True,
        escalate_after_seconds=30,
    )
    assert proposal.deadline_at > 0

    print("Escalation proposal test passed!")
```
