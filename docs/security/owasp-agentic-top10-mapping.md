# OWASP Agentic Top 10 → MAREF Control Mapping

> **Document version**: v1.0 | **Last updated**: 2026-07-15 | **Owner**: MAREF Engineering
> **Strategic context**: This document closes the §5.4 gap in the MAREF Brand Positioning & Hybrid Reinforcement Plan — README claims 10/10 OWASP coverage but the public mapping table was missing.
> **Scope**: Each OWASP Agentic Top 10 risk is mapped to MAREF controls with file paths, key code snippets, TLA+ correspondence, and test coverage. Gaps are honestly documented.

## Executive Summary

MAREF covers all 10 OWASP Agentic Top 10 risks with code-level implementations. The mapping is uneven across three dimensions:

| Dimension | Coverage |
|---|---|
| Code implementation | ✅ 10/10 (all risks have implementation) |
| TLA+ formal specification | ⚠️ 4/10 (HITL, CrossInstance, ConstitutionalRedLines, Consensus) |
| Independent unit tests | ⚠️ 7/10 (Goal Hijacking and Rogue Agents only have indirect coverage) |

**Key honesty note.** The README's claim of "Ed25519 signing for every agent decision" is currently a simulation: `AgentCardSigner.sign_card` uses SHA256 hashing with `algorithm="ed25519-sim"`, and `VerifiableCredential.proof.type` is `"HMAC-SHA256"`. The `AgentCardSignature.algorithm` field defaults to `"ed25519"` but does not invoke real elliptic-curve cryptography. This is tracked as a P0 fix item.

---

## Risk 1: Goal Hijacking

**OWASP definition.** An attacker manipulates an agent's reasoning chain to divert it from its original goal toward an attacker-chosen objective.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Subgoal interceptor | [`src/maref/subgoal/interceptor.py`](https://github.com/maref-org/maref/blob/main/src/maref/subgoal/interceptor.py) | `SubgoalInterceptor`, `InterceptorAction` |
| Chain-of-thought monitor | [`src/maref/subgoal/cot_monitor.py`](https://github.com/maref-org/maref/blob/main/src/maref/subgoal/cot_monitor.py) | `CoTMonitor._compute_risk` |
| Goal inference risk | [`src/maref/subgoal/goal_inferencer.py`](https://github.com/maref-org/maref/blob/main/src/maref/subgoal/goal_inferencer.py) | `GoalInferencer` |
| Delegation graph | [`src/maref/subgoal/delegation_graph.py`](https://github.com/maref-org/maref/blob/main/src/maref/subgoal/delegation_graph.py) | `DelegationGraph` |
| FSM routing | `src/maref/governance/state_machine.py` | `force_stabilize` / `force_halt` |

### Key Code

```python
# src/maref/subgoal/interceptor.py
class InterceptorAction(Enum):
    ALLOW = "allow"
    SLOW = "slow"
    BLOCK = "block"
    HALT = "halt"

# Decision thresholds (interceptor.py L82-92):
# risk >= 0.8 → HALT (force_halt → HALT state)
# risk >= 0.5 → SLOW (force_stabilize → STABILIZE state)
# SafetyGate blocked → BLOCK
# otherwise → ALLOW

# src/maref/subgoal/cot_monitor.py
def _compute_risk(self, hits: list[str], fork_detected: bool) -> float:
    severity = {
        "control": 0.4,                # attempt to control other agents
        "permission_escalation": 0.3,
        "deception_planning": 0.5,     # highest single weight
        "goal_divergence": 0.3,
    }
    risk = sum(severity.get(h, 0.1) for h in hits)
    if fork_detected:
        risk += 0.3
    return min(risk, 1.0)
```

### TLA+ Correspondence

No dedicated TLA+ module for subgoal interception. Indirectly covered by `SafetyGateIntegrityInv` in `MAREF_ConstitutionalRedLines.tla` (safety gate remains active, blocking unconstitutional goals).

### Test Coverage

⚠️ **No independent unit test**. Indirectly covered in `tests/test_loop_interceptor.py` and `tests/security/test_m2_threat_defense.py`.

**Gap action**: Add `tests/subgoal/test_interceptor.py` with explicit goal-hijack scenarios.

---

## Risk 2: Tool Misuse

**OWASP definition.** Agents use tools in unintended ways, exceeding granted permissions or accessing off-bounds resources.

### MAREF Controls (Three Layers)

| Layer | File | Key Symbol |
|---|---|---|
| Per-tool security metadata | [`src/maref/tools/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/tools/registry.py) | `TOOL_REGISTRY`, `security_controls` field |
| Per-loop permission matrix | [`src/maref/loop/protocols.py`](https://github.com/maref-org/maref/blob/main/src/maref/loop/protocols.py) | `ToolPermission`, `ToolBoundary` |
| Path sandbox | [`src/maref/tools/file_server.py`](https://github.com/maref-org/maref/blob/main/src/maref/tools/file_server.py) | `PathSandbox` |

### Key Code

```python
# src/maref/loop/protocols.py
class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    CREATE = "create"
    DENY = "deny"

@dataclass
class ToolBoundary:
    allowed_domains: list[str] = field(default_factory=list)
    permissions: dict[str, ToolPermission] = field(default_factory=dict)

    @classmethod
    def code_generation(cls) -> ToolBoundary:
        # Restrict code-generation loops to filesystem/test/lint/git only
        return cls(
            allowed_domains=["filesystem", "test_framework", "lint", "git"],
            permissions={"filesystem": ToolPermission.WRITE,
                         "test_framework": ToolPermission.EXECUTE,
                         "lint": ToolPermission.EXECUTE,
                         "git": ToolPermission.READ},
        )

# src/maref/tools/registry.py — per-tool security_controls metadata
# shell tool: ["CommandWhitelist", "Timeout", "OutputLimit", "MetacharacterBlock"]
# file tool:  ["PathSandbox", "FileSizeLimit"]
# email tool: ["RecipientWhitelist", "SensitiveWordFilter", "WriteModeGate"]
```

### TLA+ Correspondence

None. Tool permission policies are runtime-enforced, not formalized.

### Test Coverage

✅ `tests/tools/test_registry.py` covers tool registration and permission lookup.

---

## Risk 3: Identity Abuse

**OWASP definition.** Attackers forge agent identities or reuse credentials beyond their intended scope.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Decentralized identifier | [`src/maref/identity/did_registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/identity/did_registry.py) | `AgentDID`, `DIDRegistry` |
| Verifiable credential with TTL | [`src/maref/identity/credential.py`](https://github.com/maref-org/maref/blob/main/src/maref/identity/credential.py) | `VerifiableCredential`, `CredentialStore` |
| Trust engine | [`src/maref/identity/trust_engine.py`](https://github.com/maref-org/maref/blob/main/src/maref/identity/trust_engine.py) | `TrustEngine` |
| OS keyring storage | [`src/maref/security/keyring_store.py`](https://github.com/maref-org/maref/blob/main/src/maref/security/keyring_store.py) | `KeyringStore` |

### Key Code

```python
# src/maref/identity/credential.py
@dataclass
class VerifiableCredential:
    id: str
    issuer: AgentDID
    subject: AgentDID
    issued_at: float
    expires_at: float | None            # time-scoped credential
    credential_type: str
    claims: dict[str, Any]
    proof: dict[str, str] = field(default_factory=dict)

    @classmethod
    def issue(cls, issuer, subject, credential_type, claims,
              ttl_seconds: float | None = 3600, issuer_secret=None):
        # Default TTL=3600s; None = never expires
        ...
        proof = {"type": "HMAC-SHA256", "signature": signature}

# src/maref/identity/did_registry.py
# AgentDID format: did:maref:{namespace}:{agent_short_id}
# agent_short_id = secrets.token_hex(4) — cryptographically random

# CredentialStore supports: revoke, is_revoked, is_expired, list_valid
```

### ⚠️ Honesty Note: Ed25519 Simulation

The README claims "Ed25519 signing for every agent decision". Current code reality:

| Claimed | Actual |
|---|---|
| `AgentCardSignature.algorithm = "ed25519"` | `AgentCardSigner.sign_card` uses SHA256 hash simulation, sets `algorithm = "ed25519-sim"` |
| `VerifiableCredential.proof.type = Ed25519` | `proof.type = "HMAC-SHA256"` |

**P0 fix action**: Replace HMAC-SHA256 with real Ed25519 from `cryptography` library. Add SM2/SM3 alternative for China compliance.

### TLA+ Correspondence

None. Identity credentials are not formalized in TLA+.

### Test Coverage

✅ `tests/unit/test_identity.py` covers DID generation, credential issuance, and revocation.

---

## Risk 4: Supply Chain

**OWASP definition.** Malicious or vulnerable dependencies are introduced through agent skill packages or library updates.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Three-gate skill registry | [`src/maref/marketplace/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py) | `SkillRegistry`, `SkillManifest`, `SkillStatus` |
| SBOM generation | [`src/maref/supply_chain/sbom_generator.py`](https://github.com/maref-org/maref/blob/main/src/maref/supply_chain/sbom_generator.py) | `SBOMGenerator` |
| Vulnerability scanner | [`src/maref/supply_chain/vulnerability_scanner.py`](https://github.com/maref-org/maref/blob/main/src/maref/supply_chain/vulnerability_scanner.py) | `VulnerabilityScanner` |

### Key Code

```python
# src/maref/marketplace/registry.py
class SkillStatus(Enum):
    PENDING = "pending"              # submitted, awaiting review
    STATIC_SCAN = "static_scan"      # passed Gate 1
    SANDBOX_TEST = "sandbox_test"    # passed Gate 2
    APPROVED = "approved"            # passed Gate 3 (human review)
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    FROZEN = "frozen"

@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    dependencies: list[str]          # "skill://name@version"
    author: str
    license: str = "Apache-2.0"
    entrypoint: str
    sandbox_config: dict
    test_cases: list[dict]

# Three-gate admission:
def run_static_scan(self, skill_id) -> SkillValidationResult:  # Gate 1
    # Detects: requests., urllib, socket., open(, eval(, exec(, os.environ

def run_sandbox_test(self, skill_id) -> SkillValidationResult:  # Gate 2
    # Runs test_cases in isolation; production uses gVisor/Firecracker

def approve(self, skill_id) -> None:                            # Gate 3
    # Requires Gate 1 + Gate 2 passed; then manual review

def check_dependency_conflicts(self, skill_id) -> ...:
    # All dependencies must be in APPROVED status (transitive)
```

### TLA+ Correspondence

None. Skill admission is runtime-enforced.

### Test Coverage

✅ `tests/marketplace/test_marketplace.py` covers three-gate admission.
✅ `tests/test_supply_chain.py` covers SBOM and vulnerability scanning.

---

## Risk 5: Code Execution

**OWASP definition.** Untrusted code executes with excessive permissions, allowing sandbox escape or resource exhaustion.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| WASM sandbox executor | [`src/maref/eivl/wasm_sandbox.py`](https://github.com/maref-org/maref/blob/main/src/maref/eivl/wasm_sandbox.py) | `WasmSandboxExecutor`, `SandboxCapabilities`, `ResourceLimits`, `EIVLVerifier` |
| Life-state permission matrix | [`src/maref/life_state/sandbox.py`](https://github.com/maref-org/maref/blob/main/src/maref/life_state/sandbox.py) | `LifeStateSandbox`, `PermissionMatrix` |
| Execution harness | `src/maref/execution/harness.py` | `ExecutionHarness` |

### Key Code

```python
# src/maref/eivl/wasm_sandbox.py
@dataclass
class ResourceLimits:
    max_memory_mb: int = 128
    max_cpu_time_ms: int = 5000
    max_wall_time_ms: int = 10000
    max_stack_size_mb: int = 8
    max_output_size_kb: int = 1024
    max_file_descriptors: int = 16

@dataclass
class SandboxCapabilities:
    allow_network: bool = False
    allow_file_read: bool = False
    allow_file_write: bool = False
    allow_environment_access: bool = False
    allowed_syscalls: list[str] = field(default_factory=list)

    def validate_access(self, capability: str, details: dict | None = None) -> bool:
        # Capability-based access control + syscall whitelist
        ...

# EIVLVerifier records wasm_hash → result_hash evidence chain
# SHA256 signature for non-repudiation
```

WASM execution uses `wasmtime` with `--max-memory` and `--fuel` to enforce hard resource quotas.

### TLA+ Correspondence

None. Sandbox resource limits are runtime-enforced.

### Test Coverage

✅ `tests/test_eivl_wasm.py` covers WASM sandboxing.
✅ `tests/life_state/test_sandbox.py` covers life-state permissions.
✅ `tests/test_policy_sandbox.py` covers policy enforcement.

---

## Risk 6: Memory Poisoning

**OWASP definition.** Attackers inject malicious data into agent memory, corrupting future inferences and decisions.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Weight poison detector | [`src/maref/governance/cross_instance.py`](https://github.com/maref-org/maref/blob/main/src/maref/governance/cross_instance.py) | `WeightPoisonDetector.detect_poisoning` |
| Three-tier memory management | [`src/maref/memory/memory_manager.py`](https://github.com/maref-org/maref/blob/main/src/maref/memory/memory_manager.py) | `ConfidenceLabel`, `SourceAnnotation`, `UserIsolationTag` |
| TLA+ specification | [`src/formal/MAREF_CrossInstance.tla`](https://github.com/maref-org/maref/blob/main/src/formal/MAREF_CrossInstance.tla) | `DetectPoison` action, `Safety` invariant |

### Key Code

```python
# src/maref/governance/cross_instance.py
class WeightPoisonDetector:
    @security_critical
    def detect_poisoning(self, all_weights: dict[str, dict[str, float]]
                         ) -> list[dict[str, Any]]:
        poisoned = []
        if len(all_weights) < 3:
            return poisoned
        # Cross-instance median + MAD (Median Absolute Deviation)
        for key in weight_keys:
            ...
            modified_z = 0.6745 * abs(weights[key] - median) / mad
            if modified_z > 3.0:        # 3-sigma outlier
                poisoned.append({
                    "instance_id": instance_id,
                    "key": key,
                    "modified_z_score": round(modified_z, 4),
                    "severity": "high" if modified_z > 5.0 else "medium",
                })
        return poisoned

# src/maref/memory/memory_manager.py
class ConfidenceLabel(Enum):
    CERTAIN = "certain"      # human-verified
    HIGH = "high"            # multi-source cross-validated
    MEDIUM = "medium"        # single reliable source
    LOW = "low"              # agent inference
    UNCERTAIN = "uncertain"  # external API, unverified

class SourceAnnotation(Enum):
    HUMAN, AGENT_INFERENCE, EXTERNAL_API, OBSERVATION, DERIVED
```

### TLA+ Correspondence

```tla
# src/formal/MAREF_CrossInstance.tla
DetectPoison ==
    /\ \E i \in Instances : weights[i] > 3.0
       /\ poisonedFlags' = [poisonedFlags EXCEPT ![i] = TRUE]

Safety ==
    \A i \in Instances : (poisonedFlags[i] = TRUE) => (weights[i] > 3.0)
```

⚠️ Note: `MAREF_CrossInstance.tla` has no `.cfg` file and is not TLC-checked in CI.

### Test Coverage

✅ `tests/memory/test_memory_manager.py` covers three-tier memory architecture.
⚠️ `WeightPoisonDetector` has no dedicated unit test (covered indirectly in `tests/governance/`).

---

## Risk 7: Insecure Communication

**OWASP definition.** Inter-agent messages are intercepted, forged, or replayed.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| HMAC-signed agent channel | [`src/maref/recursive/zero_trust.py`](https://github.com/maref-org/maref/blob/main/src/maref/recursive/zero_trust.py) | `AgentMessage`, `AgentBoundary`, `ZeroTrustValidator` |
| Signed agent card | [`src/maref/recursive/signed_agent_cards.py`](https://github.com/maref-org/maref/blob/main/src/maref/recursive/signed_agent_cards.py) | `SignedAgentCard`, `AgentCardSigner` |
| Message security scanner | [`src/maref/security/message_security.py`](https://github.com/maref-org/maref/blob/main/src/maref/security/message_security.py) | `MessageSecurityScanner` |

### Key Code

```python
# src/maref/recursive/zero_trust.py
@dataclass
class AgentMessage:
    sender_id: str
    receiver_id: str
    message_type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    nonce: str = ""                           # replay protection
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0                 # time-scoped validity

def _sign_message(self, message: AgentMessage) -> str:
    payload = f"{message.sender_id}|{message.receiver_id}|{message.message_type.value}|{message.nonce}|{message.timestamp:.6f}|{hash(str(message.payload))}"
    return hmac.new(self._shared_secret.encode(), payload.encode(),
                    hashlib.sha256).hexdigest()

# ZeroTrustValidator verifies:
# (a) message age < max_age
# (b) TTL not expired
# (c) nonce not replayed
# (d) HMAC signature valid (constant-time compare_digest)
# (e) no injection patterns detected

# src/maref/security/message_security.py — risk scoring 0-100
# >70 → auto-BLOCK; detects channel misuse (e.g., execute/delete in observation channel)
```

### TLA+ Correspondence

None. Message-level security is runtime-enforced.

### Test Coverage

✅ `tests/recursive/test_r74_zero_trust.py` covers HMAC signing and replay protection.
✅ `tests/recursive/test_r36_signed_agent_cards.py` covers card signing.
✅ `tests/recursive/test_r81_signed_cards_crypto.py` covers cryptographic verification.

---

## Risk 8: Cascading Failures

**OWASP definition.** A single agent's failure propagates through the multi-agent system, causing widespread outages.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Circuit breaker | [`src/maref/governance/circuit_breaker.py`](https://github.com/maref-org/maref/blob/main/src/maref/governance/circuit_breaker.py) | `CircuitBreaker`, `BreakerState`, `BreakerTrip` |
| Chain reaction breaker | `src/maref/recursive/hitl_v2.py` (L229-275) | `ChainReactionBreaker` |
| Saga orchestrator | [`src/maref/recursive/saga_orchestrator.py`](https://github.com/maref-org/maref/blob/main/src/maref/recursive/saga_orchestrator.py) | `SagaOrchestrator`, `BackpressureConfig`, `BlastRadiusController` |

### Key Code

```python
# src/maref/governance/circuit_breaker.py
class CircuitBreaker:
    """States: CLOSED → OPEN → HALF_OPEN → CLOSED"""
    def __init__(self, max_depth: int = 3,
                 max_oscillation_rate: float = 10.0,
                 max_consecutive_failures: int = 5,
                 cooldown_seconds: float = 30.0): ...

    def check_depth(self, depth: int) -> bool:
        if depth > self._max_depth:
            self._trip(f"recursion_depth:{depth}>{self._max_depth}", ...)
            return False
        ...

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._max_failures:
            self._trip(f"consecutive_failures:{self._failure_count}", ...)

# src/maref/recursive/saga_orchestrator.py
# BackpressureConfig: max_concurrent_sagas → throttle callback
# BlastRadiusController.decide() → compensation radius
# _compensate_steps: reversed(completed_steps) for rollback

# src/maref/recursive/hitl_v2.py L229-262
# ChainReactionBreaker: 60s sliding window, ≥5 events with same chain_id
# → break_chain() to prevent cascade avalanche
```

### TLA+ Correspondence

Partially covered by `MAREFDeskJoint.tla` (circuit breaker formalization: `CBMaxBeforeLock`, `LockedNoExecution`, `HALTAbsorbing`). However, this module has no `.cfg` and is not TLC-checked.

### Test Coverage

✅ `tests/governance/test_circuit_breaker.py` covers circuit breaker state transitions.
✅ `tests/recursive/test_r72_saga_orchestrator.py` covers saga orchestration and compensation.

---

## Risk 9: Human Trust Exploitation

**OWASP definition.** Agents exploit human trust through social engineering, deceptive outputs, or unauthorized actions on behalf of users.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| HITL enforcement layer | [`src/maref/governance/hitl_enforcement.py`](https://github.com/maref-org/maref/blob/main/src/maref/governance/hitl_enforcement.py) | `HitlEnforcementLayer`, `InterceptionResult` |
| TLA+ specification | [`src/formal/hitl_governance.tla`](https://github.com/maref-org/maref/blob/main/src/formal/hitl_governance.tla) | 5 invariants + 2 liveness |
| Human decision API | `src/maref/human/decision_api.py` | `DecisionRequest`, `UrgencyLevel`, `DecisionMode` |
| Adversarial auditor | `src/maref/recursive/hitl_v2.py` | `AdversarialAuditor`, `FrequencyMatcher` |

### Key Code

```python
# src/maref/governance/hitl_enforcement.py — 4-tier permission
# permission = config["default_permissions"].get(action, "denied")
#
# "denied":           direct reject, no HITL override
# "hitl_p0_override": only for OpenCode sandbox; urgency=HIGH, timeout=300s
# "requires_hitl":    standard HITL; P1 (risk<0.8) / P0 (risk>=0.8)
# "allowed":          implicit allow

# Risk scoring (hitl_enforcement.py L51-65):
# 13 path-risk regex rules:
#   .pem/.key/.env → 0.95
#   /etc/passwd|shadow|sudoers → 0.95
#   normal source → 0.25-0.30
# + agent trust_penalty + burst penalty (>20 ops/60s = +0.25)

# Smart Auto-allow (L465-486):
# trust_level == "TRUSTED" && dynamic_trust_score >= 0.8 && risk_score < 0.6
# → skip HITL; batch threshold 10/15s
```

### TLA+ Correspondence

```tla
# src/formal/hitl_governance.tla
PERMISSIONS == {"denied", "requires_hitl", "hitl_p0_override", "allowed"}
HITLStates == {"pending", "approved", "rejected", "timeout", "batched"}

# 5 invariants:
DeniedNeverWrites          # denied agents never write
HITLRequiredForWrite       # requires_hitl writes need HITL event
AuditChainImmutability     # auditLog[i].prevHash = auditLog[i-1].hash
FSOnlyOnAllow              # filesystem modification requires allow audit
NoBatchLoss                # every queued request resolves

# 2 liveness:
HITLEventuallyResolves     # pending ~> resolved
TrustedAgentsCanWrite      # trusted agents eventually write
```

⚠️ Note: `HITLRequiredForWrite` is missing from `hitl_governance.cfg` INVARIANTS list — a P1 fix item.

### Test Coverage

✅ `tests/governance/test_hitl_enforcement.py` — main test suite.
✅ `tests/test_hitl_enforcement.py` — integration.
✅ `tests/test_async_hitl.py` — async HITL.
✅ `tests/integration/test_orchestration_hitl_integration.py` — orchestration integration.
✅ `tests/integration/test_hitl_api.py` — API integration.

**Strongest test coverage in MAREF** — 5 dedicated test files.

---

## Risk 10: Rogue Agents

**OWASP definition.** Agents deviate from expected behavior, either due to bugs, adversarial manipulation, or emergent misalignment.

### MAREF Controls

| Control | File | Key Symbol |
|---|---|---|
| Agent registry | [`src/maref/evolution/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/evolution/registry.py) | `AgentRegistry`, `DuplicateAgentError`, `UnknownAgentError` |
| Behavior monitor | [`src/maref/security/behavior_monitor.py`](https://github.com/maref-org/maref/blob/main/src/maref/security/behavior_monitor.py) | `BehaviorMonitor`, `BehaviorBaseline`, `BehaviorAnomaly` |
| DID registry | [`src/maref/identity/did_registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/identity/did_registry.py) | `DIDRegistry` |
| State monitor | `src/maref/security/state_monitor.py` | `StateMonitor` |

### Key Code

```python
# src/maref/evolution/registry.py
class AgentRegistry:
    def register_agent(self, config: GovernanceAgentConfig) -> GovernanceAgent:
        if config.agent_id in self._agents:
            raise DuplicateAgentError(
                f"Agent '{config.agent_id}' is already registered")
        agent = GovernanceAgent(config)
        self._agents[config.agent_id] = agent
        self._ensure_group(config.share_group, config.share_mode)
        self._groups[config.share_group].add_agent(agent)
        return agent

    def unregister_agent(self, agent_id: str) -> GovernanceAgent:
        if agent_id not in self._agents:
            raise UnknownAgentError(...)

# src/maref/security/behavior_monitor.py
class BehaviorMonitor:
    # Updates BehaviorBaseline every 10 samples:
    #   avg_ops_per_minute, avg_chain_depth, tool_usage_distribution
    #
    # detect_anomalies(agent_id):
    #   3-sigma rule (sigma_threshold=3.0)
    #   baseline samples exclude current window (anti-poisoning)
    #
    # _severity_from_sigma:
    #   >5 → critical / >4 → high / >3 → medium / else low
    #
    # detect_emergent_behavior:
    #   ≥2 agents simultaneously high/critical → severity doubled
    #   (detects multi-agent emergent rogue behavior)

@dataclass
class BehaviorAnomaly:
    severity: str                  # critical/high/medium/low
    deviation_sigma: float
    metric_name: str
    expected_value: float
    actual_value: float
    timestamp: float
```

### TLA+ Correspondence

None. Rogue agent detection is runtime-only.

### Test Coverage

⚠️ **No independent unit test**. Indirectly covered in `tests/security/test_m2_threat_defense.py`.

**Gap action**: Add `tests/security/test_behavior_monitor.py` with explicit rogue-agent scenarios (operation rate spike, tool distribution shift, emergent multi-agent anomalies).

---

## Coverage Matrix Summary

| # | Risk | Code | TLA+ | Tests | Gaps |
|---|---|:---:|:---:|:---:|---|
| 1 | Goal Hijacking | ✅ | ⚠️ indirect | ⚠️ indirect | No dedicated tests |
| 2 | Tool Misuse | ✅ | ❌ | ✅ | No TLA+ |
| 3 | Identity Abuse | ✅ | ❌ | ✅ | Ed25519 simulated, not real |
| 4 | Supply Chain | ✅ | ❌ | ✅ | No TLA+ |
| 5 | Code Execution | ✅ | ❌ | ✅ | No TLA+ |
| 6 | Memory Poisoning | ✅ | ✅ | ⚠️ partial | CrossInstance.tla has no .cfg |
| 7 | Insecure Comm | ✅ | ❌ | ✅ | No TLA+ |
| 8 | Cascading Failures | ✅ | ⚠️ partial | ✅ | MAREFDeskJoint.tla has no .cfg |
| 9 | Human Trust | ✅ | ✅ | ✅✅ | Strongest coverage; `HITLRequiredForWrite` missing from .cfg |
| 10 | Rogue Agents | ✅ | ❌ | ⚠️ indirect | No dedicated tests, no TLA+ |

### Aggregate

- **Code implementation**: 10/10 ✅
- **TLA+ formal specification**: 4/10 (HITL, CrossInstance, ConstitutionalRedLines, Consensus)
- **Independent unit tests**: 7/10 (Goal Hijacking and Rogue Agents only indirect)
- **Strongest coverage**: Risk 9 (Human Trust) — 5 test files + 5 TLA+ invariants + 2 liveness
- **Weakest coverage**: Risks 1, 10 — no dedicated unit tests

---

## Prioritized Gap Actions

### P0 (This sprint — W3-W4)

1. **Replace Ed25519 simulation with real Ed25519** in `src/maref/identity/credential.py` and `signed_agent_cards.py`. Add SM2 alternative for China compliance.
2. **Add `tests/subgoal/test_interceptor.py`** with explicit goal-hijack scenarios.
3. **Add `tests/security/test_behavior_monitor.py`** with rogue-agent scenarios.
4. **Add `.cfg` for `MAREF_CrossInstance.tla`** and `MAREFDeskJoint.tla`.
5. **Add `HITLRequiredForWrite` to `hitl_governance.cfg`** INVARIANTS list.

### P1 (Next sprint — W5-W6)

6. **Add TLA+ specifications** for Tool Misuse (R2), Supply Chain (R4), Code Execution (R5).
7. **Add TLA+ specification** for Rogue Agents (R10) — behavior baseline as invariant.
8. **Create `.github/workflows/formal-verify.yml`** to run TLC on all configured modules in CI.

### P2 (Long-term — W8+)

9. **Migrate declarative TLA+ THEOREMs to TLAPS machine-checked proofs**.
10. **Adopt Apalache** for symbolic model checking at production scale.
11. **Independent academic verification** of TLC results (planned for W8 arXiv submission).

---

## References

1. OWASP Foundation. (2026). *Agentic AI Top 10*. https://owasp.org/www-project-agentic-ai/
2. CISA & Five Eyes. (2026, May). *Joint Guidance on Securing Agentic AI Systems*.
3. MAREF Engineering. (2026). *Formal Verification of 10-State Gray Code Governance FSM* (arXiv draft). `docs/research/arxiv-2026-gray-code-fsm-draft.md`
4. MAREF TLA+ specifications — `src/formal/`
5. MAREF governance implementation — `src/maref/governance/`

---

*Maintained by MAREF Engineering. To report a gap or contribute a missing control, please open a GitHub Issue with the `owasp-mapping` label.*
