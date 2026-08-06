# Architecture

> Full architecture documentation: [`docs/architecture.md`](https://github.com/maref-org/maref/blob/main/docs/architecture.md)

## Six-Layer Governance Model

MAREF's governance is structured as six conceptual layers inspired by the I Ching (易经):

```
Layer           Direction     Governance Role
─────           ─────────     ───────────────
天极 (Heaven)    ↓            Constitution, meta-rules, immutable redlines
人极 (Human)     ─            Human approval, HITL/HOTL/HATL
地极 (Earth)     ↑            Zero-trust security foundation, least privilege
经卦 (Trigram)   ↓            Role orchestration, dynamic composition
别卦 (Hexagram)  ─            Capability contracts, constraint enforcement
爻变 (Change)    ↑            Self-evolution, mutation, innovation
```

### 天极 (Heaven Pole) — Constitutional Meta-Governance
- 5 immutable constitutional red lines enforced by `MetaAgentClosure`
- TLA+ formally verified invariants (INV-001 through INV-005)
- `RuleFreezeZone` — module-level write protection
- `MetaCircuitBreaker` — cross-layer safety breaker

### 人极 (Human Pole) — Human-in-the-Loop
- Three HITL modes: HITL (blocking), HOTL (supervised), HATL (audit-only)
- `EscalationProposal` + `DeadlineNegotiator` for time-bounded approvals
- Carbon-Silicon Symbiosis workflow

### 地极 (Earth Pole) — Zero Trust Foundation
- `ZeroTrustValidator` — every request must prove identity and authorization
- `TrustBoundaryManager` — cross-domain call authorization
- `SafetyGateV2` — gradual weakening detection

### 经卦 (Trigram Pole) — Role Orchestration
- 8 trigram trust states (QIAN through DUI) with Gray-code transitions
- `FourPhaseGovernance`: OLD_YANG → LESSER_YIN → LESSER_YANG → OLD_YIN

### 别卦 (Hexagram Pole) — Capability Contracts
- `CapabilityContract` — capability, constraint, and verification specification
- `IntegrityBaseline` — cross-system consistency check

### 爻变 (Change Pole) — Evolution & Mutation
- Recursive self-evolution with SAEB benchmark self-testing
- Immune system gene degradation detection

## Runtime Architecture

```
                  MAREF: Agent Governance OS
    ┌─────────────────────────────────────────────────────────┐
    │  Application Layer ─── LangGraph / CrewAI / AutoGen     │
    │              / Anthropic                                │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  Governance Layer ─── MAREF                             │
    │             · State Machine · Circuit Breaker           │
    │             · 4-Tier Decision Tree · Identity/Trust     │
    │             · Drift Detection · Formal Verification      │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  Communication Layer ─── A2A / MCP                      │
    └─────────────────────────────────────────────────────────┘
```

## Protocol Stack

- **A2A (Agent-to-Agent)** — Google A2A v0.3 for inter-agent discovery and task delegation
- **MCP (Model Context Protocol)** — Anthropic MCP with 6 transport modes for tool exposure
- **Sidecar** — Observation sidecar providing MCP bridge, drift detection, telemetry collection
- **REST API** — FastAPI-based `/api/v1/` endpoints for governance, audit, and health

## Key Source Modules

| Module | Location | Purpose |
|--------|----------|---------|
| Loop Engine | `src/maref/loop/` | ConvergentLoop, ExploratoryLoop, InteractiveLoop |
| Governance | `src/maref/governance/` | State machine, circuit breaker, audit, drift |
| Security | `src/maref/security/` | Trust boundaries, identity, sanitization |
| Execution | `src/maref/execution/` | Harness, scheduler, lifecycle management |
| Sidecar | `src/sidecar/` | MCP bridge, observation, telemetry |
| Formal | `src/maref/formal/` | TLA+ specifications and verification |
