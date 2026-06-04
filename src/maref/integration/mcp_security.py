from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MCPTrustLevel(str, Enum):
    TRUSTED = "trusted"
    SEMI_TRUSTED = "semi_trusted"
    UNTRUSTED = "untrusted"


class SecurityVerdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AUDIT = "AUDIT"


FORBIDDEN_UNTRUSTED_PATTERNS = [
    "rm ",
    "DROP",
    "DELETE",
    "sudo",
    "chmod",
    "chown",
    "format",
    "mkfs",
]

FORBIDDEN_UNTRUSTED_TOOLS = [
    "bash",
    "shell",
    "exec",
    "system",
    "spawn",
    "eval",
]


@dataclass
class AuditLogEntry:
    timestamp: datetime
    agent_id: str
    tool_name: str
    trust_level: str
    verdict: str
    args_hash: str
    chain_id: str | None = None
    delegation_depth: int = 0
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimiter:
    max_requests: int = 100
    window_seconds: int = 60
    _requests: deque[float] = field(default_factory=deque, repr=False)

    def check_rate(self) -> bool:
        now = time.time()
        # Remove old requests outside the window
        while self._requests and self._requests[0] < now - self.window_seconds:
            self._requests.popleft()

        if len(self._requests) >= self.max_requests:
            return False

        self._requests.append(now)
        return True

    def get_current_rate(self) -> int:
        now = time.time()
        while self._requests and self._requests[0] < now - self.window_seconds:
            self._requests.popleft()
        return len(self._requests)


@dataclass
class ZeroTrustContext:
    agent_id: str = ""
    chain_id: str | None = None
    delegation_depth: int = 0
    max_delegation_depth: int = 5
    session_id: str = ""
    request_id: str = ""


@dataclass
class MCPSecurityGate:
    allow_untrusted_shell: bool = False
    blocked_patterns: list[str] = field(default_factory=lambda: list(FORBIDDEN_UNTRUSTED_PATTERNS))
    blocked_tools: list[str] = field(default_factory=lambda: list(FORBIDDEN_UNTRUSTED_TOOLS))
    enable_rate_limiting: bool = True
    enable_audit_logging: bool = True
    enable_delegation_check: bool = True
    max_delegation_depth: int = 5
    rate_limiter: RateLimiter = field(default_factory=lambda: RateLimiter())
    _audit_log: list[AuditLogEntry] = field(default_factory=list, repr=False)

    def check(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any] | None = None,
        context: ZeroTrustContext | None = None,
    ) -> str:
        context = context or ZeroTrustContext()
        args = args or {}

        # Check rate limiting
        if self.enable_rate_limiting and not self.rate_limiter.check_rate():
            self._log_audit(tool_name, trust_level, "DENY", args, context, risk_score=1.0)
            return SecurityVerdict.DENY

        # Check delegation depth
        if self.enable_delegation_check:
            if context.delegation_depth > self.max_delegation_depth:
                self._log_audit(tool_name, trust_level, "DENY", args, context, risk_score=1.0)
                return SecurityVerdict.DENY

        # Base trust level check
        verdict = self._check_trust_level(tool_name, trust_level, args)

        # Calculate risk score
        risk_score = self._calculate_risk(tool_name, trust_level, args, context)

        # Log audit
        if self.enable_audit_logging:
            self._log_audit(tool_name, trust_level, verdict, args, context, risk_score)

        return verdict

    def _check_trust_level(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any],
    ) -> str:
        if trust_level == MCPTrustLevel.TRUSTED:
            return SecurityVerdict.ALLOW

        args_str = str(args).lower()

        if trust_level == MCPTrustLevel.UNTRUSTED:
            if not self.allow_untrusted_shell:
                lowered = tool_name.lower()
                for blocked in self.blocked_tools:
                    if blocked in lowered:
                        return SecurityVerdict.DENY

                for pattern in self.blocked_patterns:
                    if pattern.lower() in args_str:
                        return SecurityVerdict.DENY

            return SecurityVerdict.AUDIT

        if trust_level == MCPTrustLevel.SEMI_TRUSTED:
            for blocked in self.blocked_tools:
                if blocked in tool_name.lower():
                    return SecurityVerdict.DENY
            return SecurityVerdict.AUDIT

        return SecurityVerdict.DENY

    def _calculate_risk(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any],
        context: ZeroTrustContext,
    ) -> float:
        risk = 0.0

        # Trust level risk
        if trust_level == MCPTrustLevel.UNTRUSTED:
            risk += 0.3
        elif trust_level == MCPTrustLevel.SEMI_TRUSTED:
            risk += 0.1

        # Delegation depth risk
        if context.delegation_depth > 2:
            risk += 0.2
        if context.delegation_depth > 4:
            risk += 0.3

        # Tool risk
        lowered = tool_name.lower()
        for blocked in self.blocked_tools:
            if blocked in lowered:
                risk += 0.2
                break

        # Args risk
        args_str = str(args).lower()
        for pattern in self.blocked_patterns:
            if pattern.lower() in args_str:
                risk += 0.2
                break

        return min(risk, 1.0)

    def _log_audit(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        verdict: str,
        args: dict[str, Any],
        context: ZeroTrustContext,
        risk_score: float,
    ) -> None:
        import hashlib
        args_hash = hashlib.sha256(str(args).encode()).hexdigest()[:16]

        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id=context.agent_id,
            tool_name=tool_name,
            trust_level=trust_level.value,
            verdict=verdict,
            args_hash=args_hash,
            chain_id=context.chain_id,
            delegation_depth=context.delegation_depth,
            risk_score=risk_score,
        )
        self._audit_log.append(entry)

    def get_audit_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def get_audit_summary(self) -> dict[str, Any]:
        total = len(self._audit_log)
        allowed = sum(1 for e in self._audit_log if e.verdict == "ALLOW")
        denied = sum(1 for e in self._audit_log if e.verdict == "DENY")
        audited = sum(1 for e in self._audit_log if e.verdict == "AUDIT")

        return {
            "total_requests": total,
            "allowed": allowed,
            "denied": denied,
            "audited": audited,
            "current_rate": self.rate_limiter.get_current_rate(),
            "max_rate": self.rate_limiter.max_requests,
        }

    def export_audit_log(self, format: str = "json") -> str:
        import json
        if format == "json":
            return json.dumps([{
                "timestamp": e.timestamp.isoformat(),
                "agent_id": e.agent_id,
                "tool_name": e.tool_name,
                "trust_level": e.trust_level,
                "verdict": e.verdict,
                "args_hash": e.args_hash,
                "chain_id": e.chain_id,
                "delegation_depth": e.delegation_depth,
                "risk_score": e.risk_score,
            } for e in self._audit_log], indent=2)
        elif format == "syslog":
            lines = []
            for e in self._audit_log:
                lines.append(
                    f"{e.timestamp.isoformat()} MAREF-SECURITY "
                    f"agent={e.agent_id} tool={e.tool_name} "
                    f"trust={e.trust_level} verdict={e.verdict} "
                    f"risk={e.risk_score:.2f} depth={e.delegation_depth}"
                )
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")


DEFAULT_HMAC_SECRET_KEY = os.environb.get(
    b"MAREF_HMAC_SECRET_KEY",
    b"maref-mcp-governance-v0.27.0",
)
"""Default HMAC secret key for audit log signing.

In production, always set MAREF_HMAC_SECRET_KEY environment variable.
The default value is for development/testing only and MUST NOT be used in production.
"""


def sign_audit_entry(entry: AuditLogEntry, secret_key: bytes = DEFAULT_HMAC_SECRET_KEY) -> str:
    """Create HMAC-SHA256 signature for an audit log entry.

    The signature covers all immutable fields of the entry, providing
    tamper-evident audit logging. Store alongside the entry for verification.
    """
    payload = json.dumps({
        "timestamp": entry.timestamp.isoformat(),
        "agent_id": entry.agent_id,
        "tool_name": entry.tool_name,
        "trust_level": entry.trust_level,
        "verdict": entry.verdict,
        "args_hash": entry.args_hash,
        "chain_id": entry.chain_id,
        "delegation_depth": entry.delegation_depth,
        "risk_score": entry.risk_score,
    }, sort_keys=True)
    return hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()


def verify_audit_signature(
    entry: AuditLogEntry, signature: str, secret_key: bytes = DEFAULT_HMAC_SECRET_KEY
) -> bool:
    """Verify HMAC-SHA256 signature of an audit log entry.

    Returns True if the signature matches, False if the entry has been tampered with.
    """
    expected = sign_audit_entry(entry, secret_key)
    return hmac.compare_digest(expected, signature)
