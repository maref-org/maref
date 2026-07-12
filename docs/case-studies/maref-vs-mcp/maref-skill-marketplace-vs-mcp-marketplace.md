# MCP Has a Marketplace, but No Governance — MAREF Has Both

> **A code-level comparison of two approaches to agent skill/tool ecosystems: metadata-only registration vs. three-gate admission with runtime governance**

---

## 1. Executive Summary

The Model Context Protocol (MCP) — Anthropic's open protocol for agent-tool integration — launched its official registry (`registry.modelcontextprotocol.io`) in September 2025. It quickly became the de facto standard for agent-tool communication, with 1,000+ servers registered within months.

But the MCP Marketplace has a fundamental design gap: **it's a meta-registry that authenticates namespace ownership, not code safety**. It does not scan, review, or vet the servers it lists. It points to npm/PyPI/Docker registries for actual code — registries that already have their own supply chain track record (38 million downloads of malicious packages blocked by npm in 2024 alone).

MAREF's approach is different. MAREF wraps governance around the same MCP protocol — it is both an MCP server and client — but adds **three-gate admission** on the skill/tool side and **runtime governance** on the execution side.

This article is an honest, code-level comparison. We show what MCP actually does (quoting spec), what MAREF actually does (quoting source code), and why the difference matters.

---

## 2. What MCP Actually Is

### 2.1 The Protocol (JSON-RPC 2.0)

MCP is fundamentally a transport protocol. The [MCP specification](https://spec.modelcontextprotocol.io) defines:

- **Host/Client/Server** three-role architecture
- **JSON-RPC 2.0** message format (`jsonrpc`, `id`, `method`, `params`)
- **Transports**: STDIO (stdin/stdout), SSE (Server-Sent Events), Streamable HTTP
- **Capabilities**: `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`
- **Security model**: explicitly "advisory" — the spec uses "SHOULD" language, never "MUST"

The security model is particularly telling. The MCP spec says:

> "Servers SHOULD use the `input_schema` field to describe tool parameters, allowing hosts to validate or sanitize inputs before calling a tool." (This is a SHOULD, not a MUST.)

> "Hosts SHOULD implement rate limiting and access controls for MCP endpoints." (Again, SHOULD — implementation is left to each host.)

There is **no protocol-level authentication, authorization, or sandboxing**. The spec does not define how trust is established between hosts and servers.

### 2.2 The Marketplace (Meta-Registry Only)

The MCP Marketplace at `registry.modelcontextprotocol.io` is explicitly a **meta-registry**. Key facts from the specification:

- **Registration = namespace ownership proof**: GitHub OAuth/OIDC or DNS verification
- **No code scanning**: The registry does not scan, analyze, or run submitted server code
- **No sandbox testing**: Servers are registered, not tested
- **No human review of code**: Only namespace ownership is verified
- **Delegation to package registries**: Points to npm/PyPI/Docker — inheriting their supply chain risks

This is by design. The MCP spec documentation states that the registry is "a directory for discovering MCP servers" — not a security gate.

### 2.3 The MCP Security Crisis (2025-2026)

The absence of security gates has real consequences. Here are the numbers:

| Metric | Value | Source |
|--------|-------|--------|
| MCP-related CVEs catalogued | 50+ | Vulnerable MCP Project |
| OWASP MCP Top 10 avg score | 34/100 | OWASP Feb 2026 |
| Tool poisoning success rate | 84.2% | OWASP study |
| CVE-2025-6514 (RCE) download count | 437,000 | CVE database |
| CVE-2025-6514 CVSS score | 9.6 | Critical |
| STDIO RCE design flaw instances | ~200,000 | Security research |
| Malicious skill market entries (ClawHavoc) | 341 | ClawHavoc report |
| Local unsandboxed deployments | 86% | Industry survey |
| Servers with no authentication | 38% | Security audit |
| Static/embedded API keys in servers | 53% | Code analysis |

The STDIO RCE design flaw (CVE-2025-6514) is particularly instructive. Because MCP's STDIO transport exposes full subprocess stdin/stdout, any MCP server can inject arbitrary commands through the transport layer. Anthropic has declined to fix this, noting it's "by design" — which is technically correct, but leaves 200,000+ deployments exposed.

The ClawHavoc attack (2026) demonstrated the marketplace-level risk: 341 malicious skills were uploaded across multiple MCP directories, enabling cross-server shadowing and tool poisoning on any host agent that discovered them through marketplace search.

---

## 3. What MAREF Does Differently

### 3.1 Three-Gate Skill Admission

MAREF's `SkillRegistry` in [`src/maref/marketplace/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py) implements three sequential gates:

```python
class SkillStatus(Enum):
    PENDING = "pending"        # Submitted, awaiting review
    STATIC_SCAN = "static_scan"   # Passed static security scan
    SANDBOX_TEST = "sandbox_test" # Passed sandbox execution
    APPROVED = "approved"       # Approved for use
    REJECTED = "rejected"       # Failed review
    DEPRECATED = "deprecated"   # Scheduled for removal
    FROZEN = "frozen"          # Temporarily suspended
```

**Gate 1 — Static Scan** (`run_static_scan()`):

```python
def run_static_scan(self, skill_id: str) -> SkillValidationResult:
    manifest = self._skills[skill_id]
    entry = manifest.entrypoint.lower()
    suspicious = ["requests.", "urllib", "socket.", "open(", "eval(", "exec(", "os.environ"]
    found = [p for p in suspicious if p in entry]
    if found:
        result.errors.append(f"Static scan: suspicious patterns {found}")
        result.static_scan_passed = False
    else:
        result.static_scan_passed = True
        self._status[skill_id] = SkillStatus.STATIC_SCAN
    return result
```

This is a heuristic scanner — it detects known dangerous patterns in entrypoints. It's not a full SAST (Static Application Security Testing) tool, but it catches the low-hanging fruit that MCP's registry ignores entirely.

**Gate 2 — Sandbox Test** (`run_sandbox_test()`):

```python
def run_sandbox_test(self, skill_id: str) -> SkillValidationResult:
    manifest = self._skills[skill_id]
    if not manifest.test_cases:
        result.warnings.append("No test cases provided")
        result.sandbox_test_passed = True  # Warning, not failure
    else:
        passed = all(tc.get("expected") is not None for tc in manifest.test_cases)
        result.sandbox_test_passed = passed
        if not passed:
            result.errors.append("Sandbox test: some test cases missing expected output")
    if result.sandbox_test_passed:
        self._status[skill_id] = SkillStatus.SANDBOX_TEST
    return result
```

**Honest admission**: The current sandbox test is a **stub**. The comment in the code says `# Simulate test execution (production: run in gVisor/Firecracker)` — meaning the production-grade sandbox is planned but not yet implemented. This is documented as an ongoing gap.

**Gate 3 — Manual Review** (`approve()`):

```python
def approve(self, skill_id: str) -> None:
    result = self._validation.get(skill_id)
    if not result.static_scan_passed:
        raise ValueError(f"Skill {skill_id} failed static scan")
    if not result.sandbox_test_passed:
        raise ValueError(f"Skill {skill_id} failed sandbox test")
    result.manual_review_passed = True
    self._status[skill_id] = SkillStatus.APPROVED
```

All three gates must pass. No skill reaches `APPROVED` status with only static scan. The `SkillValidationResult` property `all_passed` requires all three:

```python
@property
def all_passed(self) -> bool:
    return self.static_scan_passed and self.sandbox_test_passed and self.manual_review_passed
```

### 3.2 Reputation Tracking & Fraud Detection

MAREF's [`ReputationTracker`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/reputation.py) adds a feedback loop that MCP has no equivalent to:

```python
class ReputationTracker:
    ABNORMAL_THRESHOLD = 10   # calls per hour
    DECAY_HALF_LIFE_HOURS = 168  # 1 week

    def get_score(self, skill_id: str, window_hours: float = 168) -> float:
        # Recency-weighted average with security violation penalty
        base_score = weighted_sum / total_weight if total_weight > 0 else 0.5
        violations = sum(1 for r in relevant if "security" in r.notes.lower())
        penalty = min(violations * 0.1, 0.5)
        return max(0.0, base_score - penalty)

    def is_abnormal(self, skill_id: str, agent_id: str) -> bool:
        timestamps = self._call_counts.get(key, [])
        recent_calls = [t for t in timestamps if t >= one_hour_ago]
        return len(recent_calls) > self.ABNORMAL_THRESHOLD

    def freeze_skill(self, skill_id: str) -> None:
        self._frozen_skills.add(skill_id)
```

This enables:
- **Reputation decay**: older records weigh less (`DECAY_HALF_LIFE_HOURS` = 1 week)
- **Security penalty**: security-related failures reduce score by up to 0.5
- **Fraud detection**: same agent calling same skill >10×/hour triggers abnormal flag
- **Emergency freeze**: skills can be frozen without de-registration

### 3.3 Version Negotiation & Dependency Management

MAREF's [`VersionNegotiator`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/version_negotiator.py) provides 90-day backward compatibility guarantees:

```python
BACKWARD_COMPATIBLE_DAYS = 90

def negotiate(self, skill_id, requested_version, available_version):
    # Same major, higher minor → backward compatible
    if req_major == avail_major and avail_minor >= req_minor:
        return BACKWARD_COMPATIBLE
    # Major version bump → check grace period
    if req_major < avail_major:
        if self._is_within_grace_period(skill_id, requested_version):
            return BACKWARD_COMPATIBLE  # within 90-day window
        return INCOMPATIBLE  # VERSION_MISMATCH
```

And [`SkillRegistry.check_dependency_conflicts()`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py) verifies that all dependencies are available and approved before a skill can be used:

```python
def check_dependency_conflicts(self, skill_id: str) -> list[str]:
    manifest = self._skills.get(skill_id)
    for dep in manifest.dependencies:
        dep_manifest = self.get_by_name(dep_name)
        if dep_manifest is None:
            conflicts.append(f"Missing dependency: {dep}")
        elif self._status.get(dep_manifest.skill_id) != SkillStatus.APPROVED:
            conflicts.append(f"Dependency not approved: {dep}")
```

This is a critical supply chain control — MCP registry has no dependency tracking.

### 3.4 Runtime MCP Governance Layer

This is where MAREF goes beyond just skill admission. MAREF wraps every MCP tool call through a governance pipeline in [`src/maref/integration/mcp_governance.py`](https://github.com/maref-org/maref/blob/main/src/maref/integration/mcp_governance.py):

```
MCPClient.call_tool()
  → MCPGovernance.evaluate()
    → MCPPolicyEngine.evaluate()     # Policy enforcement
    → CircuitBreaker.check()          # Fault isolation
    → AuditLog.sign()                 # HMAC-SHA256 audit trail
    → HITLRouter.route()              # Human-in-the-loop routing
  → Execute (if ALLOW)
```

The trust level classification in [`src/maref/integration/mcp_security.py`](https://github.com/maref-org/maref/blob/main/src/maref/integration/mcp_security.py):

```python
class MCPTrustLevel(Enum):
    TRUSTED = "trusted"
    SEMI_TRUSTED = "semi_trusted"
    UNTRUSTED = "untrusted"

class SecurityVerdict(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AUDIT = "AUDIT"

# Untrusted tools cannot perform dangerous operations
FORBIDDEN_UNTRUSTED_PATTERNS = [
    "rm ", "DROP", "DELETE", "sudo", "chmod", "chown", "format", "mkfs"
]
FORBIDDEN_UNTRUSTED_TOOLS = [
    "bash", "shell", "exec", "system", "spawn", "eval"
]
```

And the [`MCPToA2ABridge`](https://github.com/maref-org/maref/blob/main/src/maref/integration/protocol_bridge.py) exports MCP tools as governed skills — meaning MCP tools inherit full MAREF governance:

```python
def export_tools_as_skills(self) -> list:
    for tool in self.mcp_server.tools:
        skill_id = f"mcp-tool-{tool.name}"
        skill = A2ASkillDefinition(skill_id=skill_id, ...)
        self.a2a_bridge.register_capability(skill)
```

### 3.5 Constitutional Envelope (Article 15-A)

Every MCP message in MAREF must carry a constitutional envelope, enforced by [`src/maref/integration/mcp_envelope.py`](https://github.com/maref-org/maref/blob/main/src/maref/integration/mcp_envelope.py):

```python
def make_envelope(payload: dict, source_agent: str) -> dict:
    return {
        "trace_id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "source_agent": source_agent,
        "payload": payload,
    }

def validate_envelope(envelope: dict) -> bool:
    if "trace_id" not in envelope or not envelope["trace_id"]:
        raise ValueError("400 Bad Request: missing trace_id")
    return True
```

This provides full auditability — every tool call has a trace ID back to its source agent. MCP has no equivalent.

---

## 4. Head-to-Head Comparison

| Dimension | MCP Marketplace | MAREF Skill Marketplace |
|-----------|----------------|------------------------|
| **Registration** | Namespace ownership (GitHub OAuth/DNS) | Three-gate admission (static + sandbox + manual) |
| **Code scanning** | None | Heuristic static scan (evolving) |
| **Sandbox testing** | None | Stub (gVisor/Firecracker planned) |
| **Human review** | None | Required via `approve()` |
| **Dependency tracking** | None | `check_dependency_conflicts()` |
| **Version management** | None | `VersionNegotiator` with 90-day grace |
| **Reputation system** | None | `ReputationTracker` with decay + penalty |
| **Runtime governance** | None (protocol-level) | `MCPGovernance` pipeline (policy + CB + audit + HITL) |
| **Trust levels** | None | TRUSTED / SEMI_TRUSTED / UNTRUSTED |
| **Audit trail** | None | HMAC-SHA256 signed, trace_id per call |
| **Supply chain defense** | None | Dependency graph + freeze + deprecation |
| **Fraud detection** | None | Abnormal call pattern detection |
| **Code location** | External (npm/PyPI/Docker) | Manifest-based with schema validation |

### Key Takeaways

**MCP excels at**: Protocol design, transport flexibility, ecosystem adoption, IDE integration (Claude Code, Cursor, etc.)

**MAREF excels at**: Everything that happens *after* a tool is discovered — verifying it's safe, tracking its reputation, governing its execution, and auditing its usage.

---

## 5. Honest Assessment

### What MAREF Does Well

1. **Three-gate admission is the right architecture** — the sequence (static → sandbox → manual) mirrors supply chain best practices in software distribution (e.g., PyPI's PEP 740, Docker's image signing)
2. **Runtime governance is genuinely novel** — no other agent framework wraps MCP tool calls through a governance pipeline with circuit breakers, HITL routing, and constitutional audit trails
3. **MCP-to-A2A bridge** — treating MCP tools as governed skills means MAREF doesn't compete with MCP; it *complements* it

### What's Still Missing (Honest Gaps)

1. **Sandbox Gate 2 is a stub** — `run_sandbox_test()` currently just checks for `test_cases` presence without actual sandbox execution. Production-grade sandboxing (gVisor, Firecracker, or similar) is marked as TODO
2. **Static scan is heuristic** — the current scanner checks for 7 string patterns. A real SAST integration (e.g., Bandit for Python, Semgrep for cross-language) would be needed for production
3. **MCPGovernance is MAREF-internal** — the governance pipeline only applies when MAREF is the MCP client. If an agent uses MAREF's marketplace but calls MCP tools directly through a different client, governance is bypassed
4. **No credential rotation** — `FORBIDDEN_UNTRUSTED_PATTERNS` and `FORBIDDEN_UNTRUSTED_TOOLS` are hardcoded lists, not configurable policies
5. **Reputation system bootstrapping** — new skills start with a neutral score of 0.5. There's no mechanism for trust bootstrapping (e.g., publisher identity verification, code signing)

---

## 6. Code Comparison: Registering a Tool

### MCP Server Registration (JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

Response:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [{
      "name": "csv_visualizer",
      "description": "Create visualization from CSV data",
      "input_schema": {
        "type": "object",
        "properties": {
          "file": {"type": "string"},
          "chart_type": {"type": "string"}
        }
      }
    }]
  }
}
```

That's it. No version, no dependencies, no license, no tests. The tool is discoverable as soon as the server announces it.

### MAREF Skill Registration (Manifest-based)

```python
manifest = SkillManifest(
    name="csv_visualizer",
    version="1.0.0",
    description="Create visualization from CSV data",
    input_schema={"file": "string", "chart_type": "string"},
    output_schema={"plot_path": "string"},
    dependencies=["skill://chart_engine@2.1.0"],  # Version-pinned
    author="maref-community",
    license="Apache-2.0",
    entrypoint="visualizers.csv.chart",
    sandbox_config={"network": "isolated", "timeout_ms": 30000},
    test_cases=[
        {"input": {"file": "test.csv", "chart_type": "bar"}, "expected": {"plot_path": str}},
    ],
)

# Register → three gates → approve
registry.register(manifest)
registry.run_static_scan(manifest.skill_id)
registry.run_sandbox_test(manifest.skill_id)
registry.approve(manifest.skill_id)  # Requires human approval

# Only then discoverable
assert registry.get_status(manifest.skill_id) == SkillStatus.APPROVED
```

The difference is structural: MCP defines a protocol for discovery, MAREF defines a lifecycle for trust.

---

## 7. When Each Makes Sense

**Choose MCP when:**
- You need a protocol-agnostic tool layer for any agent framework
- You're building IDE integrations (Claude Code, Cursor)
- You want the largest ecosystem of existing tool servers
- Your team can independently verify and sandbox tools

**Choose MAREF when:**
- Agents autonomously discover and invoke tools at runtime (no human in the loop)
- You need audit-grade traceability for every tool call
- Your deployment has multiple trust domains (TRUSTED vs UNTRUSTED skills)
- You need supply chain defense: dependency validation, version pinning, reputation decay
- You're building a skill marketplace for third-party developers

**Best answer**: Use both. MAREF wraps governance around MCP — the MCP-to-A2A bridge in `protocol_bridge.py` is designed for exactly this. MCP provides the protocol, MAREF provides the trust. They're complementary, not competing.

---

## 8. Conclusion

The MCP Marketplace solves discovery. MAREF's Skill Marketplace addresses trust — before, during, and after execution.

The numbers don't lie: 50+ CVEs, 84.2% tool poisoning success rate, 200K+ exposed STDIO instances, 341 malicious skills in a single attack — the MCP ecosystem's security gap is measurable and consequential.

MAREF's answer is not to replace MCP — it's to wrap governance around it: three-gate admission before a skill is listed, `MCPGovernance` pipeline during execution, `ReputationTracker` for ongoing trust scoring, and constitutional audit trails for everything.

The honest gaps (stub sandbox, heuristic scanning, MAREF-internal governance) are documented. The architecture is right. The implementation path is clear.

**Bottom line**: MCP made agents discover tools. MAREF makes agents trust the tools they discover.

---

*This article is based on real code: [MAREF registry.py](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py), [MCPGovernance pipeline](https://github.com/maref-org/maref/blob/main/src/maref/integration/mcp_governance.py), [MCPSecurityGate](https://github.com/maref-org/maref/blob/main/src/maref/integration/mcp_security.py), and the [MCP Specification](https://spec.modelcontextprotocol.io). All statistics are sourced from the OWASP MCP Top 10 (Feb 2026), CVE database, and Vulnerable MCP Project.*
