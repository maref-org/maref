# Cookbook: Custom MCP Governance Policy

This guide shows how to create and register custom governance policies with `MCPPolicyEngine` for domain-specific tool access control.

## Scenario

You need to enforce business rules like "allow write operations only during business hours" and "require trusted agents for secrets management."

## Prerequisites

```bash
pip install maref
```

## Step 1: Create a Custom Policy Rule

```python
from maref.integration.mcp_governance import (
    MCPPolicyRule, MCPPolicyContext, MCPGovernanceResult, MCPDecisionVerdict,
)


class BusinessHoursWriteRule(MCPPolicyRule):
    """Only allow write operations during business hours (09:00-17:00 UTC)."""

    def __init__(self) -> None:
        super().__init__(
            rule_id="my-biz-hours",
            description="Allow writes only during business hours",
            priority=70,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        import datetime
        write_prefixes = ("write", "create", "delete", "update", "push")
        if context.tool_name.lower().startswith(write_prefixes):
            hour = datetime.datetime.now(datetime.timezone.utc).hour
            if hour < 9 or hour > 17:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Write tool '{context.tool_name}' blocked outside business hours ({hour}:00 UTC)",
                    matched_rule=self.rule_id,
                    risk_score=0.6,
                )
        return None
```

## Step 2: Register with MCPPolicyEngine

```python
from maref.integration.mcp_governance import MCPPolicyEngine, MCPGovernance

# Create engine with default rules + custom rule
engine = MCPPolicyEngine()
engine.add_rule(BusinessHoursWriteRule())

# Or create a fresh engine with only custom rules
custom_engine = MCPPolicyEngine(rules=[BusinessHoursWriteRule()])

# Wire into governance pipeline
governance = MCPGovernance(policy_engine=engine)
```

## Step 3: Create a High-Security Rule

```python
class SecretsTrustRule(MCPPolicyRule):
    """Secrets/key management tools require TRUSTED agents."""

    SECRET_KEYWORDS = {"secret", "password", "token", "api_key", "credential"}

    def __init__(self) -> None:
        super().__init__(
            rule_id="my-secrets-trust",
            description="Secrets tools require TRUSTED trust level",
            priority=80,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        from maref.integration.mcp_security import MCPTrustLevel
        name = context.tool_name.lower()
        if any(kw in name for kw in self.SECRET_KEYWORDS):
            if context.trust_level != MCPTrustLevel.TRUSTED:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Secrets tool '{context.tool_name}' requires TRUSTED level, got {context.trust_level.value}",
                    matched_rule=self.rule_id,
                    risk_score=0.95,
                )
        return None
```

## Step 4: YAML-Based Policy Mapping

```python
from maref.integration.mcp_governance import MCPPolicyMapping, MCPMappedPolicyEngine

mapping = MCPPolicyMapping(mappings=[
    {"tools": ["read_file", "list_directory"], "rule": "mcp-rule-002"},
    {"tools": ["write_file"], "rule": "my-biz-hours"},
    {"patterns": ["*secret*", "*key*", "*credential*"], "rule": "my-secrets-trust"},
    {"patterns": ["*"], "rule": "mcp-rule-006"},
])

engine = MCPMappedPolicyEngine(mapping=mapping, rules=[
    BusinessHoursWriteRule(),
    SecretsTrustRule(),
])
```

## Step 5: Verify

```python
from maref.integration.mcp_governance import MCPPolicyContext
from maref.integration.mcp_security import MCPTrustLevel

result = engine.evaluate(MCPPolicyContext(
    tool_name="write_file",
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
))
print(f"Verdict: {result.verdict.value}, Rule: {result.matched_rule}")
# Outside business hours: Verdict: deny, Rule: my-biz-hours

result = engine.evaluate(MCPPolicyContext(
    tool_name="read_secret",
    trust_level=MCPTrustLevel.UNTRUSTED,
))
print(f"Verdict: {result.verdict.value}, Reason: {result.reason}")
# Verdict: deny, Reason: Secrets tool 'read_secret' requires TRUSTED...
```
