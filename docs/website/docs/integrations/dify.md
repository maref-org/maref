---
sidebar_position: 4
title: Dify Integration
description: Apply MAREF governance to Dify workflows
---

# Integrating MAREF Governance with Dify

This guide shows how to use MAREF governance with Dify workflows and custom tools, wrapping Dify API calls with governance decisions, audit logging, and circuit breaker protection.

## Overview

Dify provides a visual AI workflow builder with LLM orchestration. MAREF governance adds safety evaluation, risk assessment, and compliance auditing to every Dify workflow node and API call.

## Basic Setup

```python
from sidecar.adapters.dify import DifyAdapter

adapter = DifyAdapter(
    api_key="dify-app-key",
    base_url="http://localhost:8000",
)

decision, reason = adapter.evaluate_workflow_safety(
    workflow_id="wf-001",
    input_data={"query": "Delete user records"},
)
if decision == "block":
    print(f"Workflow blocked: {reason}")
else:
    result = adapter.execute_with_governance(
        workflow_id="wf-001",
        input_data={"query": "Show user stats"},
    )
```

## Key Features

- Workflow-level safety evaluation before execution
- Governance wrapping for Dify API calls
- Audit logging of all workflow executions
- Circuit breaker integration for API fault isolation

## Complete Example

```python
"""full_dify_integration.py"""
from sidecar.adapters.dify import DifyAdapter


def run_governed_dify_workflow():
    adapter = DifyAdapter(
        api_key="dify-app-key",
        base_url="http://localhost:8000",
    )

    workflow_id = "wf-001"

    # Step 1: Evaluate workflow safety
    decision, reason = adapter.evaluate_workflow_safety(
        workflow_id=workflow_id,
        input_data={"query": "Delete user records"},
    )
    if decision == "block":
        print(f"Workflow blocked: {reason}")
        return

    # Step 2: Execute with governance
    result = adapter.execute_with_governance(
        workflow_id=workflow_id,
        input_data={"query": "Show monthly user statistics"},
    )

    # Step 3: Check audit trail
    audit = adapter.get_audit_log(workflow_id)
    print(f"Audit entries: {len(audit)}")
    for entry in audit[-3:]:
        print(f"  {entry.timestamp}: {entry.verdict}")

    return result


run_governed_dify_workflow()
```

## Circuit Breaker for Dify API

```python
from sidecar.adapters.dify import DifyAdapter
from maref.governance.circuit_breaker import CircuitBreaker

adapter = DifyAdapter(
    api_key="dify-app-key",
    base_url="http://localhost:8000",
    circuit_breaker=CircuitBreaker(max_consecutive_failures=3),
)

# If Dify API fails 3 times, circuit opens and all calls are blocked
# until cooldown expires
```

## Custom Tool Governance

```python
# Wrap custom Dify API tools with governance
from maref.integration.mcp_governance import MCPGovernance

governance = MCPGovernance()
adapter.set_governance_pipeline(governance)

# Every Dify tool call now flows through MCPGovernance's
# policy engine, circuit breaker, and HMAC audit
```

See the [GitHub source](https://github.com/maref-org/maref/blob/main/docs/integrations/dify.md) for the latest integration code.
