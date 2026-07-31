---
sidebar_position: 1
title: Introduction
description: MAREF — Agent Governance OS
---

# Introduction

**MAREF (Multi-Agent Recursive Evolution Framework)** is an open-source **Agent Governance Operating System** that provides formal verification, constitutional governance, self-healing infrastructure, and comprehensive compliance for multi-agent systems.

## Why MAREF?

As AI agents become autonomous and interconnected, governing their behavior becomes critical. MAREF addresses four fundamental challenges:

| Challenge | MAREF Solution |
|-----------|---------------|
| **Safety** | 5 constitutional red lines enforced by MetaAgentClosure |
| **Trust** | 8-trigram trust states with Gray-code transitions |
| **Interoperability** | Dual protocol (A2A v0.3 + MCP 2025-03-26) for maximum ecosystem compatibility |
| **Compliance** | HMAC-SHA256 audit chains, EU AI Act, SOC 2 modules |

## Core Capabilities

- **Six-Layer Governance** — Heaven (constitutional) → Human (HITL) → Earth (zero trust) → Trigram (roles) → Hexagram (contracts) → Change (evolution)
- **34-State Gray-Code FSM** (10 governance + 24 agent) — Hamming distance=1 transitions guarantee stability
- **TLA+ Formal Verification** — 5 proven invariants running at runtime
- **A2A Protocol v0.3** — Google-standard Agent-to-Agent task delegation
- **MCP Protocol 2025-03-26** — Anthropic-standard Model Context Protocol with 6 transports
- **Self-Healing** — 8 Self-* modules for autonomous recovery
- **Governance as a Service** — Multi-tenant REST API for governance decisions
- **Compliance** — HMAC audit, EU AI Act, SOC 2, HIPAA, PCI-DSS

## Quick Links

- [Quickstart](/docs/quickstart) — Get started in 5 minutes
- [Architecture](/docs/architecture) — Deep dive into the six-layer model
- [API Reference](/docs/api-reference) — Complete API documentation
- [Cookbook](/docs/cookbook/governed-agent-setup) — Step-by-step guides
- [Deployment](/docs/deployment) — K8s, Docker, desktop deployment

## Project Status

- **CI/CD**: [GitHub Actions CI](https://github.com/maref-org/maref/actions/workflows/ci.yml)
- **Code Coverage**: [Codecov](https://codecov.io/gh/maref-org/maref)
- **SBOM**: [`sbom.spdx.json`](https://github.com/maref-org/maref/blob/main/sbom.spdx.json)
- **Chaos Reports**: [`.chaos-reports/`](https://github.com/maref-org/maref/blob/main/.chaos-reports/)

## License

Apache-2.0 — see [LICENSE](https://github.com/maref-org/maref/blob/main/LICENSE) for details.
