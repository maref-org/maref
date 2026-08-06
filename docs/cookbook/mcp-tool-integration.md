# Cookbook: MCP Tool Integration

This guide covers connecting to MCP servers via different transports, registering tools, calling them through the governance pipeline, and aggregating multiple backends via the MCP Gateway.

## Prerequisites

```bash
pip install maref httpx
```

## Step 1: In-Process MCP (Simplest Path)

Register tools on an `MCPServer` and call them via `InProcessTransport` -- no network, zero latency.

```python
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel
from maref.integration.mcp_transport import JSONRPCRequest

# Create server with security gate
server = MCPServer(
    name="my-server",
    version="1.0.0",
    security_gate=MCPSecurityGate(),
)

# Register a tool
def greet_handler(args: dict) -> dict:
    name = args.get("name", "world")
    return {"message": f"Hello, {name}!"}

server.register_tool(
    name="greet",
    description="Greet a user by name",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name to greet"},
        },
    },
    handler=greet_handler,
)

# Get in-process transport (zero latency)
transport = server.get_inprocess_transport()

# Call the tool
request = JSONRPCRequest(
    method="tools/call",
    params={"name": "greet", "arguments": {"name": "MAREF"}},
    id=1,
)
response = transport.send(request)
print(response.result)  # {"message": "Hello, MAREF!"}

# List tools
list_req = JSONRPCRequest(method="tools/list", id=2)
list_resp = transport.send(list_req)
print(list_resp.result["tools"])
```

## Step 2: Stdio Transport (External MCP Server)

Connect to an external MCP server via subprocess stdin/stdout, like `@modelcontextprotocol/server-filesystem`.

```python
from maref.integration.mcp_client import MCPClient, MCPServerConfig

client = MCPClient()

# Connect to a stdio-based MCP server
config = MCPServerConfig(
    command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    transport_type="stdio",
    server_name="filesystem",
)
conn = client.register_server(config)
print(f"Connected: {conn.state.value}")

# List available tools
tools = client.list_tools(conn)
for tool in tools:
    print(f"  {tool.name}: {tool.description}")

# Call a tool (raw, no governance)
from maref.integration.mcp_security import MCPTrustLevel

response = client.call_tool(
    conn=conn,
    tool_name="read_file",
    args={"path": "/tmp/test.txt"},
    trust_level=MCPTrustLevel.TRUSTED,
)
if response.is_error:
    print(f"Error: {response.error}")
else:
    print(f"Result: {response.result}")
```

## Step 3: SSE Transport (Remote MCP Server)

Connect to a remote MCP server via Server-Sent Events.

```python
config = MCPServerConfig(
    url="https://mcp.example.com/sse",
    transport_type="sse",
    server_name="remote-server",
)
conn = client.register_server(config)

# SSE transport handles reconnection (max 3 retries)
# Event callbacks for push notifications
from maref.integration.mcp_transport import SSETransport
from maref.integration.mcp_client import MCPServerConfig

# Or directly:
sse_transport = SSETransport(
    url="https://mcp.example.com/sse",
    max_retries=3,
    timeout=30.0,
)
sse_transport.connect()

def on_message(data: str) -> None:
    print(f"SSE message: {data}")

sse_transport.on_event("message", on_message)
```

## Step 4: Applying Governance to MCP Calls

Wire up the full governance pipeline to control what tools agents can call.

```python
from maref.integration.mcp_governance import (
    MCPGovernance,
    MCPPolicyEngine,
    MCPDecisionVerdict,
)
from maref.integration.mcp_security import MCPTrustLevel

# Create governance pipeline
governance = MCPGovernance()

# Register governance with client
client = MCPClient()
client.register_governance(governance)

# Connect to server
config = MCPServerConfig(
    command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    transport_type="stdio",
)
conn = client.register_server(config)

# This call will go through governance:
# 1. Policy engine evaluates (rules in priority order)
# 2. Circuit breaker checks
# 3. HMAC audit signed
# 4. HITL routed if needed
result = client.call_tool(
    conn=conn,
    tool_name="write_file",
    args={"path": "/tmp/test.txt", "content": "hello"},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
    session_id="sess-001",
)

if result.is_error:
    # Check if governance blocked it
    if result.error_code == -32000:
        print(f"Governance denied: {result.error['message']}")
    elif result.error_code == -32001:
        print(f"HITL required: {result.error['message']}")
        hitl_id = result.result.get("hitl_event_id")
else:
    print(f"Tool call succeeded: {result.result}")

# Check governance audit log
summary = governance.get_audit_summary()
print(f"Total calls: {summary['total_calls']}")
print(f"Allowed: {summary['allowed']}")
print(f"Denied: {summary['denied']}")
print(f"HITL pending: {summary['hitl_pending']}")

# Verify HMAC integrity
violations = governance.verify_audit_integrity()
print(f"Integrity violations: {len(violations)}")
```

## Step 5: Custom Policy Rules

Add custom governance rules for domain-specific tool policies.

```python
from maref.integration.mcp_governance import (
    MCPPolicyRule,
    MCPPolicyContext,
    MCPGovernanceResult,
    MCPDecisionVerdict,
    MCPPolicyEngine,
)


class AllowBusinessHoursOnly(MCPPolicyRule):
    """Only allow write operations during business hours."""

    def __init__(self):
        super().__init__(
            rule_id="my-rule-001",
            description="Allow writes only during business hours",
            priority=70,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        import datetime
        if context.tool_name.startswith("write"):
            hour = datetime.datetime.now().hour
            if hour < 9 or hour > 17:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Write tool '{context.tool_name}' blocked outside business hours (current hour: {hour})",
                    matched_rule=self.rule_id,
                    risk_score=0.6,
                )
        return None


class RequireHighTrustForSecrets(MCPPolicyRule):
    """Block secret/key related tools for untrusted agents."""

    def __init__(self):
        super().__init__(
            rule_id="my-rule-002",
            description="Secrets management requires trusted agents",
            priority=70,
        )

    SECRET_KEYWORDS = ["secret", "password", "token", "key", "credential"]

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        name = context.tool_name.lower()
        for keyword in self.SECRET_KEYWORDS:
            if keyword in name and context.trust_level.value != "trusted":
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Tool '{context.tool_name}' requires TRUSTED level, got {context.trust_level.value}",
                    matched_rule=self.rule_id,
                    risk_score=0.9,
                )
        return None


# Create custom policy engine
custom_engine = MCPPolicyEngine(rules=[
    AllowBusinessHoursOnly(),
    RequireHighTrustForSecrets(),
])

# Use with governance
from maref.integration.mcp_governance import MCPGovernance
custom_gov = MCPGovernance(policy_engine=custom_engine)

# Test
from maref.integration.mcp_client import MCPClient, MCPServerConfig
from maref.integration.mcp_security import MCPTrustLevel

client = MCPClient()
client.register_governance(custom_gov)
```

## Step 6: MCP Gateway — Multi-Backend Aggregation

Aggregate tools from multiple MCP servers behind a single gateway.

```python
from sidecar.mcp_gateway import MCPGateway

gateway = MCPGateway()

# Register backend 1: filesystem tools
gateway.register_backend(
    prefix="fs_",
    server_url="stdio://filesystem",
    transport_type="in-process",
    handler=my_fs_handler,
    tools=[
        {"name": "fs_read_file", "description": "Read a file", "inputSchema": {}},
        {"name": "fs_write_file", "description": "Write a file", "inputSchema": {}},
    ],
)

# Register backend 2: git tools
gateway.register_backend(
    prefix="git_",
    transport_type="in-process",
    handler=my_git_handler,
    tools=[
        {"name": "git_status", "description": "Git status", "inputSchema": {}},
        {"name": "git_log", "description": "Git log", "inputSchema": {}},
    ],
)

# Aggregate all tools
all_tools = gateway.list_tools()
for tool in all_tools:
    print(f"  {tool['name']}: {tool['description']}")

# Route a call through gateway
result = gateway.call_tool(
    tool_name="fs_read_file",
    arguments={"path": "/tmp/test.txt"},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
)
```

## Step 7: YAML-Based Policy Mapping

Define tool-to-rule mappings in YAML for runtime configurability.

```yaml
# policy.yaml
version: "1.0"
mappings:
  - tools: ["ping", "tools/list", "resources/list"]
    rule: "mcp-rule-001"
  - tools: ["read_file", "list_directory", "search_files"]
    rule: "mcp-rule-002"
  - tools: ["shell", "bash", "exec"]
    rule: "mcp-rule-003"
  - patterns: ["write_", "delete_", "push_"]
    rule: "mcp-rule-005"
  - patterns: ["*"]
    rule: "mcp-rule-006"
```

```python
from maref.integration.mcp_governance import (
    MCPPolicyMapping,
    MCPMappedPolicyEngine,
)

# Load from file
mapping = MCPPolicyMapping.from_yaml_file("policy.yaml")

# Create mapped engine
engine = MCPMappedPolicyEngine(mapping=mapping)

# Test a tool
from maref.integration.mcp_governance import MCPPolicyContext
from maref.integration.mcp_security import MCPTrustLevel

context = MCPPolicyContext(
    tool_name="shell",
    trust_level=MCPTrustLevel.UNTRUSTED,
)
result = engine.evaluate(context)
print(f"{context.tool_name} -> {result.verdict.value} (rule: {result.matched_rule})")
# shell -> ask_user (rule: mcp-rule-003)
```

## Step 8: Complete Integration Test

```python
"""test_mcp_integration.py"""
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_client import MCPClient, MCPServerConfig
from maref.integration.mcp_governance import MCPGovernance, MCPDecisionVerdict
from maref.integration.mcp_security import MCPTrustLevel


def test_inprocess_mcp_with_governance():
    # Server
    server = MCPServer(name="test-server")
    server.register_tool(
        name="echo",
        description="Echo input",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        handler=lambda args: {"echo": args.get("message", "")},
    )

    # Governance
    gov = MCPGovernance()

    # Client
    client = MCPClient()
    client.register_governance(gov)

    # Connect via in-process transport
    transport = server.get_inprocess_transport()
    config = MCPServerConfig(
        transport_type="stdio",
        command=["echo", "inprocess"],
        server_name="test",
    )
    # For in-process, register server directly
    conn = client.register_server(config)
    # Replace with in-process transport
    conn.transport = transport
    conn.state = "connected"

    # Call tool
    result = client.call_tool(
        conn=conn,
        tool_name="echo",
        args={"message": "hello"},
        trust_level=MCPTrustLevel.TRUSTED,
    )
    assert not result.is_error
    assert result.result["echo"] == "hello"

    # Governance audit logged
    assert len(gov.get_audit_log()) > 0

    # Verify audit integrity
    violations = gov.verify_audit_integrity()
    assert len(violations) == 0

    # Dangerous tool triggers ASK_USER
    result = client.call_tool(
        conn=conn,
        tool_name="bash",
        args={"command": "rm -rf /"},
        trust_level=MCPTrustLevel.UNTRUSTED,
    )
    assert result.is_error
    assert result.error_code == -32000

    print("All MCP integration tests passed!")
```
