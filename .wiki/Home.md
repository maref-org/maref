# Welcome to the MAREF Wiki

**MAREF** (Multi-Agent Recursive Engineering Framework) is an Agent Governance Operating System — the kernel for managing the lifecycle, security boundaries, health, and evolutionary direction of agent clusters.

## Quick Links

| Page | Description |
|------|-------------|
| [Architecture](Architecture) | Six-layer governance, state machine, protocol stack |
| [Quick Start](Quick-Start) | 5-minute setup guide |
| [API Reference](API-Reference) | CLI, Python API, and protocol endpoints |
| [Competitive Analysis](Competitive-Analysis) | MAREF vs Anthropic, OpenAI, LangGraph, CrewAI, AutoGen |

## Core Capabilities

### Governance Layer (World-Leading)
- **10-State Gray Code Governance State Machine** — Mathematically provable convergence (6-bit, Hamming distance=1)
- **TLA+ Formal Verification** — 5 theorem proofs (Lyapunov convergence + Sperner completeness)
- **CircuitBreaker** — Auto-lock after 3 consecutive failures + HALT absorb state + 30s cooldown
- **Four-Tier Security Decision Tree** — Rule → Mode → SafetyGate → User, 97% automation rate
- **Dual Drift Detection (LoRA/Ontology)** — KL/JS/Hellinger triple divergence + human arbitration
- **Verifier Cross-Validation** — Weighted majority and unanimous consensus protocols
- **Three Loop Meta-Patterns** — Convergent / Exploratory / Interactive template library

### Operations Layer
- Desktop Agent control via screenshot → parse → keyboard/mouse → verify
- Multi-agent task orchestration with TaskDAG and Saga compensation
- SubAgent context isolation (Git Worktree-style, 96% token savings)
- Mobile-to-desktop task bridging
- Secure browser control via Playwright

### Evolution Layer
- Recursive self-evolution engine (C1 Observe → C2 Optimize → C3 Converge)
- Red-Blue teaming (200 rounds, 5 phases, 7.7× attack intensity gain)
- Chaos engineering with 5 LLM fault injection types
- Three-temperature memory framework (Hot/Warm/Cold)
- Trust Engine v2 with Goodhart manipulation detection

### Ecosystem
- **A2A/MCP Dual Protocol** — Google A2A v0.3 + Anthropic MCP (6 transports)
- **Cross-Framework Adapters** — AutoGen, CrewAI, LangGraph, Dify, Coze
- **OpenTelemetry** — Prometheus, Grafana, OTLP full-link observability
- **Serverless Runtime** — Lambda, Cloud Run ready
- **TypeScript SDK** — `@maref/sdk` npm package

## Project Status

| Metric | Status |
|--------|--------|
| Version | v0.36.0-rc |
| License | Apache 2.0 |
| Tests | 4,300+ |
| Coverage | 82% |
| Python | 3.10+ |

## Getting Help

- [GitHub Discussions](https://github.com/maref-org/maref/discussions)
- [Issue Tracker](https://github.com/maref-org/maref/issues)
- Technical Whitepaper: [English](https://github.com/maref-org/maref/blob/main/docs/MAREF-Technical-Whitepaper-arXiv.md) | [中文](https://github.com/maref-org/maref/blob/main/docs/MAREF-Technical-Whitepaper-zh-CN.md)
