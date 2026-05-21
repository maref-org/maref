# P1-P7: MCP/A2A 协议标准化 — Implementation Notes

## Architecture Decisions
- **Dual protocol support**: MCP (Anthropic) for tool/resource access + A2A (Google) for agent discovery/communication
- **JSON-RPC 2.0**: Standard transport for both protocols, ensuring interoperability
- **Protocol bridge pattern**: MCP→A2A skill export automates capability synchronization
- **InProcess transport**: MCP Server uses InProcessTransport for zero-latency local communication

## MCP Server Implementation
- Tools: Governance state queries, entropy readings, observation collection, anomaly detection, compliance checks
- Resources: Agent states (application/maref-state+json), entropy metrics (application/maref-entropy+json), metrics (text/plain)
- Prompts: Compliance snapshot generation, governance overview generation
- Security: All tool calls pass through MCPSecurityGate with delegation chain verification

## A2A Bridge Implementation
- Agent Card: Self-describing JSON-LD document per A2A v0.3 spec
- Task protocol: Bidirectional state mapping between A2A TaskState and MAREF GovernanceState
- mTLS transport: Mutual TLS with certificate pinning for agent-to-agent communication

## Protocol Bridge
- MCP Tools exported as A2A Skills with auto-generated metadata
- MCP Resources exported as A2A Skill capabilities
- State machine synchronization: A2A Task events trigger Gray Code state transitions

## Sidecar MCP Integration
- POST `/api/mcp` endpoint accepts standard JSON-RPC 2.0 requests
- GET `/api/mcp/.well-known` provides server discovery
- SidecarMCPBridge class handles tool routing and result formatting

## Test Coverage
- MCP Server: Protocol compliance tests (JSON-RPC schema validation)
- A2A Bridge: Agent Card generation, Task lifecycle, mTLS handshake
- Protocol Bridge: Tool→Skill export, state mapping, interop tests with LangChain/AutoGen
- Sidecar MCP: Initialize, tools/list, resources/list, tools/call, prompts/list
- Coverage: 85-90% across protocol modules