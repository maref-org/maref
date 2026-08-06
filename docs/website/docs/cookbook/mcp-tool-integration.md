---
sidebar_position: 3
title: MCP Tool Integration
description: Connect MCP servers with governance
---

# Cookbook: MCP Tool Integration

This guide covers connecting to MCP servers via different transports, registering tools, calling them through the governance pipeline, and aggregating multiple backends via the MCP Gateway.

## Step 1: In-Process MCP

```python
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_transport import JSONRPCRequest

server = MCPServer(name="my-server", version="1.0.0")

def greet_handler(args: dict) -> dict:
    return {"message": f"Hello, {args.get('name', 'world')}!"}

server.register_tool(name="greet", description="Greet a user", input_schema={
    "type": "object", "properties": {"name": {"type": "string"}},
}, handler=greet_handler)

transport = server.get_inprocess_transport()
response = transport.send(JSONRPCRequest(
    method="tools/call",
    params={"name": "greet", "arguments": {"name": "MAREF"}},
    id=1,
))
print(response.result)
```

## Step 2: Stdio & SSE Transports

```python
from maref.integration.mcp_client import MCPClient, MCPServerConfig

client = MCPClient()
config = MCPServerConfig(
    command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    transport_type="stdio",
    server_name="filesystem",
)
conn = client.register_server(config)
tools = client.list_tools(conn)
```

## Step 3: Governance Pipeline

```python
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel

governance = MCPGovernance()
client = MCPClient()
client.register_governance(governance)

result = client.call_tool(
    conn=conn,
    tool_name="write_file",
    args={"path": "/tmp/test.txt", "content": "hello"},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
)
```

## Step 4: Custom Policy Rules

```python
from maref.integration.mcp_governance import (
    MCPPolicyRule, MCPPolicyContext, MCPGovernanceResult, MCPDecisionVerdict,
)

class AllowBusinessHoursOnly(MCPPolicyRule):
    def __init__(self):
        super().__init__(rule_id="my-rule-001", priority=70)
    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        import datetime
        if context.tool_name.startswith("write"):
            hour = datetime.datetime.now().hour
            if hour < 9 or hour > 17:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Blocked outside business hours",
                    matched_rule=self.rule_id,
                    risk_score=0.6,
                )
        return None
```

## Step 5: MCP Gateway

```python
from sidecar.mcp_gateway import MCPGateway

gateway = MCPGateway()
gateway.register_backend(
    prefix="fs_", transport_type="in-process",
    handler=my_handler, tools=[{"name": "fs_read_file", ...}],
)
all_tools = gateway.list_tools()
```

See the [full cookbook on GitHub](https://github.com/maref-org/maref/blob/main/docs/cookbook/mcp-tool-integration.md) for YAML-based policy mappings and complete integration tests.
