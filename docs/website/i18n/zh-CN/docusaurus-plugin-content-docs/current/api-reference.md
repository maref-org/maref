---
sidebar_position: 4
title: API 参考
description: 完整的 MAREF API 参考文档
---

# MAREF API Reference

> Version: v0.33.0-rc | Sidecar: v0.32.0-rc | GaaS: v0.28.0

This document covers all public APIs: Sidecar REST API, Governance-as-a-Service (GaaS) API, A2A Python API, and MCP Python API.

## Sidecar REST API

The Sidecar runs on port 8000 with endpoints for MCP, A2A, compliance, immunity, and observability.

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/mcp` | MCP JSON-RPC |
| `GET /.well-known/agent-card.json` | A2A agent card |
| `GET /api/health` | Health check |
| `GET /api/agents` | List agents |
| `GET /api/metrics` | Prometheus metrics |

## Governance API (GaaS)

Base path: `/api/v1/gaas` with `X-API-Key` authentication.

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/gaas/govern` | Execute governance decision |
| `POST /api/v1/gaas/hitl/request` | Request human approval |
| `GET /api/v1/gaas/trust/score` | Get trust score |
| `POST /api/v1/gaas/audit/query` | Query audit logs |

## A2A Python API

`A2ABridge`, `A2AClient`, and `A2ADiscovery` classes for inter-agent communication.

## MCP Python API

`MCPServer`, `MCPClient`, `MCPSecurityGate`, `MCPGateway`, and `MCPGovernance` classes with 6 transport types.

See the [full API reference on GitHub](https://github.com/maref-org/maref/blob/main/docs/api-reference.md) for complete request/response schemas.
