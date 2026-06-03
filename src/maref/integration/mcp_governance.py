"""
MCP Governance Layer — bridges MCP tool calls to MAREF governance pipeline.

Every MCP tool call flows through:
  1. MCPPolicyEngine — evaluates tool name + args against configurable rules
  2. CircuitBreaker — fault tolerance (depth, oscillation, failure count)
  3. HMAC-SHA256 Audit Log — immutable audit trail
  4. HITL Router — human-in-the-loop for high-risk operations

Architecture:
  MCPClient.call_tool()
    → MCPGovernance.evaluate()
      → MCPPolicyEngine.evaluate()  → ALLOW | DENY | ASK_USER
      → CircuitBreaker.check()
      → AuditLog.sign()  (HMAC-SHA256)
      → HITLRouter.route()  (if ASK_USER)
    → If ALLOW: transport.send_tool_call()
    → Return result
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml

from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.hitl import HITLRouter, HITLStatus, HITLTier
from maref.integration.mcp_security import (
    AuditLogEntry,
    MCPSecurityGate,
    MCPTrustLevel,
    SecurityVerdict,
    ZeroTrustContext,
)

HMAC_SECRET_KEY = os.environb.get(
    b"MAREF_HMAC_SECRET_KEY",
    b"maref-mcp-governance-v0.27.0",
)
"""HMAC secret key for audit log signing.

In production, always set MAREF_HMAC_SECRET_KEY environment variable.
The default value is for development/testing only and MUST NOT be used in production.
"""


@dataclass
class MCPToolCallStats:
    tool_name: str
    call_count: int = 0
    error_count: int = 0
    total_latency: float = 0.0
    max_latency: float = 0.0

    @property
    def avg_latency(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_latency / self.call_count

    @property
    def error_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.error_count / self.call_count


class MCPCircuitBreakerMonitor:
    """Per-tool circuit breaker metrics monitor.

    Tracks call volume, error rates, and latency per tool.
    Provides threshold-based querying for circuit breaker decisions.
    """

    def __init__(
        self,
        max_error_rate: float = 0.3,
        max_avg_latency_ms: float = 30000.0,
        min_calls_for_metrics: int = 3,
    ) -> None:
        self._max_error_rate = max_error_rate
        self._max_avg_latency_ms = max_avg_latency_ms
        self._min_calls_for_metrics = min_calls_for_metrics
        self._tool_stats: dict[str, MCPToolCallStats] = {}

    def record_call(self, tool_name: str, latency: float, success: bool) -> None:
        if tool_name not in self._tool_stats:
            self._tool_stats[tool_name] = MCPToolCallStats(tool_name=tool_name)
        stats = self._tool_stats[tool_name]
        stats.call_count += 1
        stats.total_latency += latency
        if latency > stats.max_latency:
            stats.max_latency = latency
        if not success:
            stats.error_count += 1

    def should_trip(self, tool_name: str) -> tuple[bool, str]:
        stats = self._tool_stats.get(tool_name)
        if stats is None or stats.call_count < self._min_calls_for_metrics:
            return False, ""

        if stats.error_rate > self._max_error_rate:
            return True, f"error_rate={stats.error_rate:.2f} > max={self._max_error_rate}"

        if stats.max_latency > self._max_avg_latency_ms / 1000.0:
            return (
                True,
                f"max_latency={stats.max_latency:.2f}s > max={self._max_avg_latency_ms / 1000:.2f}s",
            )

        return False, ""

    def get_tool_stats(self, tool_name: str) -> MCPToolCallStats | None:
        return self._tool_stats.get(tool_name)

    def get_all_stats(self) -> dict[str, MCPToolCallStats]:
        return dict(self._tool_stats)

    def reset_tool(self, tool_name: str) -> None:
        self._tool_stats.pop(tool_name, None)

    def reset_all(self) -> None:
        self._tool_stats.clear()


class MCPDecisionVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"


@dataclass
class MCPPolicyContext:
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    trust_level: MCPTrustLevel = MCPTrustLevel.UNTRUSTED
    agent_id: str = ""
    session_id: str = ""
    chain_id: str | None = None
    delegation_depth: int = 0
    request_id: str = ""


@dataclass
class MCPGovernanceResult:
    verdict: MCPDecisionVerdict
    reason: str = ""
    risk_score: float = 0.0
    audit_signature: str = ""
    hitl_event_id: str | None = None
    hitl_tier: HITLTier | None = None
    matched_rule: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "risk_score": self.risk_score,
            "audit_signature": self.audit_signature,
            "hitl_event_id": self.hitl_event_id,
            "hitl_tier": self.hitl_tier.value if self.hitl_tier else None,
            "matched_rule": self.matched_rule,
            "metadata": self.metadata,
        }


class MCPPolicyRule(ABC):
    """Base class for MCP policy rules. Each rule evaluates a tool call context
    and returns a verdict if it matches, or None to pass to the next rule."""

    def __init__(self, rule_id: str, description: str, priority: int = 0) -> None:
        self.rule_id = rule_id
        self.description = description
        self.priority = priority

    @abstractmethod
    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None: ...


class AllowMCPProtocolSignals(MCPPolicyRule):
    """Allow MCP protocol-level signals (list tools/resources, ping, etc.) without governance."""

    SAFE_METHODS = {
        "tools/list",
        "tools/resources",
        "resources/list",
        "resources/subscribe",
        "resources/unsubscribe",
        "prompts/list",
        "prompts/get",
        "ping",
        "completion/complete",
        "logging/setLevel",
    }

    def __init__(self) -> None:
        super().__init__(
            rule_id="mcp-rule-001",
            description="Allow MCP protocol signals without governance check",
            priority=100,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        if context.tool_name in self.SAFE_METHODS:
            return MCPGovernanceResult(
                verdict=MCPDecisionVerdict.ALLOW,
                reason=f"MCP protocol signal '{context.tool_name}' auto-allowed",
                matched_rule=self.rule_id,
                risk_score=0.0,
            )
        return None


class AllowKnownSafeMCPTools(MCPPolicyRule):
    """Allow known-safe MCP tools (read-only tools, info queries)."""

    SAFE_TOOL_PREFIXES = {
        "read",
        "list",
        "get",
        "search",
        "query",
        "lookup",
        "find",
        "status",
        "info",
        "help",
    }

    SAFE_TOOL_NAMES = {
        "read_file",
        "list_directory",
        "get_file_info",
        "search_files",
        "git_log",
        "git_status",
        "git_diff",
        "git_branch",
        "browser_screenshot",
    }

    def __init__(self) -> None:
        super().__init__(
            rule_id="mcp-rule-002",
            description="Allow known-safe tools by name prefix or exact match",
            priority=90,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        name = context.tool_name.lower()
        if name in self.SAFE_TOOL_NAMES:
            return MCPGovernanceResult(
                verdict=MCPDecisionVerdict.ALLOW,
                reason=f"Known-safe tool '{context.tool_name}' auto-allowed",
                matched_rule=self.rule_id,
                risk_score=0.1,
            )
        for prefix in self.SAFE_TOOL_PREFIXES:
            if name.startswith(prefix):
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.ALLOW,
                    reason=f"Tool '{context.tool_name}' matches safe prefix '{prefix}'",
                    matched_rule=self.rule_id,
                    risk_score=0.1,
                )
        return None


class BlockDangerousMCPTools(MCPPolicyRule):
    """Block known-dangerous MCP tools regardless of trust level."""

    DANGEROUS_TOOL_NAMES = {
        "shell",
        "bash",
        "zsh",
        "sh",
        "exec",
        "spawn",
        "system",
        "popen",
        "subprocess",
        "eval",
        "exec_command",
        "sudo",
        "su",
        "chmod",
        "chown",
        "mkfs",
        "format",
        "dd",
        "fdisk",
        "mount",
        "umount",
    }

    def __init__(self) -> None:
        super().__init__(
            rule_id="mcp-rule-003",
            description="Block known-dangerous MCP tools",
            priority=80,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        name = context.tool_name.lower()
        for dangerous in self.DANGEROUS_TOOL_NAMES:
            if dangerous in name:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.ASK_USER,
                    reason=f"Dangerous tool '{context.tool_name}' requires user confirmation",
                    matched_rule=self.rule_id,
                    risk_score=0.9,
                )
        return None


class BlockDangerousArgs(MCPPolicyRule):
    """Block dangerous argument patterns in tool calls."""

    DANGEROUS_PATTERNS = [
        "rm -rf",
        "rm -fr",
        "rm --recursive",
        "mkfs",
        "dd if=",
        "DROP TABLE",
        "DROP DATABASE",
        "DELETE FROM",
        "shutdown",
        "reboot",
        "init 0",
        "init 6",
        "chmod 777",
        "chmod -R 777",
        "sudo ",
        "> /dev/sda",
        "| bash",
        "| sh",
        "wget ",
        "curl ",
    ]

    def __init__(self) -> None:
        super().__init__(
            rule_id="mcp-rule-004",
            description="Block dangerous argument patterns in tool calls",
            priority=75,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        args_str = json.dumps(context.args).lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in args_str:
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason=f"Dangerous pattern '{pattern}' detected in arguments",
                    matched_rule=self.rule_id,
                    risk_score=1.0,
                )
        return None


class WriteToolRequiresHITL(MCPPolicyRule):
    """Tools that modify state (write, delete, push, send) require HITL."""

    MODIFY_TOOL_PREFIXES = {
        "write",
        "create",
        "delete",
        "remove",
        "update",
        "edit",
        "push",
        "commit",
        "send",
        "upload",
        "deploy",
        "publish",
        "move",
        "copy",
        "rename",
    }

    def __init__(self) -> None:
        super().__init__(
            rule_id="mcp-rule-005",
            description="Write/delete/push tools require HITL confirmation",
            priority=60,
        )

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        name = context.tool_name.lower()
        for prefix in self.MODIFY_TOOL_PREFIXES:
            if name.startswith(prefix):
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.ASK_USER,
                    reason=f"Write tool '{context.tool_name}' requires user confirmation",
                    matched_rule=self.rule_id,
                    risk_score=0.7,
                )
        return None


class TrustLevelBasedGate(MCPPolicyRule):
    """Use MCPSecurityGate for trust-level based evaluation."""

    def __init__(self, security_gate: MCPSecurityGate | None = None) -> None:
        super().__init__(
            rule_id="mcp-rule-006",
            description="Trust-level based evaluation via MCPSecurityGate",
            priority=50,
        )
        self._security_gate = security_gate or MCPSecurityGate()

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult | None:
        zt_context = ZeroTrustContext(
            agent_id=context.agent_id,
            chain_id=context.chain_id,
            delegation_depth=context.delegation_depth,
            session_id=context.session_id,
            request_id=context.request_id,
        )
        verdict = self._security_gate.check(
            tool_name=context.tool_name,
            trust_level=context.trust_level,
            args=context.args,
            context=zt_context,
        )

        if verdict == SecurityVerdict.DENY:
            return MCPGovernanceResult(
                verdict=MCPDecisionVerdict.DENY,
                reason=f"MCPSecurityGate denied: trust_level={context.trust_level.value}, tool={context.tool_name}",
                matched_rule=self.rule_id,
                risk_score=1.0,
            )

        if verdict == SecurityVerdict.AUDIT and context.trust_level != MCPTrustLevel.TRUSTED:
            return MCPGovernanceResult(
                verdict=MCPDecisionVerdict.ASK_USER,
                reason=f"MCPSecurityGate requires audit for trust_level={context.trust_level.value}",
                matched_rule=self.rule_id,
                risk_score=0.5,
            )

        return None


def sign_audit_entry(entry: AuditLogEntry, secret_key: bytes = HMAC_SECRET_KEY) -> str:
    """Create HMAC-SHA256 signature for an audit log entry."""
    payload = json.dumps(
        {
            "timestamp": entry.timestamp.isoformat(),
            "agent_id": entry.agent_id,
            "tool_name": entry.tool_name,
            "trust_level": entry.trust_level,
            "verdict": entry.verdict,
            "args_hash": entry.args_hash,
            "chain_id": entry.chain_id,
            "delegation_depth": entry.delegation_depth,
            "risk_score": entry.risk_score,
        },
        sort_keys=True,
    )
    signature = hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()
    return signature


def verify_audit_signature(
    entry: AuditLogEntry, signature: str, secret_key: bytes = HMAC_SECRET_KEY
) -> bool:
    """Verify HMAC-SHA256 signature of an audit log entry."""
    expected = sign_audit_entry(entry, secret_key)
    return hmac.compare_digest(expected, signature)


class MCPPolicyEngine:
    """MCP Policy Decision Engine.

    Evaluates tool calls against a configurable chain of policy rules.
    Rules are evaluated in priority order (highest first). The first
    rule that returns a result determines the verdict.
    """

    def __init__(self, rules: list[MCPPolicyRule] | None = None) -> None:
        self._rules = rules or [
            AllowMCPProtocolSignals(),
            AllowKnownSafeMCPTools(),
            BlockDangerousMCPTools(),
            BlockDangerousArgs(),
            WriteToolRequiresHITL(),
            TrustLevelBasedGate(),
        ]

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult:
        sorted_rules = sorted(self._rules, key=lambda r: r.priority, reverse=True)
        for rule in sorted_rules:
            result = rule.evaluate(context)
            if result is not None:
                return result
        return MCPGovernanceResult(
            verdict=MCPDecisionVerdict.ALLOW,
            reason="No rules matched — default ALLOW (semi-auto mode)",
            risk_score=0.2,
            matched_rule="default",
        )

    def add_rule(self, rule: MCPPolicyRule) -> None:
        self._rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        for i, rule in enumerate(self._rules):
            if rule.rule_id == rule_id:
                self._rules.pop(i)
                return True
        return False

    def get_rules(self) -> list[MCPPolicyRule]:
        return list(self._rules)


class MCPGovernance:
    """Full governance pipeline for MCP tool calls.

    Every tool call evaluation flows through:
    1. MCPPolicyEngine — rule-based allow/deny/ask_user
    2. CircuitBreaker — fault tolerance check
    3. HMAC-signed audit logging
    4. HITL routing — human approval for ask_user verdicts
    """

    def __init__(
        self,
        policy_engine: MCPPolicyEngine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        hitl_router: HITLRouter | None = None,
        cb_monitor: MCPCircuitBreakerMonitor | None = None,
    ) -> None:
        self._policy_engine = policy_engine or MCPPolicyEngine()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            max_depth=10,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        self._hitl_router = hitl_router or HITLRouter()
        self._cb_monitor = cb_monitor or MCPCircuitBreakerMonitor()
        self._audit_log: list[AuditLogEntry] = []
        self._decision_log: list[MCPGovernanceResult] = []
        self._secret_key = HMAC_SECRET_KEY

    @property
    def policy_engine(self) -> MCPPolicyEngine:
        return self._policy_engine

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def hitl_router(self) -> HITLRouter:
        return self._hitl_router

    @property
    def cb_monitor(self) -> MCPCircuitBreakerMonitor:
        return self._cb_monitor

    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        trust_level: MCPTrustLevel = MCPTrustLevel.UNTRUSTED,
        agent_id: str = "",
        session_id: str = "",
        chain_id: str | None = None,
        delegation_depth: int = 0,
        request_id: str = "",
        timeout_seconds: float = 0.0,
    ) -> MCPGovernanceResult:
        context = MCPPolicyContext(
            tool_name=tool_name,
            args=args or {},
            trust_level=trust_level,
            agent_id=agent_id,
            session_id=session_id,
            chain_id=chain_id,
            delegation_depth=delegation_depth,
            request_id=request_id,
        )

        # E1.2: Check CB monitor before policy evaluation
        should_trip, trip_reason = self._cb_monitor.should_trip(tool_name)
        if should_trip:
            self._circuit_breaker.record_failure()
            result = MCPGovernanceResult(
                verdict=MCPDecisionVerdict.DENY,
                reason=f"Circuit breaker monitor tripped for '{tool_name}': {trip_reason}",
                risk_score=1.0,
                matched_rule="circuit_breaker_monitor",
            )
            self._record_decision(
                result, tool_name, trust_level, agent_id, chain_id, delegation_depth, context.args
            )
            self._decision_log.append(result)
            return result

        circuit_breaker_depth = delegation_depth + 1
        if not self._circuit_breaker.check_depth(circuit_breaker_depth):
            result = MCPGovernanceResult(
                verdict=MCPDecisionVerdict.DENY,
                reason=f"Circuit breaker open at depth {circuit_breaker_depth}",
                risk_score=1.0,
                matched_rule="circuit_breaker",
            )
            self._record_decision(
                result, tool_name, trust_level, agent_id, chain_id, delegation_depth, context.args
            )
            self._decision_log.append(result)
            return result

        result = self._policy_engine.evaluate(context)
        self._record_decision(
            result, tool_name, trust_level, agent_id, chain_id, delegation_depth, context.args
        )

        if result.verdict == MCPDecisionVerdict.ASK_USER:
            hitl_event = self._hitl_router.route(
                severity="warning" if result.risk_score < 0.8 else "critical",
                anomaly_type="mcp_tool_call",
                description=result.reason,
                tool_name=tool_name,
                risk_score=result.risk_score,
                request_id=request_id,
                agent_id=agent_id,
            )
            result.hitl_event_id = hitl_event.event_id
            result.hitl_tier = hitl_event.tier

        if result.verdict == MCPDecisionVerdict.ALLOW:
            self._circuit_breaker.record_success()
        else:
            self._circuit_breaker.record_failure()

        self._decision_log.append(result)
        return result

    def _record_decision(
        self,
        result: MCPGovernanceResult,
        tool_name: str,
        trust_level: MCPTrustLevel,
        agent_id: str,
        chain_id: str | None,
        delegation_depth: int,
        args: dict[str, Any] | None = None,
    ) -> None:
        args_hash = hashlib.sha256(json.dumps(args or {}, sort_keys=True).encode()).hexdigest()[:16]

        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            agent_id=agent_id,
            tool_name=tool_name,
            trust_level=trust_level.value,
            verdict=result.verdict.value.upper(),
            args_hash=args_hash,
            chain_id=chain_id,
            delegation_depth=delegation_depth,
            risk_score=result.risk_score,
            metadata={
                "reason": result.reason,
                "matched_rule": result.matched_rule,
            },
        )
        result.audit_signature = sign_audit_entry(entry, self._secret_key)
        result.metadata["audit_signature"] = result.audit_signature
        self._audit_log.append(entry)

    def approve_tool_call(self, event_id: str, reviewer: str = "human") -> bool:
        status = self._hitl_router.approve(event_id, reviewer)
        return status == HITLStatus.APPROVED

    def reject_tool_call(self, event_id: str, reason: str = "") -> bool:
        status = self._hitl_router.reject(event_id, reason)
        return status == HITLStatus.REJECTED

    def get_audit_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def get_decision_log(self) -> list[MCPGovernanceResult]:
        return list(self._decision_log)

    def get_audit_summary(self) -> dict[str, Any]:
        total = len(self._audit_log)
        allowed = sum(1 for e in self._audit_log if e.verdict == "ALLOW")
        denied = sum(1 for e in self._audit_log if e.verdict == "DENY")
        audited = sum(1 for e in self._audit_log if e.verdict == "ASK_USER")
        cb_stats = self._circuit_breaker.get_stats()
        hitl_stats = self._hitl_router.get_stats()
        cb_monitor_all = self._cb_monitor.get_all_stats()
        return {
            "total_calls": total,
            "allowed": allowed,
            "denied": denied,
            "ask_user": audited,
            "circuit_breaker_state": cb_stats.get("state"),
            "cb_trip_count": cb_stats.get("trip_count"),
            "hitl_pending": hitl_stats.get("pending_count"),
            "cb_monitored_tools": len(cb_monitor_all),
            "cb_monitor_tool_stats": {
                name: {
                    "call_count": s.call_count,
                    "error_count": s.error_count,
                    "avg_latency": round(s.avg_latency, 3),
                    "error_rate": round(s.error_rate, 3),
                }
                for name, s in cb_monitor_all.items()
            },
        }

    def get_audit_entry(self, index: int) -> AuditLogEntry | None:
        if 0 <= index < len(self._audit_log):
            return self._audit_log[index]
        return None

    def clear_audit_log(self) -> int:
        count = len(self._audit_log)
        self._audit_log.clear()
        self._decision_log.clear()
        return count

    def verify_audit_integrity(self) -> list[dict[str, Any]]:
        violations = []
        for i, entry in enumerate(self._audit_log):
            stored_sig = None
            if i < len(self._decision_log):
                stored_sig = self._decision_log[i].metadata.get("audit_signature", "")
            if not stored_sig:
                violations.append(
                    {"index": i, "tool_name": entry.tool_name, "issue": "no_signature"}
                )
                continue
            if not verify_audit_signature(entry, stored_sig, self._secret_key):
                violations.append(
                    {"index": i, "tool_name": entry.tool_name, "issue": "signature_mismatch"}
                )
        return violations

    def export_audit_log(self, format: str = "json") -> str:
        if format == "json":
            return json.dumps(
                [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "agent_id": e.agent_id,
                        "tool_name": e.tool_name,
                        "trust_level": e.trust_level,
                        "verdict": e.verdict,
                        "args_hash": e.args_hash,
                        "chain_id": e.chain_id,
                        "delegation_depth": e.delegation_depth,
                        "risk_score": e.risk_score,
                        "metadata": e.metadata,
                    }
                    for e in self._audit_log
                ],
                indent=2,
            )
        elif format == "syslog":
            lines = []
            for e in self._audit_log:
                lines.append(
                    f"{e.timestamp.isoformat()} MAREF-MCP-GOV "
                    f"agent={e.agent_id} tool={e.tool_name} "
                    f"trust={e.trust_level} verdict={e.verdict} "
                    f"risk={e.risk_score:.2f} depth={e.delegation_depth} "
                    f"hash={e.args_hash}"
                )
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def get_hitl_events(self, status: str | None = None) -> list[dict[str, Any]]:
        events = self._hitl_router.get_all()
        if status:
            events = [e for e in events if e.status.value == status]
        return [e.to_dict() for e in events]

    def get_hitl_event(self, event_id: str) -> dict[str, Any] | None:
        for event in self._hitl_router.get_all():
            if event.event_id == event_id:
                return event.to_dict()
        return None

    def check_hitl_timeouts(self) -> list[str]:
        auto_approved = []
        for event in self._hitl_router.get_pending():
            if event.auto_approve_seconds > 0 and self._hitl_router.check_timeout(event):
                event.status = HITLStatus.AUTO_APPROVED
                auto_approved.append(event.event_id)
        return auto_approved


DEFAULT_POLICY_MAPPING_YAML = """
version: "1.0"
mappings:
  # Protocol signals → allow
  - tools: ["ping", "tools/list", "resources/list", "prompts/list", "completion/complete"]
    rule: "mcp-rule-001"
  # Safe read tools → allow
  - tools: ["read_file", "list_directory", "get_file_info", "search_files",
            "git_log", "git_status", "git_diff", "git_branch"]
    rule: "mcp-rule-002"
  # Dangerous shell tools → ask user
  - tools: ["shell", "bash", "zsh", "exec", "spawn", "exec_command", "popen"]
    rule: "mcp-rule-003"
  # Write/modify tools → ask user
  - patterns: ["write_", "create_", "delete_", "update_", "push_", "send_"]
    rule: "mcp-rule-005"
  # Default fallback → trust level gate
  - patterns: ["*"]
    rule: "mcp-rule-006"
"""


@dataclass
class MCPPolicyMapping:
    """YAML-configurable mapping from tool names/patterns to policy rules.

    Each mapping entry can specify:
    - tools: list of exact tool names
    - patterns: list of glob-style patterns (supports '*' prefix/suffix)
    - rule: rule_id to apply
    """

    mappings: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> MCPPolicyMapping:
        data = yaml.safe_load(yaml_str)
        if not data or "mappings" not in data:
            raise ValueError("Invalid policy mapping YAML: missing 'mappings' key")
        return cls(mappings=data["mappings"])

    @classmethod
    def from_yaml_file(cls, path: str) -> MCPPolicyMapping:
        with open(path) as f:
            return cls.from_yaml(f.read())

    @classmethod
    def default(cls) -> MCPPolicyMapping:
        return cls.from_yaml(DEFAULT_POLICY_MAPPING_YAML)

    def get_rule_for_tool(self, tool_name: str) -> str:
        for mapping in self.mappings:
            tools = mapping.get("tools", [])
            patterns = mapping.get("patterns", [])
            rule = mapping.get("rule", "mcp-rule-006")

            if tool_name in tools:
                return rule

            for pattern in patterns:
                if pattern == "*":
                    return rule
                if pattern.endswith("*") and tool_name.startswith(pattern[:-1]):
                    return rule
                if pattern.startswith("*") and tool_name.endswith(pattern[1:]):
                    return rule
                if pattern in tool_name:
                    return rule

        return "mcp-rule-006"

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            {"version": "1.0", "mappings": self.mappings}, default_flow_style=False
        )


class MCPMappedPolicyEngine(MCPPolicyEngine):
    """Policy engine that uses a mapping table to select which rules to apply per tool."""

    def __init__(
        self,
        mapping: MCPPolicyMapping | None = None,
        rules: list[MCPPolicyRule] | None = None,
    ) -> None:
        super().__init__(rules=rules)
        self._mapping = mapping or MCPPolicyMapping.default()
        self._rule_map: dict[str, MCPPolicyRule] = {}
        for rule in self._rules:
            self._rule_map[rule.rule_id] = rule

    @property
    def mapping(self) -> MCPPolicyMapping:
        return self._mapping

    def set_mapping(self, mapping: MCPPolicyMapping) -> None:
        self._mapping = mapping

    def evaluate(self, context: MCPPolicyContext) -> MCPGovernanceResult:
        rule_id = self._mapping.get_rule_for_tool(context.tool_name)
        rule = self._rule_map.get(rule_id)

        if rule is not None:
            result = rule.evaluate(context)
            if result is not None:
                return result

        return MCPGovernanceResult(
            verdict=MCPDecisionVerdict.ALLOW,
            reason=f"Mapped rule '{rule_id}' for '{context.tool_name}' — no match from rule, default ALLOW",
            risk_score=0.2,
            matched_rule="default",
        )
