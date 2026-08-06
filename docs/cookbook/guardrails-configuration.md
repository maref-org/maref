# Cookbook: Guardrails Configuration

This guide covers configuring `MCPSecurityGate` with custom trust levels, rate limits, OAuth, and the full guardrail pipeline.

## Scenario

You need to configure different trust levels for different agents, set rate limits per tool, and integrate OAuth2 for external agent authentication.

## Prerequisites

```bash
pip install maref httpx
```

## Step 1: Trust Level Configuration

```python
from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel

gate = MCPSecurityGate(
    default_trust_level=MCPTrustLevel.UNTRUSTED,
    rate_limit_per_minute=60,
)

# Trust levels (in order of increasing trust):
# UNTRUSTED (0) -> SEMI_TRUSTED (1) -> TRUSTED (2) -> ROOT (3)

# Check a tool call
from maref.integration.mcp_security import ZeroTrustContext

verdict = gate.check(
    tool_name="write_file",
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    args={"path": "/tmp/test.txt"},
    context=ZeroTrustContext(agent_id="agent-42"),
)
print(f"Verdict: {verdict.value}")
```

## Step 2: Custom Rate Limits Per Agent

```python
gate.set_agent_rate_limit(agent_id="agent-42", max_requests=30, window_seconds=60)
gate.set_agent_rate_limit(agent_id="agent-99", max_requests=100, window_seconds=60)

remaining = gate.get_remaining_quota("agent-42")
print(f"Agent-42 remaining: {remaining}")
```

## Step 3: OAuth Integration

```python
from maref.integration.mcp_security import OAuthValidator

# Configure OAuth
oauth = OAuthValidator(
    issuer="https://auth.maref.org",
    client_id="maref-gateway",
    jwks_url="https://auth.maref.org/.well-known/jwks.json",
)

# Validate a token
token = "eyJhbGciOiJSUzI1NiIs..."
claims = oauth.validate(token)
if claims:
    agent_id = claims.get("sub")
    trust_level = MCPTrustLevel.TRUSTED if claims.get("role") == "admin" else MCPTrustLevel.SEMI_TRUSTED
    print(f"Agent {agent_id} authenticated, trust level: {trust_level.value}")
else:
    print("Token validation failed — falling back to UNTRUSTED")
```

## Step 4: Full Guardrail Pipeline

```python
from maref.observability.guardrail_metrics import GuardrailMetricsCollector

metrics = GuardrailMetricsCollector()

verdict = gate.check(
    tool_name="delete_file",
    trust_level=MCPTrustLevel.UNTRUSTED,
    args={"path": "/etc/config.yaml"},
    context=ZeroTrustContext(agent_id="agent-42"),
)

# Record metrics
if verdict.value == "DENY":
    metrics.record_check("DENY", "security", 5.0)
    metrics.set_active_denials(metrics.get_stats()["active_denials"] + 1)

# Get Prometheus metrics output
print(metrics.get_metrics())
```

## Step 5: Verify

```python
verdict = gate.check(
    tool_name="read_file",
    trust_level=MCPTrustLevel.TRUSTED,
    args={"path": "/tmp/test.txt"},
    context=ZeroTrustContext(agent_id="agent-42"),
)
print(f"Trusted read: {verdict.value}")

quota = gate.get_remaining_quota("agent-42")
print(f"Remaining quota: {quota}")

stats = metrics.get_stats()
print(f"Total checks: {stats['total_checks']}")
print(f"Allow rate: {stats['allow_rate']}%")
```
