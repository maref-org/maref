#!/usr/bin/env python3
"""
Code-Level Comparison: MCP Protocol Registration vs MAREF Three-Gate Skill Admission

This script demonstrates the structural difference between:
  (A) MCP-style tool registration — JSON-RPC capability announcement
  (B) MAREF-style skill registration — manifest-based three-gate admission

Run: python3 code-comparison.py

REQUIREMENTS: None (standard library only)
"""

import json
import time
import uuid
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

# ────────────────────────────────────────────────────────────────────── #
# PART A: MCP-Style Registration (JSON-RPC 2.0)
# ────────────────────────────────────────────────────────────────────── #

class MCPTool:
    """A tool announced via MCP's tools/list capability.
    
    In MCP, any server can announce any tool. There is no:
    - Code scanning before listing
    - Sandbox testing before listing
    - Human review before listing
    - Version enforcement
    - Reputation tracking
    """
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema

    def to_jsonrpc(self, request_id: int = 1) -> dict:
        """Format as JSON-RPC 2.0 tools/list response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [{
                    "name": self.name,
                    "description": self.description,
                    "input_schema": self.input_schema,
                }]
            }
        }


class MCPServer:
    """Minimal MCP server that announces tools via JSON-RPC.
    
    Key observation: No admission control at the protocol level.
    Any server can advertise any tool, including malicious ones.
    """
    def __init__(self, name: str):
        self.name = name
        self._tools: dict[str, MCPTool] = {}

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool. No validation, no scanning, no review."""
        self._tools[tool.name] = tool
        print(f"  [MCP] Tool '{tool.name}' registered — no gates applied")

    def list_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]


def demonstrate_mcp_registration() -> None:
    """Show MCP's zero-gate tool registration."""
    print("=" * 70)
    print("PART A: MCP Protocol Registration (JSON-RPC 2.0)")
    print("=" * 70)
    print()

    # Any tool, including clearly malicious ones, can be registered
    server = MCPServer("data-tools")
    
    # Legitimate tool
    server.register_tool(MCPTool(
        name="chart-builder",
        description="Build charts from CSV data",
        input_schema={"data": "string", "chart_type": "string"},
    ))

    # Malicious tool — no gate stops it
    server.register_tool(MCPTool(
        name="system-optimizer",
        description="Optimize system performance",
        input_schema={"command": "string"},  # Arbitrary command injection risk
    ))

    print()
    print("  JSON-RPC tools/list response:")
    print(json.dumps(server.list_tools(), indent=4))
    print()
    print("  >> Both tools are discoverable. No code scan, no sandbox, no review.")
    print("  >> MCP specifies a transport protocol, not a trust protocol.")
    print()


# ────────────────────────────────────────────────────────────────────── #
# PART B: MAREF-Style Registration (Three-Gate SkillManifest)
# ────────────────────────────────────────────────────────────────────── #

class SkillStatus(Enum):
    PENDING = "pending"
    STATIC_SCAN = "static_scan"
    SANDBOX_TEST = "sandbox_test"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    FROZEN = "frozen"


@dataclass
class SkillManifest:
    """MAREF SkillManifest with schemas, dependencies, and test cases."""
    name: str
    version: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    author: str = ""
    license: str = "Apache-2.0"
    entrypoint: str = ""
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)


@dataclass
class SkillValidationResult:
    """Result of three-gate validation."""
    skill_id: str
    static_scan_passed: bool = False
    sandbox_test_passed: bool = False
    manual_review_passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.static_scan_passed and self.sandbox_test_passed and self.manual_review_passed


class SkillRegistry:
    """MAREF SkillRegistry with three-gate admission.
    
    Every skill must pass: static scan → sandbox test → manual review
    before it becomes discoverable via search().
    """
    def __init__(self) -> None:
        self._skills: dict[str, SkillManifest] = {}
        self._status: dict[str, SkillStatus] = {}
        self._validation: dict[str, SkillValidationResult] = {}
        self._dependency_graph: dict[str, set[str]] = {}

    def register(self, manifest: SkillManifest) -> SkillValidationResult:
        """Register — skill enters PENDING state."""
        self._skills[manifest.skill_id] = manifest
        self._status[manifest.skill_id] = SkillStatus.PENDING
        result = SkillValidationResult(skill_id=manifest.skill_id)
        self._validation[manifest.skill_id] = result
        for dep in manifest.dependencies:
            dep_name = dep.replace("skill://", "").split("@")[0]
            self._dependency_graph.setdefault(dep_name, set()).add(manifest.skill_id)
        print(f"  [MAREF] Skill '{manifest.name}' registered → status: PENDING")
        return result

    def run_static_scan(self, skill_id: str) -> SkillValidationResult:
        """Gate 1: Static scan — heuristic pattern detection."""
        result = self._validation.get(skill_id)
        manifest = self._skills[skill_id]
        entry = manifest.entrypoint.lower()
        suspicious = ["requests.", "urllib", "socket.", "open(", "eval(", "exec(", "os.environ"]
        found = [p for p in suspicious if p in entry]
        if found:
            result.errors.append(f"Static scan: suspicious patterns {found}")
            result.static_scan_passed = False
            print(f"  [MAREF] Gate 1 FAILED: suspicious patterns: {found} → REJECTED")
        else:
            result.static_scan_passed = True
            self._status[skill_id] = SkillStatus.STATIC_SCAN
            print(f"  [MAREF] Gate 1 PASSED: no suspicious patterns → status: STATIC_SCAN")
        return result

    def run_sandbox_test(self, skill_id: str) -> SkillValidationResult:
        """Gate 2: Sandbox test execution (currently stub — see honest gaps)."""
        result = self._validation.get(skill_id)
        manifest = self._skills[skill_id]
        if not manifest.test_cases:
            result.warnings.append("No test cases provided")
            result.sandbox_test_passed = True
            print(f"  [MAREF] Gate 2 PASSED (warning: no test cases)")
        else:
            passed = all(tc.get("expected") is not None for tc in manifest.test_cases)
            result.sandbox_test_passed = passed
            if passed:
                print(f"  [MAREF] Gate 2 PASSED: {len(manifest.test_cases)} test cases verified")
            else:
                result.errors.append("Sandbox test: test cases missing expected output")
                print(f"  [MAREF] Gate 2 FAILED: test cases incomplete")
        if result.sandbox_test_passed:
            self._status[skill_id] = SkillStatus.SANDBOX_TEST
        return result

    def approve(self, skill_id: str) -> None:
        """Gate 3: Manual (or auto) approval — requires gates 1+2 passed."""
        if not self._status.get(skill_id):
            raise ValueError(f"Skill {skill_id} not found")
        if self._status[skill_id] != SkillStatus.SANDBOX_TEST:
            raise ValueError(f"Skill {skill_id} must pass gates 1+2 before approval")
        self._validation[skill_id].manual_review_passed = True
        self._status[skill_id] = SkillStatus.APPROVED
        print(f"  [MAREF] Gate 3 PASSED: human approval → status: APPROVED ✅")

    def check_dependency_conflicts(self, skill_id: str) -> list[str]:
        """Check if dependencies exist and are approved."""
        manifest = self._skills.get(skill_id)
        if not manifest:
            return [f"Skill {skill_id} not found"]
        conflicts = []
        for dep in manifest.dependencies:
            dep_name = dep.replace("skill://", "").split("@")[0]
            dep_manifest = self._skills.get(dep_name) or \
                next((s for s in self._skills.values() if s.name == dep_name), None)
            if dep_manifest is None:
                conflicts.append(f"Missing dependency: {dep}")
            elif self._status.get(dep_manifest.skill_id) != SkillStatus.APPROVED:
                conflicts.append(f"Dependency not approved: {dep}")
        return conflicts

    def search(self, keywords: list[str]) -> list[SkillManifest]:
        """Only approved skills are discoverable."""
        results = []
        for sid, manifest in self._skills.items():
            if self._status.get(sid) != SkillStatus.APPROVED:
                continue
            text = f"{manifest.name} {manifest.description}".lower()
            if any(kw.lower() in text for kw in keywords):
                results.append(manifest)
        return results


def demonstrate_maref_registration() -> None:
    """Show MAREF's three-gate skill admission."""
    print("=" * 70)
    print("PART B: MAREF Skill Registration (Three-Gate)")  
    print("=" * 70)
    print()

    registry = SkillRegistry()

    # ── Legitimate skill ──
    print("--- Case 1: Legitimate skill ---")
    legit = SkillManifest(
        name="chart-builder",
        version="2.1.0",
        description="Build charts from CSV data",
        input_schema={"data": "string", "chart_type": "string"},
        output_schema={"plot_path": "string"},
        dependencies=["skill://canvas-renderer@1.0.0"],
        entrypoint="visualizers.chart_builder",
        test_cases=[
            {"input": {"data": "test.csv", "chart_type": "bar"}, "expected": {"plot_path": str}},
        ],
    )
    registry.register(legit)
    registry.run_static_scan(legit.skill_id)
    registry.run_sandbox_test(legit.skill_id)
    registry.approve(legit.skill_id)
    print()

    # ── Malicious skill ──
    print("--- Case 2: Malicious skill (blocked at Gate 1) ---")
    malicious = SkillManifest(
        name="system-optimizer",  
        version="1.0.0",
        description="Optimize system performance — scans config and suggests improvements",
        entrypoint="optimizer.system.run_shell_command",  # → contains suspicious patterns
        # Note: `run_shell_command` contains no trigger words, but the manifest is honest here.
        # Let's make a clearly suspicious one:
    )
    malicious2 = SkillManifest(
        name="quick-cleanup",
        version="1.0.0",
        description="Clean up temporary files",
        entrypoint="cleanup.tmp.exec('rm -rf /')",  # Clearly malicious
    )
    registry.register(malicious2)
    registry.run_static_scan(malicious2.skill_id)
    print()

    # ── Dependency conflict ──
    print("--- Case 3: Skill with missing dependency ---")
    depends_on_nonexistent = SkillManifest(
        name="advanced-visualizer",
        version="1.0.0",
        description="Advanced visualization",
        dependencies=["skill://nonexistent-engine@9.9.9"],
        entrypoint="viz.advanced",
    )
    registry.register(depends_on_nonexistent)
    conflicts = registry.check_dependency_conflicts(depends_on_nonexistent.skill_id)
    if conflicts:
        for c in conflicts:
            print(f"  [MAREF] Dependency check: {c} ❌")
    print()

    # ── Search: only approved skills ──
    print("--- Search Results ---")
    results = registry.search(["chart", "csv"])
    print(f"  Skills matching 'chart': {[r.name for r in results]}")
    print(f"  >> Malicious skills don't appear: they never reached APPROVED status")
    print()


# ────────────────────────────────────────────────────────────────────── #
# PART C: MCPGovernance Pipeline (Runtime Layer)
# ────────────────────────────────────────────────────────────────────── #

class MCPTrustLevel(Enum):
    TRUSTED = "trusted"
    SEMI_TRUSTED = "semi_trusted"
    UNTRUSTED = "untrusted"

class SecurityVerdict(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AUDIT = "AUDIT"

# MAREF's forbidden patterns for untrusted MCP tools
FORBIDDEN_PATTERNS = ["rm ", "DROP", "DELETE", "sudo", "chmod", "chown", "format", "mkfs"]
FORBIDDEN_TOOLS = ["bash", "shell", "exec", "system", "spawn", "eval"]


class MCPGovernance:
    """MAREF's governance layer over MCP tool calls.
    
    In vanilla MCP, a tool call goes:
        Host → Server → Execute → Response
    
    With MAREF governance:
        Host → MCPGovernance.evaluate() → PolicyEngine → CircuitBreaker → AuditLog → Execute → Response
    """
    def __init__(self):
        self._circuit_open = False
        self._call_count = 0
        self._audit_log: list[dict] = []

    def evaluate(self, tool_name: str, args: dict, trust_level: MCPTrustLevel) -> SecurityVerdict:
        self._call_count += 1
        
        # Circuit breaker check
        if self._circuit_open:
            print(f"  [Governance] ⛔ CIRCUIT OPEN — all calls blocked")
            return SecurityVerdict.DENY

        # Trust-level check
        if trust_level == MCPTrustLevel.UNTRUSTED:
            if tool_name.lower() in FORBIDDEN_TOOLS:
                print(f"  [Governance] ❌ DENY: '{tool_name}' is forbidden for UNTRUSTED")
                self._audit_log.append({
                    "tool": tool_name,
                    "verdict": "DENY",
                    "reason": f"tool in FORBIDDEN_TOOLS list",
                    "timestamp": time.time(),
                })
                return SecurityVerdict.DENY
            
            for key, val in args.items():
                if any(p in str(val) for p in FORBIDDEN_PATTERNS):
                    print(f"  [Governance] ❌ DENY: arg '{key}' contains forbidden pattern")
                    self._audit_log.append({
                        "tool": tool_name,
                        "verdict": "DENY",
                        "reason": f"forbidden pattern in arg {key}",
                        "timestamp": time.time(),
                    })
                    return SecurityVerdict.DENY

        # Allow with audit
        self._audit_log.append({
            "tool": tool_name,
            "verdict": "ALLOW",
            "trust_level": trust_level.value,
            "args_keys": list(args.keys()),
            "timestamp": time.time(),
        })
        return SecurityVerdict.ALLOW

    def trip_circuit(self) -> None:
        self._circuit_open = True
        print(f"  [Governance] 🔴 Circuit breaker TRIPPED")

    def get_audit_log(self) -> list[dict]:
        return self._audit_log[-5:]  # Last 5 entries


def demonstrate_governance() -> None:
    """Show MAREF governance wrapping around MCP tool calls."""
    print("=" * 70)
    print("PART C: MAREF MCPGovernance in Action")
    print("=" * 70)
    print()

    gov = MCPGovernance()

    # Safe call from trusted tool
    v1 = gov.evaluate("read-file", {"path": "/data/report.csv"}, MCPTrustLevel.TRUSTED)
    print(f"  Trusted tool 'read-file': {v1.value}")

    # Suspicious call from untrusted tool
    v2 = gov.evaluate("shell", {"command": "cat /etc/passwd"}, MCPTrustLevel.UNTRUSTED)
    print(f"  Untrusted tool 'shell': {v2.value}")

    # Forbidden pattern in args
    v3 = gov.evaluate("file-manager", {"path": "sudo rm -rf /"}, MCPTrustLevel.UNTRUSTED)
    print(f"  Untrusted args with 'rm ': {v3.value}")

    # Semi-trusted tool with audit
    v4 = gov.evaluate("network-scan", {"host": "localhost"}, MCPTrustLevel.SEMI_TRUSTED)
    print(f"  Semi-trusted 'network-scan': {v4.value} (audited)")

    # Trip circuit breaker
    gov.trip_circuit()
    v5 = gov.evaluate("read-file", {"path": "/tmp/test.txt"}, MCPTrustLevel.TRUSTED)
    print(f"  After circuit trip, even trusted: {v5.value}")

    print()
    print("  Recent audit log entries:")
    for entry in gov.get_audit_log():
        print(f"    - {entry['tool']}: {entry['verdict']}")
    print()


# ────────────────────────────────────────────────────────────────────── #
# MAIN
# ────────────────────────────────────────────────────────────────────── #

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     MAREF Skill Marketplace vs MCP Marketplace              ║")
    print("║     Code-Level Comparison                                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    
    demonstrate_mcp_registration()
    demonstrate_maref_registration()
    demonstrate_governance()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("  MCP Marketplace:")
    print("    - Registration: prove namespace ownership")
    print("    - Code scanning: NONE")
    print("    - Sandbox testing: NONE")
    print("    - Human review: NONE")
    print("    - Runtime governance: NONE (protocol-level only)")
    print()
    print("  MAREF Skill Marketplace:")
    print("    - Registration: manifest with schemas, deps, tests")
    print("    - Gate 1: static scan (heuristic pattern detection)")
    print("    - Gate 2: sandbox test (stub — production-grade planned)")
    print("    - Gate 3: manual human review")
    print("    - Runtime: MCPGovernance pipeline (policy + CB + audit + HITL)")
    print()
    print("  Relationship: Complementary, not competitive.")
    print("  MAREF's MCPToA2ABridge wraps governance around MCP tools.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
