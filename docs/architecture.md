# MAREF Architecture

> Version: v0.36.0-rc | Last updated: 2026-06-19

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
- Source: `src/maref/recursive/zero_trust.py`, `src/maref/security/trust_boundary/`, `src/maref/recursive/safety_gate_v2.py`

### 经卦 (Trigram Pole) -- Role Orchestration
- 8 trigram trust states (QIAN through DUI) with Gray-code transitions (Hamming distance = 1)
- `FourPhaseGovernance`: OLD_YANG -> LESSER_YIN -> LESSER_YANG -> OLD_YIN with increasing oversight
- `RoleComposer` + `HexagramWorkflow` for dynamic agent role assembly
- Source: `src/maref/recursive/eight_trigrams_governance.py`, `src/maref/recursive/four_phase_governance.py`

### 别卦 (Hexagram Pole) -- Capability Contracts
- `CapabilityContract` -- strict input/output schemas for every agent capability
- `BlastRadiusController` -- threat assessment for capability combinations
- `PermissionMatrix` -- fine-grained scope-based access control
- Source: `src/maref/recursive/capability_contracts.py`, `src/maref/recursive/blast_radius.py`, `src/maref/recursive/permission_matrix.py`

### 爻变 (Change Pole) -- Self-Evolution
- Recursive self-evolution engine: observe -> diagnose -> architect -> execute -> heal -> optimize
- `ChaosInjector` -- 5 failure types for resilience testing
- Red/Blue adversarial engine -- 200 rounds, 5-phase attacks
- Source: `src/maref/evolution/`, `src/maref/recursive/chaos_injector.py`, `src/maref/redblue/red_blue_engine.py`

---

## 2. Core Runtime Architecture

The runtime is divided into five architectural layers, each with distinct responsibilities:

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

### 2.1 Meta Layer

The meta layer provides self-referential safety guarantees -- the framework's immune system.

#### MetaAgentClosure (`src/maref/recursive/meta_agent_closure.py`)
- Manages 5 constitutional red lines (RL-001 through RL-005)
- Prevents agents from modifying their own safety constraints
- Enforces that only `human_constitution_maker` can modify red lines
- Reviews all evolution decisions against red lines
- Proves 5 TLA+ invariants at runtime

```python
from maref.recursive.meta_agent_closure import MetaAgentClosure

closure = MetaAgentClosure()
result = closure.submit_decision(
    agent_id="agent-42",
    decision_type=EvolutionDecisionType.POLICY_UPDATE,
    description="Update trust evaluation weights",
)
# result.status == "rejected" (violates RL-005)
```

#### MetaGovernance (`src/maref/recursive/meta_governance.py`)
- Wraps inner governance layer recursively (max depth = 3)
- `MetaCircuitBreaker`: CLOSED -> OPEN (3 trips) -> HALF_OPEN (30s cooldown) -> CLOSED
- Cross-layer audit trail ties inner/outer states together
- `RecursionDepthExceededError` when depth > 3

```python
from maref.recursive.meta_governance import MetaGovernance

meta = MetaGovernance(depth=0)
meta.wrap(inner_governance)
meta.signal_inner_trip()  # records fault in cross-layer audit
meta.try_recover()        # attempt half-open after cooldown
```

### 2.2 Governance Layer

The core governance engine that decides what agents are allowed to do.

#### Eight Trigrams Governance (`src/maref/recursive/eight_trigrams_governance.py`)
- 8 trust states with Gray-code adjacency (Hamming distance = 1)
- Each trigram has a trust threshold, autonomy scope, audit frequency, and evolution permission
- Transitions are constrained to adjacent trigrams only
- Trust score auto-determines current trigram

| Trigram | Trust Threshold | Autonomy | Audit Freq | Human Signoff |
|---------|----------------|----------|------------|---------------|
| QIAN (乾) | 0.90 | complete | 24h | No |
| KUN (坤) | 0.30 | passive | 1h | Yes |
| ZHEN (震) | 0.50 | crisis | 4h | No |
| XUN (巽) | 0.60 | observation | 6h | Yes |
| KAN (坎) | 0.55 | navigation | 3h | No |
| LI (离) | 0.70 | dialogue | 12h | Yes |
| GEN (艮) | 0.80 | stability | 8h | No |
| DUI (兑) | 0.65 | interconnection | 12h | No |

#### Four Phase Governance (`src/maref/recursive/four_phase_governance.py`)
- 4 phases mirroring the yin-yang cycle: OLD_YANG (full autonomy) -> LESSER_YIN -> LESSER_YANG -> OLD_YIN (observation only)
- Permissions decrease as oversight increases
- Red line permissions include QUARANTINE for OLD_YANG
- BFS-based shortest path transitions

#### Rule Freeze Zone (`src/maref/recursive/rule_freeze_zone.py`)
- Freezes critical parameter groups: `rl_table`, `safety_gate_params`, `core_components`, `circuit_breaker_hard_limits`, `audit_immutability`, `meta_freeze`
- Context manager `freeze_operation()` prevents writes to frozen targets
- `FreezeBlockedError` raised on violation

#### Safety Gate V2 (`src/maref/recursive/safety_gate_v2.py`)
- `detect_core_removal` -- prevents removal of 5 core components
- `detect_gradual_weakening` -- blocks 3 consecutive decreases of the same target
- `detect_combinatorial_explosion` -- prevents batch changes affecting 2+ core components
- `validate_decomposition` -- limits subtasks (max 12, dangerous max 8)
- `validate_handoff` -- prevents privilege escalation between agents
- `validate_capability_assignment` -- combinatorial risk analysis
- `detect_ai_stench` -- scans generated code for AI-generation patterns

### 2.3 Orchestration Layer

Coordinates multi-agent task execution with formal planning and fault tolerance.

#### Self-* Modules (8 modules)
| Module | File | Responsibility |
|--------|------|----------------|
| SelfArchitect | `self_architect.py` | Architecture snapshots, bottleneck detection, refactoring proposals |
| SelfDiagnostician | `self_diagnostician.py` | Full-dimension health diagnosis |
| SelfExecutor | `self_executor.py` | Code generation -> AST validation -> sandbox -> deploy -> rollback |
| SelfHealer | `self_healer.py` | Partition recovery, fault strategies |
| SelfKnowledge | `self_knowledge.py` | Structured knowledge extraction from codebase |
| SelfObserver | `self_observer.py` | Change observation, test success tracking |
| SelfOptimizer | `self_optimizer.py` | Mutation -> sandbox -> adopt/revert, saturation detection |
| SelfVersion | `self_version.py` | Dependency locking, API drift detection |

#### Task Planning
- `FormalPlanner` -- forward-chaining and cost-based planners
- `TaskDecomposer` -- DAG-based task decomposition
- `HybridDecomposer` -- combines multiple decomposition strategies
- `SagaOrchestrator` -- distributed sagas with compensation transactions
- `RoleComposer` -- hexagram-based workflow composition

### 2.4 Execution Layer

Manages agent lifecycle, skill execution, and multi-agent coordination.

#### Agent 24-State FSM (`src/maref/recursive/agent_24_state_machine.py`)
- 64 states (8 trigrams x 8 sub-states)
- Gray-code transitions (Hamming distance = 1)
- Pickle-safe snapshot/restore

#### Skill System
- `MarefSkill` with `HexagramTrigger` and `ContextActivation` (`skill_schema.py`)
- `SkillLoader` -- multi-directory loading with priority merging (`skill_loader.py`)
- `SkillExecutor` -- input/output validation (`skill_executor.py`)
- `SkillTrigger` -- bagua state transition validation (`skill_trigger.py`)

#### Multi-Agent Coordination
- `FederationCoordinator` -- gossip protocol for state propagation
- `DistributedBFT` -- Byzantine fault tolerance consensus
- `DistributedCRDT` -- conflict-free replicated data types
- `StigmergySwarm` -- pheromone-based swarm intelligence
- `DecisionMarket` -- prediction market for agent decisions

#### Federation Aggregation Platform (`src/maref/federation/`)
A 9-module platform for cross-organization agent aggregation, identity
translation, and economic settlement. Wired up by
`create_default_federation()`:

| Module | Purpose |
|--------|---------|
| `gateway.py` | `FederationGateway` — unified entry point: AIC↔DID translation, ACS parsing, dispatch |
| `discovery.py` | `FederatedDiscovery` — ADP v2.00 cross-org discovery, peer forwarding |
| `catalog.py` | `FederatedCatalog` — searchable inverted index of federated agents |
| `trust.py` | `FederatedTrustEngine` — `effective = α·local + (1−α)·federated` with peer-report decay |
| `policy.py` | `FederationPolicyEngine` — 3 layers, 4 conflict strategies (FEDERATION_WINS, LOCAL_WINS, DENY_IF_CONFLICT, MOST_RESTRICTIVE) |
| `hitl.py` | `CrossOrgHITL` — cross-org human approval with auto-approve intra-org and escalation |
| `marketplace.py` | `AgentMarketplace` — listings, pricing models, reviews, capability search |
| `metering.py` | `TaskMeteringEngine` — per-task metrics + contribution scores |
| `settlement.py` | `FederatedSettlement` — cross-org billing, proposals, ledger |

**Integration to mainline** (v0.36+):
- `FederatedPlanExecutor` (`orchestration/federated_plan_executor.py`) — wraps
  `PlanExecutor`; routes `federation_dispatch` steps through the gateway with
  automatic task metering.
- `FederatedSagaOrchestrator` (`recursive/federated_saga_orchestrator.py`) —
  wraps `SagaOrchestrator`; evaluates policy per step, routes `DEFER`
  decisions to `CrossOrgHITL`, tracks trust per agent.

```python
from maref.federation import create_default_federation
from maref.orchestration import FederatedPlanExecutor, Plan, PlanStep

platform = create_default_federation(server_id="maref-prod-01")
executor = FederatedPlanExecutor(platform=platform)
plan = Plan(plan_id="p1", steps=[
    PlanStep(task_id="t1", action="federation_dispatch",
             params={"required_capability": "research",
                     "consumer_org": "GammaCorp", "provider_org": "Acme",
                     "token_count": 1000, "complexity_score": 0.5}),
])
report = executor.execute(plan)  # routes via gateway, meters, bills
```

#### Hooks
- `HookChain` -- ordered hook execution pipeline
- `HookRegistry` -- centralized hook registration
- `HookTemplates` -- reusable hook patterns
- `HookTopics` -- topic-based hook dispatch

### 2.5 Infrastructure Layer

#### Audit
- `AuditLogger` (`governance/audit.py`) -- append-only JSONL log with HMAC-SHA256 signing
- `UnifiedAuditStore` (`recursive/unified_audit.py`) -- cross-layer record storage
- `AuditSchema` -- standardized cross-layer audit entries
- Integrity verification via Merkle chain hashing

#### Trust
- `TrustEngineV2` (`recursive/trust_engine_v2.py`) -- 5-factor weighted trust scoring
- `TrustV2` (`recursive/trust_v2.py`) -- Goodhart's law anti-manipulation detection
- `ReliabilityMatrix` (`recursive/reliability_matrix.py`) -- reliability scoring
- `AgentCreditRatingSystem` (`recursive/agent_credit_rating.py`)

#### Safety
- `TrustBoundaryManager` (`security/trust_boundary/`) -- cross-domain call authorization
- `@security_critical` decorator (`security/decorators.py`)
- `Sanitizer` (`security/sanitizer.py`) -- input/output sanitization
- `KeyringStore` (`security/keyring_store.py`) -- macOS Keychain integration

#### Compliance
- `Registry` -- framework registration, capability mapping
- `ComplianceMonitor` -- real-time compliance checking
- `DataSovereignty` -- data residency enforcement
- EU AI Act, Five Eyes, HIPAA, PCI-DSS modules
- `ReportGenerator` -- automated compliance report generation

#### Memory
- 3-tier memory: Hot (working), Warm (short-term), Cold (long-term)
- `MemoryManager` (`memory/memory_manager.py`)
- `MemoryThreeTemperature` -- memory temperature control
- `ExperiencePool` -- pattern-based experience storage

#### GaaS (Governance as a Service)
Multi-tenant REST API that exposes governance decisions as a service:
- `GovernanceRouter` -- full governance pipeline
- `CircuitBreakerPool` -- per-tenant breaker management
- `HITLService` -- human approval routing
- `AuditLogService` -- queryable audit storage
- `TrustScoreService` -- trust score tracking
- `TenantManager` -- tenant lifecycle management

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

### 3.1 A2A (Agent-to-Agent) Protocol v0.2.6

Google-standard A2A protocol for inter-agent task delegation.

**Components:**
- `A2ABridge` -- wraps governance (state machine + audit + circuit breaker) as A2A-compatible agent
- `A2AClient` -- sends tasks to other agents, polls status, pushes state updates
- `A2ADiscovery` -- agent registry with capability-based lookup and health checks
- `A2AServer` -- FastAPI router exposing A2A REST endpoints
- `A2ASecureTransport` -- encrypted transport layer
- `SignedAgentCard` -- cryptographically signed capability declarations

**Flow:**
```
Agent A                          Agent B
  │                                │
  │── POST /api/a2a/task/send ────>│  (JSON-RPC 2.0)
  │<── { id, status.submitted } ──│
  │                                │
  │── GET /api/a2a/task/{id} ─────>│
  │<── { status.working } ────────│
  │                                │
  │── POST /api/a2a/task/state ───>│  (state push notification)
  │<── { success } ──────────────│
  │                                │
  │── POST /api/a2a/task/cancel ──>│
  │<── { success, state.canceled }│
```

**Agent Card Discovery:**
```
Agent A                          Agent B
  │                                │
  │── GET /.well-known/agent-card.json ──>│
  │<── { agentCard, signature } ─────────│
  │                                │
  │ verify signature                │
  │ match capabilities              │
  │ send task                       │
```

### 3.2 MCP (Model Context Protocol)

Anthropic-standard MCP for tool discovery, resource access, and prompt templates.

**Components:**
- `MCPServer` -- tool/resource/prompt registration and JSON-RPC dispatch
- `MCPClient` -- server management, tool calls with governance enforcement
- `MCPSecurityGate` -- trust-level authorization, rate limiting, OAuth
- `MCPGateway` -- multi-backend tool routing with audit logging
- `MCPGovernance` -- full policy engine for MCP tool calls
- 6 transport types: Stdio, SSE, HTTP, InProcess, plus async variants

**Transport Types:**

| Transport | Use Case | Latency |
|-----------|----------|---------|
| Stdio | Local subprocess MCP servers | Low |
| SSE | Remote MCP servers with streaming | Medium |
| HTTP | Simple remote MCP calls | Medium |
| InProcess | Same-process zero-latency | Zero |
| AsyncStdio | Non-blocking stdio | Low |
| AsyncSSE | Non-blocking SSE | Medium |

**Governance Pipeline:**
```
MCPClient.call_tool()
  → MCPGovernance.evaluate()
    → MCPPolicyEngine.evaluate()    (rule chain)
      → AllowMCPProtocolSignals     (priority 100)
      → AllowKnownSafeMCPTools      (priority 90)
      → BlockDangerousMCPTools      (priority 80)
      → BlockDangerousArgs          (priority 75)
      → WriteToolRequiresHITL       (priority 60)
      → TrustLevelBasedGate         (priority 50)
    → CircuitBreaker.check()
    → HMAC-SHA256 Audit Log
    → HITL Router (if ASK_USER)
  → transport.send_tool_call()
```

### 3.3 A2A + MCP Interaction

The two protocols work together:
- Use A2A for task delegation between agents (high-level orchestration)
- Use MCP for tool execution within an agent (low-level capability access)
- Both flow through the same governance pipeline (audit, CB, HITL)

---

## 4. Security Architecture

### 4.1 Trust Boundary Manager

Enforces cross-domain call authorization. Every inter-module or inter-agent call must be authorized.

- `TrustBoundaryManager.check(source, target, action)` -> `bool`
- Domain isolation prevents privilege escalation
- Source: `src/maref/security/trust_boundary/`

### 4.2 Safety Gate V2

Multi-dimensional safety checks executed before every governance decision:

1. Core removal detection
2. Gradual weakening detection (3 consecutive decreases)
3. Combinatorial explosion prevention
4. Subtask explosion prevention
5. Handoff privilege escalation prevention
6. Capability assignment validation
7. AI generation stench detection
8. Capability contract validation

### 4.3 MCP Security Gate

Three-tier trust model for MCP tool calls:
- `TRUSTED` -- all tools allowed
- `SEMI_TRUSTED` -- shell/exec tools denied (or audited during sessions)
- `UNTRUSTED` -- shell/exec tools and dangerous patterns denied

Additional protections:
- Rate limiting (100 req/60s default)
- Delegation depth checking (max 5)
- OAuth 2.1 token authentication and validation
- Forbidden patterns: `rm `, `DROP`, `DELETE`, `sudo`, `chmod`, `chown`, `format`, `mkfs`
- Forbidden tools: `bash`, `shell`, `exec`, `system`, `spawn`, `eval`

### 4.4 HMAC Audit Trail

Every audit entry is signed with HMAC-SHA256:
```
entry = {
  id, timestamp, event_type, actor, action, details,
  metadata, previous_hash, chain_hash, hmac_signature
}
```
- `AuditLogger.log()` creates entries with automatic signing
- `AuditLogger.verify_integrity()` validates the entire chain
- Chain hash links entries together (tampering breaks the chain)
- Production: set `MAREF_HMAC_SECRET_KEY` environment variable

### 4.5 OAuth 2.1

- `OAuthTokenProvider` -- client credentials and refresh token flows
- `OAuthMiddleware` -- token validation and context extraction
- JWT decoding with expiration checking
- Scope-based authorization (`maref:mcp` default scope)

---

## 4.5 Loop Engineering Integration

MAREF treats agent loops as first-class governance citizens. See [Loop Engineering Integration](./loop-engineering-integration.md) for:

- **Three meta-patterns** — Convergent Loop (monotonic improvement), Exploratory Loop (diversity coverage), Interactive Loop (human-in-the-loop)
- **Scenario-Governance Design Matrix** — mapping loop patterns to governance strategy and tool boundaries
- **Design flow** — Step-by-step process for adding governance to any agent loop
- **Template specs** — `docs/loop-engineering/` with per-pattern Evaluator interfaces, tool whitelists, and stop conditions
- **Roadmap** — `src/maref/loop/` subsystem planned for v0.36.0-rc

---

## 5. Flow Diagrams

### 5.1 Task Creation -> Governance -> Execution -> Audit

```
User/Agent
  │
  │  POST /api/a2a/task/send
  ▼
A2ABridge.create_task()
  │
  ├── GovernanceStateMachine.transition(INIT)
  ├── AuditLogger.log("a2a_task_created")
  ├── CircuitBreaker.check_depth()
  │
  ▼
EightTrigramsGovernance.transition()
  │  (auto-adjust based on trust score)
  │
  ├── SafetyGateV2.validate_decomposition()
  ├── SafetyGateV2.validate_handoff()
  ├── MetaAgentClosure.review_evolution_decision()
  │
  ▼  [ALLOW]
TaskDecomposer.decompose()
  │
  ├── FormalPlanner.plan()
  ├── SagaOrchestrator.orchestrate()
  ├── AgentDispatcher.dispatch()
  │
  ▼
Agent24StateMachine.execute()
  │
  ├── SkillExecutor.run()
  ├── Hooks.execute()
  │
  ▼
AuditLogger.log("task_completed")
  │
  ├── HMAC-SHA256 signature
  ├── Chain hash link
  └── JSONL storage
```

### 5.2 A2A Delegation Flow

```
Agent A                          Agent B
  │                                │
  │ 1. A2ADiscovery.discover()     │
  │<── agent card ────────────────│
  │                                │
  │ 2. Verify signature            │
  │ 3. Match capabilities          │
  │                                │
  │ 4. A2AClient.send_task()       │
  │── POST /api/a2a/task/send ────>│
  │                                │
  │ 5. A2ABridge.create_task()     │
  │ 6. Governance check            │
  │ 7. Audit log                   │
  │                                │
  │<── { task_id, submitted } ────│
  │                                │
  │ 8. Poll GET /api/a2a/task/{id} │
  │── GET ────────────────────────>│
  │<── { completed } ─────────────│
  │                                │
  │ 9. sync_state_from_a2a()       │
  │10. Audit log delegation result │
```

### 5.3 MCP Tool Call with Governance Gate

```
Client (Agent/User)
  │
  │  tools/call { name: "write_file", args: {...} }
  ▼
MCPClient.call_tool()
  │
  ├── MCPGovernance.evaluate()
  │     │
  │     ├── MCPPolicyEngine (rule chain)
  │     │     ├── Is it a protocol signal?          → ALLOW
  │     │     ├── Is it a known safe tool?           → ALLOW
  │     │     ├── Is it a dangerous tool?            → ASK_USER
  │     │     ├── Are args dangerous?                → DENY
  │     │     ├── Is it a write tool?                → ASK_USER
  │     │     └── Trust level gate                   → ALLOW/AUDIT/DENY
  │     │
  │     ├── MCSCircuitBreakerMonitor.should_trip()
  │     ├── CircuitBreaker.check_depth()
  │     ├── AuditLogEntry (HMAC-SHA256 signed)
  │     └── HITL Router (if ASK_USER)
  │
  ▼  [ALLOW]
InProcessTransport.send_tool_call()
  │
  ▼
MCPServer._handle_tools_call()
  │
  ├── MCPSecurityGate.check()
  └── MCPTool.handler(args)
  │
  ▼
Result returned to client
```

---

## 6. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 64-state Gray Code FSM | Hamming distance=1 transitions guarantee stability |
| TLA+ formal verification | Prove correctness before implementation |
| 5 constitutional red lines | Immutable safety constraints enforced at meta layer |
| 8-trigram trust states | Trust-aware autonomy scaling with smooth transitions |
| HMAC-SHA256 audit chain | Tamper-evident logging for ISO 27001 compliance |
| Dual protocol (A2A + MCP) | Interoperability with Google and Anthropic ecosystems |
| 6 transport types | Support all deployment modes (local, remote, embedded) |
| Recursion depth limit=3 | Prevents infinite governance loops |
| 5% spot check rate | Balances autonomy with human oversight |

---

## 7. Module Dependency Map

```
maref/
├── recursive/          # Core governance, orchestration, execution, infra
│   └── meta_agent_closure.py      depends on: (none — constitutional bedrock)
│   └── eight_trigrams_governance  depends on: audit_schema
│   └── four_phase_governance      depends on: unified_audit
│   └── safety_gate_v2             depends on: capability_contracts (optional)
│   └── agent_24_state_machine     depends on: (standalone)
│
├── governance/         # Core state machine, audit, CB
│   └── state_machine.py          depends on: governance/types, governance/constants
│   └── audit.py                  depends on: recursive/unified_audit
│   └── circuit_breaker.py        depends on: (standalone)
│
├── integration/        # A2A, MCP, Gateway, HITL bridges
│   └── a2a_bridge.py             depends on: governance/*, integration/*
│   └── mcp_governance.py         depends on: governance/circuit_breaker, integration/*
│   └── mcp_server.py             depends on: mcp_transport
│
├── gaas/               # Multi-tenant REST API
│   └── governance_router.py      depends on: gaas/*, governance/*
│
├── security/           # Trust boundaries, cryptography, sanitization
│
├── compliance/         # Regulatory compliance modules
│
└── identity/           # DID + W3C Verifiable Credentials
```
