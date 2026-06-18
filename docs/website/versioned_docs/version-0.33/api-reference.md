---
sidebar_position: 4
title: API Reference
description: Complete MAREF API reference
---

# MAREF API Reference

> Version: v0.33.0-rc | Sidecar: v0.32.0-rc | GaaS: v0.28.0

This document covers all public APIs: Sidecar REST API, Governance-as-a-Service (GaaS) API, A2A Python API, and MCP Python API.

---

## 1. Sidecar REST API

The Sidecar is the main HTTP interface for MAREF, running on port 8000 by default.

### 1.1 MCP Endpoints

#### `POST /api/mcp`
MCP JSON-RPC endpoint. Accepts standard MCP methods.

**Supported methods:** `initialize`, `tools/list`, `resources/list`, `prompts/list`, `tools/call`

#### `GET /api/mcp/.well-known`
Returns MCP capabilities metadata.

### 1.2 A2A Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/a2a/task/send` | POST | Submit a task via JSON-RPC 2.0 |
| `/api/a2a/task/{task_id}` | GET | Get task status |
| `/api/a2a/task/cancel` | POST | Cancel a running task |
| `/api/a2a/task/state` | POST | Push state update |
| `/api/a2a/task/{task_id}/stream` | GET | SSE streaming |

### 1.3 Agent Card & Discovery

#### `GET /.well-known/agent-card.json`
Returns the A2A agent card for discovery with HMAC-signed capability declarations.

### 1.4 MCP Gateway Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mcp/gateway/health` | GET | Gateway health status |
| `/api/mcp/gateway/tools/call` | POST | Route tool call through gateway |
| `/api/mcp/gateway/tools` | GET | List aggregated tools |

### 1.5 Health & Status

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/status` | Service status |
| `GET /api/version` | Version info |

### 1.6 Observability & Management

| Endpoint | Description |
|----------|-------------|
| `GET /api/agents` | List discovered agents |
| `GET /api/observations` | Recent observations |
| `GET /api/anomalies` | Detected anomalies |
| `GET /api/metrics` | Prometheus metrics |
| `GET /api/sessions` | Session management |
| `GET /api/providers` | LLM providers |
| `GET /api/skills` | Available skills |
| `GET /api/tasks` | Task management |
| `GET /api/filetree` | Workspace file tree |

### 1.7 Compliance Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/compliance/register` | Register agent for compliance |
| `GET /api/compliance/agents` | List compliance agents |
| `POST /api/compliance/check-action` | Check action compliance |
| `POST /api/compliance/snapshot` | Take compliance snapshot |
| `GET /api/compliance/audit-log/{agent_id}` | Get agent audit log |

### 1.8 Immunity Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/immunity/cooldown` | List cooldown entries |
| `GET /api/immunity/cooldown/summary` | Cooldown summary |
| `GET /api/immunity/genes` | Gene audit trail |

---

## 2. Governance API (GaaS)

Base path: `/api/v1/gaas`. All endpoints require `X-API-Key` header.

### `POST /api/v1/gaas/govern`
Execute a governance decision for an agent action.

**Verdict values:** `ALLOW`, `DENY`, `ASK_USER`, `DEFER`

### `POST /api/v1/gaas/hitl/request`
Request human approval.

### HITL Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/gaas/hitl/{event_id}/approve` | POST | Approve HITL event |
| `/api/v1/gaas/hitl/{event_id}/deny` | POST | Deny HITL event |
| `/api/v1/gaas/hitl/pending` | GET | List pending HITL events |

### Trust & Audit

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/gaas/trust/score` | GET | Get trust score |
| `/api/v1/gaas/audit/query` | POST | Query audit logs |
| `/api/v1/gaas/cb/status` | GET | Circuit breaker status |
| `/api/v1/gaas/health` | GET | GaaS health check |

### Session Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/v1/gaas/session/declare` | POST | Declare session |
| `GET /api/v1/gaas/session/active` | GET | Active sessions |
| `GET /api/v1/gaas/session/{id}` | GET | Session status |
| `POST /api/v1/gaas/session/{id}/complete` | POST | Complete session |
| `POST /api/v1/gaas/session/{id}/step` | POST | Increment step |

---

## 3. A2A Python API

### `A2ABridge` (`maref.integration.a2a_bridge`)

Wraps MAREF governance as an A2A-compatible agent.

| Method | Description |
|--------|-------------|
| `build_agent_card(base_url)` | Build A2A agent card |
| `create_task(description, context)` | Create governed task |
| `get_task(task_id)` | Get task by ID |
| `delegate_task(task_id, target_url)` | Delegate to another agent |
| `sync_state_from_a2a(task_id, a2a_state)` | Sync A2A state to MAREF |
| `force_halt_task(task_id, reason)` | Force halt a task |

### `A2AClient` (`maref.integration.a2a_client`)

HTTP client for A2A communication.

| Method | Description |
|--------|-------------|
| `send_task(agent_url, skill_id, input, metadata)` | Send task to agent |
| `get_task(agent_url, task_id)` | Get task status |
| `cancel_task(agent_url, task_id, reason)` | Cancel task |
| `discover_agent_card(agent_url)` | Fetch agent card |

### `A2ADiscovery` (`maref.integration.a2a_discovery`)

Agent registry with capability-based lookup.

| Method | Description |
|--------|-------------|
| `register_agent(agent_id, url, capabilities)` | Register agent |
| `discover_agents(capability_filter)` | Find agents by capability |
| `health_check(agent_id)` | Check agent health |

---

## 4. MCP Python API

### `MCPServer` (`maref.integration.mcp_server`)

| Method | Description |
|--------|-------------|
| `register_tool(name, description, schema, handler)` | Register MCP tool |
| `register_resource(uri, name, mime, handler)` | Register MCP resource |
| `register_prompt(name, description, args, handler)` | Register MCP prompt |
| `handle_request(request, trust_level)` | Handle MCP request |

### `MCPClient` (`maref.integration.mcp_client`)

| Method | Description |
|--------|-------------|
| `register_server(config)` | Connect to MCP server |
| `register_governance(governance)` | Attach governance pipeline |
| `list_tools(conn)` | List server tools |
| `call_tool(conn, name, args, trust_level)` | Call tool with governance |

### `MCPSecurityGate` (`maref.integration.mcp_security`)

Three-tier trust model: `TRUSTED`, `SEMI_TRUSTED`, `UNTRUSTED`

### Transports (`maref.integration.mcp_transport`)

| Transport | Description |
|-----------|-------------|
| `StdioTransport` | Subprocess stdin/stdout |
| `SSETransport` | Server-Sent Events |
| `HTTPTransport` | Simple HTTP POST |
| `InProcessTransport` | Same-process zero-latency |
| `AsyncStdioTransport` | Non-blocking subprocess |
| `AsyncSSETransport` | Non-blocking SSE |

### `MCPGovernance` (`maref.integration.mcp_governance`)

Full governance pipeline with policy engine, circuit breaker, HMAC audit, and HITL routing.

### `MCPPolicyEngine`

Configurable rule chain with built-in and custom policy rules.

### Governance State Machine

| Method | Description |
|--------|-------------|
| `can_transition(target)` | Check Gray-code validity |
| `transition(target, reason)` | Execute state change |
| `force_stabilize(reason)` | BFS shortest path to STABILIZE |
| `force_halt(reason)` | BFS shortest path to HALT |
| `snapshot()` | Pickle-safe snapshot |
| `restore(snapshot)` | Restore from snapshot |

### Governance States

| State | Entropy | Description |
|-------|---------|-------------|
| INIT | 0 | Initial state |
| OBSERVE | 1 | Monitoring |
| ANALYZE | 2 | Analysis |
| EVALUATE | 3 | Evaluation |
| DECIDE | 3 | Decision making |
| ACT | 4 | Execution |
| VERIFY | 4 | Verification |
| STABILIZE | 2 | Stabilization |
| REPORT | 1 | Reporting |
| HALT | 0 | Terminal halt |

See the [full API reference on GitHub](https://github.com/maref-org/maref/blob/main/docs/api-reference.md) for complete request/response schemas and advanced usage.
