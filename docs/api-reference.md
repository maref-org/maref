# MAREF API Reference

> Version: v0.33.0-rc | Sidecar: v0.32.0-rc | GaaS: v0.28.0

This document covers all public APIs: Sidecar REST API, Governance-as-a-Service (GaaS) API, A2A Python API, and MCP Python API.

---

## 1. Sidecar REST API

The Sidecar is the main HTTP interface for MAREF, running on port 8000 by default. It combines A2A task management, MCP tool bridging, governance routing, and observability.

### 1.1 MCP Endpoints

#### `POST /api/mcp`
MCP JSON-RPC endpoint. Accepts standard MCP methods.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": { "name": "maref_read_observations", "arguments": { "count": 10 } },
  "id": 1
}
```

**Supported methods:** `initialize`, `tools/list`, `resources/list`, `prompts/list`, `tools/call`

**Response (tools/list):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "maref_observe_agent",
        "description": "Observe a specific agent's state",
        "inputSchema": { "type": "object", "properties": { "agent_id": { "type": "string" } } }
      },
      {
        "name": "maref_read_entropy",
        "description": "Read entropy reading for an agent",
        "inputSchema": { "type": "object", "properties": { "agent_id": { "type": "string" } } }
      },
      {
        "name": "maref_read_observations",
        "description": "Read recent observations",
        "inputSchema": { "type": "object", "properties": { "count": { "type": "integer" } } }
      },
      {
        "name": "maref_read_anomalies",
        "description": "Read recent anomalies",
        "inputSchema": { "type": "object", "properties": { "count": { "type": "integer" } } }
      },
      {
        "name": "maref_compliance_check",
        "description": "Check compliance for an action",
        "inputSchema": { "type": "object", "properties": { "agent_id": { "type": "string" }, "action": { "type": "string" } } }
      }
    ]
  }
}
```

#### `GET /api/mcp/.well-known`
Returns MCP capabilities metadata.

```json
{
  "protocol": "mcp",
  "version": "2024-11-05",
  "capabilities": { "tools": [...] }
}
```

### 1.2 A2A Endpoints

#### `POST /api/a2a/task/send`
Submit a task to the MAREF agent using JSON-RPC 2.0.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tasks.send",
  "params": {
    "id": "req-001",
    "message": { "parts": [{ "text": "Analyze the quarterly report" }] },
    "metadata": { "skills": ["maref-governance"] }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "id": "maref-task-a1b2c3d4e5f6",
    "status": { "state": "submitted" },
    "createdAt": 1718612345.67
  }
}
```

**Errors:**
- `-32600` Invalid JSON-RPC
- `-32601` Method not found
- `-32602` Unknown skills
- `-32000` Circuit breaker OPEN

#### `GET /api/a2a/task/{task_id}`
Get task status.

**Response:**
```json
{
  "id": "maref-task-a1b2c3d4e5f6",
  "status": { "state": "working" },
  "description": "Analyze the quarterly report",
  "maref_state": "ACT",
  "createdAt": 1718612345.67,
  "updatedAt": 1718612350.12,
  "history": [{ "state": "working", "timestamp": 1718612350.12 }]
}
```

#### `POST /api/a2a/task/cancel`
Cancel a running task.

**Request:**
```json
{ "id": "maref-task-a1b2c3d4e5f6", "task_id": "maref-task-a1b2c3d4e5f6", "reason": "User requested halt" }
```

**Response:**
```json
{ "success": true, "task_id": "maref-task-a1b2c3d4e5f6", "state": "canceled", "reason": "User requested halt" }
```

#### `POST /api/a2a/task/state`
Push a state update for a task.

**Request:**
```json
{ "task_id": "maref-task-a1b2c3d4e5f6", "id": "maref-task-a1b2c3d4e5f6", "state": "completed" }
```

**Response:**
```json
{ "success": true, "state": "completed" }
```

#### `GET /{task_id}/stream)` (note: path is `/api/a2a/task/{task_id}/stream`)
SSE streaming endpoint for task progress updates.

### 1.3 Agent Card & Discovery

#### `GET /.well-known/agent-card.json`
Returns the A2A agent card for discovery.

**Response:**
```json
{
  "agentCard": {
    "name": "maref-agent",
    "description": "MAREF-governed agent",
    "version": "0.2.0",
    "url": "http://localhost:8000",
    "protocolVersion": "1.0",
    "capabilities": { "streaming": true, "pushNotifications": true, "stateTransitionHistory": true },
    "skills": [
      { "id": "maref-governance", "name": "MAREF Governance", "description": "Execute tasks under MAREF 10-state governance", "tags": ["governance", "state-machine", "entropy"], "examples": ["Govern a research task through the MAREF lifecycle"], "inputModes": ["text/plain"], "outputModes": ["application/json"] }
    ],
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["application/json"]
  },
  "signature": "hmac-sha256-hex-digest",
  "signingAlgorithm": "hmac-sha256"
}
```

### 1.4 MCP Gateway Endpoints

#### `GET /api/mcp/gateway/health`
Gateway health status.

#### `POST /api/mcp/gateway/tools/call`
Route a tool call through the MCP gateway. The gateway applies governance, then dispatches to the registered backend.

**Request:**
```json
{
  "tool_name": "maref_read_observations",
  "arguments": { "count": 5 },
  "trust_level": "semi_trusted",
  "agent_id": "agent-42",
  "session_id": "sess-001"
}
```

#### `GET /api/mcp/gateway/tools`
List all aggregated tools from registered backends.

**Response:**
```json
{
  "tools": [
    { "name": "maref_observe_agent", "description": "...", "inputSchema": {} },
    { "name": "maref_read_entropy", "description": "...", "inputSchema": {} }
  ],
  "backends": ["maref_"]
}
```

### 1.5 Health & Status

#### `GET /api/health`
```json
{ "status": "healthy", "collector_running": true, "buffer_size": 42 }
```

#### `GET /api/status`
```json
{ "status": "running" }
```

#### `GET /api/version`
```json
{ "version": "0.32.0-rc" }
```

### 1.6 Observability Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/agents` | List discovered agents |
| `GET /api/observations` | Recent observations from collector |
| `GET /api/anomalies` | Detected anomalies |
| `GET /api/metrics` | Prometheus-formatted metrics |
| `GET /api/obs/status` | Observation bridge status |

### 1.7 Session & Provider Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/sessions` | Create session |
| `GET /api/sessions` | List sessions |
| `GET /api/sessions/{id}` | Get session |
| `DELETE /api/sessions/{id}` | Delete session |
| `GET /api/sessions/{id}/messages` | Get session messages |
| `POST /api/sessions/{id}/messages` | Send message |
| `GET /api/providers` | List LLM providers |
| `POST /api/providers` | Register provider |
| `GET /api/skills` | Available skills |
| `GET /api/tasks` | List tasks |
| `POST /api/tasks` | Create task |
| `GET /api/filetree` | Workspace file tree |

### 1.8 Compliance Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/compliance/register` | Register agent for compliance |
| `GET /api/compliance/agents` | List compliance agents |
| `POST /api/compliance/check-action` | Check if action is compliant |
| `POST /api/compliance/snapshot` | Take compliance snapshot |
| `GET /api/compliance/audit-log/{agent_id}` | Get agent audit log |

### 1.9 Immunity Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/immunity/cooldown` | List cooldown entries |
| `GET /api/immunity/cooldown/summary` | Cooldown summary |
| `GET /api/immunity/genes` | Gene audit trail |

---

## 2. Governance API (GaaS)

The Governance-as-a-Service (GaaS) router provides multi-tenant governance decisions via REST API. All endpoints require an `X-API-Key` header for tenant authentication.

Base path: `/api/v1/gaas` (mounted in Sidecar) or alternatively `/api/v1/` in standalone mode.

### `POST /api/v1/gaas/govern`
Execute a governance decision for an agent action.

**Request:**
```json
{
  "tenant_id": "tenant-abc",
  "agent_id": "agent-42",
  "action": "file.write",
  "parameters": { "path": "/tmp/output.txt", "content": "..." },
  "context": {
    "session_id": "sess-001",
    "recursion_depth": 0,
    "trust_score": 85.0,
    "source_ip": "10.0.0.1",
    "user_agent": "maref-agent/0.33"
  }
}
```

**Response:**
```json
{
  "verdict": "ALLOW",
  "circuit_breaker_state": "CLOSED",
  "audit_log_id": "audit_000042",
  "required_hitl_tier": null,
  "estimated_latency_ms": 12,
  "policy_version": "v0.28.0-default",
  "reason": "Default allow"
}
```

**Verdict values:** `ALLOW`, `DENY`, `ASK_USER`, `DEFER`

### `POST /api/v1/gaas/hitl/request`
Request human approval.

**Request:**
```json
{
  "agent_id": "agent-42",
  "action": "file.delete",
  "description": "Delete production config file",
  "parameters": { "path": "/etc/prod/config.yaml" },
  "tier": "p0",
  "auto_approve_seconds": 30.0
}
```

**Response:**
```json
{ "event_id": "hitl-event-001", "status": "pending" }
```

### `POST /api/v1/gaas/hitl/{event_id}/approve`
Approve a pending HITL event.

### `POST /api/v1/gaas/hitl/{event_id}/deny`
Deny a pending HITL event.

### `GET /api/v1/gaas/hitl/pending`
List pending HITL events.

### `GET /api/v1/gaas/trust/score?agent_id=agent-42`
Get trust score for an agent.

**Response:**
```json
{
  "tenant_id": "tenant-abc",
  "agent_id": "agent-42",
  "trust_score": 85.5,
  "trust_tier": "trusted",
  "history_count": 47,
  "last_updated": 1718612345.67
}
```

### `POST /api/v1/gaas/audit/query`
Query audit logs.

**Request:**
```json
{
  "start_time": 1718600000.0,
  "end_time": 1718700000.0,
  "agent_id": "agent-42",
  "action": "file.write",
  "limit": 50,
  "offset": 0
}
```

**Response:**
```json
{
  "entries": [
    {
      "log_id": "audit_000042",
      "timestamp": 1718612345.67,
      "tenant_id": "tenant-abc",
      "agent_id": "agent-42",
      "action": "file.write",
      "verdict": "ALLOW",
      "hmac_signature": "abc123..."
    }
  ],
  "total": 1
}
```

### `GET /api/v1/gaas/cb/status?agent_id=agent-42&action=file.write`
Get circuit breaker status.

### `GET /api/v1/gaas/health`
GaaS service health check.

### Session Management

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/gaas/session/declare` | Declare a new execution session |
| `GET /api/v1/gaas/session/active` | List active sessions |
| `GET /api/v1/gaas/session/{id}` | Get session status |
| `POST /api/v1/gaas/session/{id}/complete` | Complete a session |
| `POST /api/v1/gaas/session/{id}/step` | Increment step counter |

---

## 3. A2A Python API

### `A2ABridge` (`maref.integration.a2a_bridge`)

Wraps MAREF governance (state machine + audit logger + circuit breaker) as an A2A-compatible agent.

```python
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge

bridge = A2ABridge(
    state_machine=GovernanceStateMachine(),
    audit_logger=AuditLogger(),
    circuit_breaker=CircuitBreaker(),
    agent_name="my-agent",
    agent_description="My governed agent",
)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `build_agent_card` | `(base_url: str) -> dict` | Build A2A agent card with capabilities |
| `create_task` | `(description: str, context: dict | None) -> str` | Create a governed task |
| `get_task` | `(task_id: str) -> A2ATaskContext | None` | Get task by ID |
| `delegate_task` | `(task_id: str, target_agent_url: str) -> bool` | Delegate task to another agent |
| `sync_state_from_a2a` | `(task_id: str, a2a_state: str) -> bool` | Sync A2A state to MAREF state machine |
| `handle_push_notification` | `(task_id: str, event: dict) -> None` | Handle A2A push notification |
| `register_capability` | `(capability: A2ASkillDefinition) -> None` | Register a new capability |
| `list_governed_tasks` | `(filter_state: GovernanceState | None) -> list` | List governed tasks |
| `force_halt_task` | `(task_id: str, reason: str) -> bool` | Force halt a task |
| `get_delegated_tasks` | `() -> list` | List delegated tasks |

### `A2AClient` (`maref.integration.a2a_client`)

HTTP client for communicating with other A2A agents.

```python
from maref.integration.a2a_client import A2AClient

client = A2AClient(timeout=30.0)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `send_task` | `(agent_url: str, skill_id: str, input_data: str, metadata: dict | None) -> dict | None` | Send task to agent |
| `get_task` | `(agent_url: str, task_id: str) -> dict | None` | Get task status from agent |
| `cancel_task` | `(agent_url: str, task_id: str, reason: str) -> bool` | Cancel task on remote agent |
| `push_state` | `(agent_url: str, task_id: str, state: str) -> bool` | Push state update to remote agent |
| `discover_agent_card` | `(agent_url: str) -> dict | None` | Fetch agent card from remote agent |

### `A2ADiscovery` (`maref.integration.a2a_discovery`)

Agent registry with capability-based lookup and health checks.

```python
from maref.integration.a2a_discovery import A2ADiscovery

discovery = A2ADiscovery(health_check_interval=60.0)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_agent` | `(agent_id: str, agent_url: str, capabilities: list[str] | None) -> None` | Register an agent |
| `unregister_agent` | `(agent_id: str) -> bool` | Remove agent from registry |
| `discover_agents` | `(capability_filter: str | None) -> list[dict]` | Find agents by capability |
| `health_check` | `(agent_id: str) -> bool` | Check agent health |
| `refresh_all` | `() -> dict[str, bool]` | Health check all agents |

### A2A Types (`maref.integration.a2a_types`)

```python
from maref.integration.a2a_types import (
    A2ATaskState,        # Enum: SUBMITTED, WORKING, INPUT_REQUIRED, COMPLETED, CANCELED, FAILED, REJECTED, AUTH_REQUIRED
    A2ASkillDefinition,  # Dataclass: id, name, description, tags, examples, input_modes, output_modes
    A2ATaskContext,      # Dataclass: task_id, description, a2a_state, maref_state, context, created_at, updated_at
    DelegatedTask,       # Dataclass: task_id, target_agent_url, delegated_at, status
    map_a2a_to_maref,    # Function: A2ATaskState -> GovernanceState
    map_maref_to_a2a,    # Function: GovernanceState -> A2ATaskState
    validate_agent_card_json,  # Function: dict -> bool
)
```

**State Mapping:**
| A2A State | MAREF State |
|-----------|-------------|
| SUBMITTED | INIT |
| WORKING | ACT |
| INPUT_REQUIRED | ANALYZE |
| COMPLETED | REPORT |
| CANCELED | HALT |
| FAILED | HALT |
| REJECTED | HALT |
| AUTH_REQUIRED | EVALUATE |

---

## 4. MCP Python API

### `MCPServer` (`maref.integration.mcp_server`)

MCP server for registering tools, resources, and prompts.

```python
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_security import MCPSecurityGate

server = MCPServer(
    name="my-server",
    version="1.0.0",
    security_gate=MCPSecurityGate(),
)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_tool` | `(name, description, input_schema, handler) -> None` | Register an MCP tool |
| `register_resource` | `(uri, name, mime_type, handler) -> None` | Register an MCP resource |
| `register_prompt` | `(name, description, arguments, handler) -> None` | Register an MCP prompt |
| `handle_request` | `(request: JSONRPCRequest, trust_level) -> JSONRPCResponse` | Handle any MCP request |
| `get_inprocess_transport` | `() -> InProcessTransport` | Get in-process transport for same-process calls |

### `MCPClient` (`maref.integration.mcp_client`)

MCP client for connecting to and calling MCP servers.

```python
from maref.integration.mcp_client import MCPClient, MCPServerConfig

client = MCPClient()
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_server` | `(config: MCPServerConfig) -> MCPConnection` | Connect to an MCP server |
| `register_governance` | `(governance: MCPGovernance) -> None` | Attach governance pipeline |
| `list_tools` | `(conn: MCPConnection) -> list[MCPToolDef]` | List server tools |
| `call_tool` | `(conn, tool_name, args, trust_level, ...) -> JSONRPCResponse` | Call tool with governance |
| `list_resources` | `(conn: MCPConnection) -> list[MCPResourceDef]` | List server resources |

#### `MCPServerConfig` Fields
```python
from maref.integration.mcp_client import MCPServerConfig

config = MCPServerConfig(
    command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    url="https://mcp.example.com/sse",
    transport_type="stdio",       # "stdio", "sse", "http"
    server_name="my-server",
    env={"KEY": "value"},
)
```

### `MCPSecurityGate` (`maref.integration.mcp_security`)

Three-tier trust authorization for MCP tool calls.

```python
from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel

gate = MCPSecurityGate(
    allow_untrusted_shell=False,
    enable_rate_limiting=True,
    enable_delegation_check=True,
    max_delegation_depth=5,
)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `check` | `(tool_name, trust_level, args, context, relaxed) -> SecurityVerdict` | Evaluate tool call |
| `authenticate_request` | `(headers: dict) -> ZeroTrustContext` | Authenticate HTTP request |
| `get_audit_log` | `() -> list[AuditLogEntry]` | Get audit log |
| `get_audit_summary` | `() -> dict` | Get summary statistics |
| `export_audit_log` | `(format: str) -> str` | Export as JSON or syslog |

**Trust Level Enum:**
```python
from maref.integration.mcp_security import MCPTrustLevel

MCPTrustLevel.TRUSTED       # All tools allowed
MCPTrustLevel.SEMI_TRUSTED  # Shell/exec denied (or audited in session)
MCPTrustLevel.UNTRUSTED     # Shell/exec + dangerous patterns denied
```

### `MCPGateway` (`maref.integration.gateway`)

Multi-backend MCP tool routing with governance enforcement.

```python
from sidecar.mcp_gateway import MCPGateway

gateway = MCPGateway()
gateway.register_backend(
    prefix="maref_",
    transport_type="in-process",
    handler=my_handler,
    tools=[{"name": "my_tool", "description": "...", "inputSchema": {}}],
)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_backend` | `(prefix, server_url, transport_type, handler, tools) -> None` | Register an MCP backend |
| `remove_backend` | `(prefix: str) -> bool` | Remove a backend |
| `list_tools` | `() -> list[dict]` | List all aggregated tools |
| `call_tool` | `(tool_name, arguments, ...) -> dict` | Route tool call to backend |

### `MCPGovernance` (`maref.integration.mcp_governance`)

Full governance pipeline integrating policy engine, circuit breaker, HMAC audit, and HITL routing.

```python
from maref.integration.mcp_governance import MCPGovernance

governance = MCPGovernance()
result = governance.evaluate(
    tool_name="write_file",
    args={"path": "/tmp/test.txt"},
    trust_level=MCPTrustLevel.SEMI_TRUSTED,
    agent_id="agent-42",
)
# result.verdict == MCPDecisionVerdict.ASK_USER
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `evaluate` | `(tool_name, args, trust_level, ...) -> MCPGovernanceResult` | Full governance evaluation |
| `approve_tool_call` | `(event_id, reviewer) -> bool` | Approve HITL-triggered tool call |
| `reject_tool_call` | `(event_id, reason) -> bool` | Reject HITL-triggered tool call |
| `get_audit_log` | `() -> list[AuditLogEntry]` | Get full audit log |
| `verify_audit_integrity` | `() -> list[dict]` | Verify HMAC signatures |
| `export_audit_log` | `(format: str) -> str` | Export JSON or syslog |
| `check_hitl_timeouts` | `() -> list[str]` | Auto-approve timed-out events |

### `MCPGovernanceResult`

```python
from maref.integration.mcp_governance import MCPDecisionVerdict

# result.verdict: ALLOW, DENY, ASK_USER
# result.reason: str
# result.risk_score: float (0.0-1.0)
# result.audit_signature: str
# result.hitl_event_id: str | None
# result.matched_rule: str
```

### Transport Classes (`maref.integration.mcp_transport`)

| Transport | Constructor | Description |
|-----------|-------------|-------------|
| `StdioTransport` | `(command: list[str])` | Subprocess stdin/stdout |
| `SSETransport` | `(url: str, max_retries=3, timeout=30.0)` | Server-Sent Events |
| `HTTPTransport` | `(endpoint_url: str)` | Simple HTTP POST |
| `InProcessTransport` | `(message_handler: Callable | None)` | Same-process zero-latency |

**Async variants** (in `maref.integration.mcp_transport_async`):

| Transport | Description |
|-----------|-------------|
| `AsyncStdioTransport` | Non-blocking subprocess |
| `AsyncSSETransport` | Non-blocking SSE with asyncio |

All transports implement:
- `connect()` / `disconnect()`
- `send(request: JSONRPCRequest) -> JSONRPCResponse`
- `send_initialize()`, `send_tools_list()`, `send_tool_call()`, `send_resources_list()`

### `MCPPolicyEngine` (`maref.integration.mcp_governance`)

Configurable rule chain for MCP tool call policy evaluation.

```python
from maref.integration.mcp_governance import (
    MCPPolicyEngine,
    AllowMCPProtocolSignals,
    AllowKnownSafeMCPTools,
    BlockDangerousMCPTools,
    BlockDangerousArgs,
    WriteToolRequiresHITL,
    TrustLevelBasedGate,
)

engine = MCPPolicyEngine(rules=[
    AllowMCPProtocolSignals(),
    AllowKnownSafeMCPTools(),
    BlockDangerousMCPTools(),
    BlockDangerousArgs(),
    WriteToolRequiresHITL(),
    TrustLevelBasedGate(),
])

# Custom rule:
from maref.integration.mcp_governance import MCPPolicyRule, MCPPolicyContext, MCPGovernanceResult, MCPDecisionVerdict

class MyCustomRule(MCPPolicyRule):
    def __init__(self):
        super().__init__(rule_id="my-rule-001", description="Block tools over network", priority=70)

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        if "network" in context.tool_name.lower():
            return MCPGovernanceResult(
                verdict=MCPDecisionVerdict.DENY,
                reason="Network tools blocked by policy",
                matched_rule=self.rule_id,
                risk_score=0.8,
            )
        return None
```

### HMAC Audit Utilities

```python
from maref.integration.mcp_governance import sign_audit_entry, verify_audit_signature

# Sign an audit entry
signature = sign_audit_entry(entry, secret_key)

# Verify
is_valid = verify_audit_signature(entry, signature, secret_key)
```

---

## 5. Governance State Machine API

The 10-state Gray-code state machine is the foundation of governance.

```python
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState

sm = GovernanceStateMachine()
```

| Method | Returns | Description |
|--------|---------|-------------|
| `can_transition(target)` | `bool` | Check Gray-code validity |
| `transition(target, reason)` | `bool` | Execute state change |
| `force_stabilize(reason)` | `bool` | BFS shortest path to STABILIZE |
| `force_halt(reason)` | `bool` | BFS shortest path to HALT |
| `snapshot()` | `StateMachineSnapshot` | Pickle-safe snapshot |
| `restore(snapshot)` | `GovernanceStateMachine` | Restore from snapshot |
| `get_history()` | `list[StateTransition]` | Full transition history |
| `get_entropy_trend()` | `dict` | Entropy statistics |
| `is_terminal()` | `bool` | True if HALT |

**Properties:**
- `current_state -> GovernanceState`
- `current_entropy -> int` (0-4)
- `transition_count -> int`
- `valid_next_states -> list[GovernanceState]`

### Governance States

| State | Entropy | Description |
|-------|---------|-------------|
| INIT | 0 | Initial state |
| OBSERVE | 1 | Monitoring/observation |
| ANALYZE | 2 | Analysis |
| EVALUATE | 3 | Evaluation |
| DECIDE | 3 | Decision making |
| ACT | 4 | Execution |
| VERIFY | 4 | Verification |
| STABILIZE | 2 | Stabilization |
| REPORT | 1 | Reporting |
| HALT | 0 | Terminal halt |
