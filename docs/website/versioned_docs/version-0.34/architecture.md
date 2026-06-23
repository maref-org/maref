---
sidebar_position: 3
title: Architecture
description: MAREF six-layer governance architecture
---

# MAREF Architecture

> Version: v0.34.0-rc | Last updated: 2026-06-17

## Overview

MAREF (Multi-Agent Recursive Evolution Framework) is an Agent Governance Operating System. It provides six-layer governance, formal verification via TLA+, a 64-state Gray-code finite state machine, dual-protocol communication (A2A + MCP), and a full audit/security/compliance infrastructure.

This document describes the architecture from four perspectives: the six-layer governance model, the runtime architecture layers, the protocol layer, and the security architecture.

---

## 1. Six-Layer Governance

MAREF's governance is structured as six conceptual layers inspired by the I Ching (易经), each mapping to operational autonomy and trust levels.

```
Layer         Direction       Governance Role
─────         ─────────       ───────────────
天极 (Heaven)  ↓              宪法、元规则、不可修改的红线
人极 (Human)   ─              人类审批、HITL/HOTL/HATL
地极 (Earth)   ↑              零信任安全底座、最小权限
经卦 (Trigram) ↓              角色编排、动态组合
别卦 (Hexagram)─              能力契约、约束止行
爻变 (Change)  ↑              自我演化、变异创新
```

### 天极 (Heaven Pole) -- Constitutional Meta-Governance
- Constitutional red lines (5 immutable rules enforced by `MetaAgentClosure`)
- TLA+ formally verified invariants (INV-001 through INV-005)
- `RuleFreezeZone` -- module-level write protection for critical parameters
- `MetaCircuitBreaker` -- cross-layer safety breaker with HALT absorb state
- Source: `src/maref/recursive/meta_agent_closure.py`, `src/maref/recursive/rule_freeze_zone.py`

### 人极 (Human Pole) -- Human-in-the-Loop
- Three HITL modes: HITL (blocking), HOTL (supervised), HATL (audit-only)
- `EscalationProposal` + `DeadlineNegotiator` for time-bounded approvals
- Carbon-Silicon Symbiosis workflow: Human confirm -> Agent execute -> Self review -> Spot check
- 5% random spot check rate for agent-only tasks
- Source: `src/maref/recursive/hitl_v2.py`, `src/maref/recursive/carbon_silicon_symbiosis.py`

### 地极 (Earth Pole) -- Zero Trust Foundation
- `ZeroTrustValidator` -- every request must prove identity and authorization
- `TrustBoundaryManager` -- cross-domain call authorization
- `SafetyGateV2` -- core component protection, gradual weakening detection, combinatorial explosion prevention
- Source: `src/maref/recursive/zero_trust.py`, `src/maref/security/trust_boundary/`

### 经卦 (Trigram Pole) -- Role Orchestration
- 8 trigram trust states (QIAN through DUI) with Gray-code transitions (Hamming distance = 1)
- `FourPhaseGovernance`: OLD_YANG -> LESSER_YIN -> LESSER_YANG -> OLD_YIN with increasing oversight
- `RoleComposer` + `HexagramWorkflow` for dynamic agent role assembly

### 别卦 (Hexagram Pole) -- Capability Contracts
- `CapabilityContract` -- strict input/output schemas for every agent capability
- `BlastRadiusController` -- threat assessment for capability combinations
- `PermissionMatrix` -- fine-grained scope-based access control

### 爻变 (Change Pole) -- Self-Evolution
- Recursive self-evolution engine: observe -> diagnose -> architect -> execute -> heal -> optimize
- `ChaosInjector` -- 5 failure types for resilience testing
- Red/Blue adversarial engine -- 200 rounds, 5-phase attacks

---

## 2. Core Runtime Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        META LAYER                                │
│  MetaAgentClosure · MetaGovernance · MetaCircuitBreaker          │
│  ConstitutionalRedLine · InvariantProofEngine                    │
├─────────────────────────────────────────────────────────────────┤
│                      GOVERNANCE LAYER                            │
│  EightTrigramsGovernance · FourPhaseGovernance                   │
│  RuleFreezeZone · SafetyGateV2 · ZeroTrustValidator              │
│  BlastRadiusController · PermissionMatrix · HITL v2             │
├─────────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                            │
│  Self-*(8) · SagaOrchestrator · RoleComposer                     │
│  FormalPlanner · TaskDecomposer · HybridDecomposer               │
├─────────────────────────────────────────────────────────────────┤
│                      EXECUTION LAYER                              │
│  Agent24StateMachine · Skills · Federation · Hooks · Swarm       │
│  AgentMarketplace · AgentEconomy · AgentHandoff                  │
├─────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE LAYER                          │
│  Audit · Trust · Safety · Compliance · Memory · GaaS             │
│  Observability · Identity · Keyring · SupplyChain                │
└─────────────────────────────────────────────────────────────────┘
```

The runtime is divided into five architectural layers. See the full [Architecture document on GitHub](https://github.com/maref-org/maref/blob/main/docs/architecture.md) for details on each layer including the Meta Layer, Governance Layer, Orchestration Layer, Execution Layer, and Infrastructure Layer.

---

## 3. Protocol Layer Architecture

MAREF implements two standard protocols for agent communication:

```
┌───────────────────────────────────────────────────────┐
│                    MAREF Agent                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │           A2ABridge (Agent-to-Agent)             │  │
│  │  Agent Card · Task Send/Get/Cancel · State Push  │  │
│  │  A2ADiscovery · A2AClient · SecureTransport      │  │
│  └─────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────┐  │
│  │        MCP Bridge (Model Context Protocol)       │  │
│  │  MCPServer · MCPClient · MCPSecurityGate         │  │
│  │  MCPGateway · MCPGovernance · Transports(6)      │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

### A2A (Agent-to-Agent) Protocol v0.2.6

Google-standard A2A protocol for inter-agent task delegation with signed agent cards, capability-based discovery, and JSON-RPC 2.0 messaging.

### MCP (Model Context Protocol)

Anthropic-standard MCP for tool discovery, resource access, and prompt templates with 6 transport types: Stdio, SSE, HTTP, InProcess, AsyncStdio, AsyncSSE.

---

## 4. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 64-state Gray Code FSM | Hamming distance=1 transitions guarantee stability |
| TLA+ formal verification | Prove correctness before implementation |
| 5 constitutional red lines | Immutable safety constraints enforced at meta layer |
| 8-trigram trust states | Trust-aware autonomy scaling with smooth transitions |
| HMAC-SHA256 audit chain | Tamper-evident logging for ISO 27001 compliance |
| Dual protocol (A2A + MCP) | Interoperability with Google and Anthropic ecosystems |
| Recursion depth limit=3 | Prevents infinite governance loops |
| 5% spot check rate | Balances autonomy with human oversight |

See the [full architecture document](https://github.com/maref-org/maref/blob/main/docs/architecture.md) for complete details on all layers, flow diagrams, and module dependency maps.
