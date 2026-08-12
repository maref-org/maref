"""Destructive Operation Gate — default-on human confirmation for destructive actions.

Every destructive operation (delete, drop, rm, format, mass-update, etc.)
requires explicit human confirmation BEFORE execution. The gate is
DEFAULT-ENABLED — no configuration is needed to activate it.

Each gate decision (BLOCK / ALLOW) produces an Ed25519-signed audit entry
that any third party (including regulators) can independently verify.

Design:
- Pattern-based: matches operation names and arguments against known
  destructive patterns (``DESTRUCTIVE_PATTERNS``).
- Heuristic scoring: assigns a severity score (0.0–1.0) to each operation.
- HITL integration: operations above ``hitl_threshold`` require an explicit
  human approval call before they can proceed.
- Ed25519 evidence: every block/allow decision is signed and logged.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateVerdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HITL_REQUIRED = "HITL_REQUIRED"


# Destructive patterns — matched case-insensitively against operation
# names and stringified arguments. These fire the gate by default.
DESTRUCTIVE_PATTERNS: list[str] = [
    # File system destruction
    "rm ",
    "rm -rf",
    "rmdir",
    "unlink",
    # Database destruction
    "drop ",
    "drop table",
    "drop database",
    "delete ",
    "delete from",
    "truncate",
    # Storage destruction
    "format",
    "mkfs",
    "fdisk",
    "dd ",
    # Permission escalation
    "chmod 0",
    "chmod 777",
    "chown",
    # Bulk mutation
    "update ",
    "update set",
    # Infrastructure destruction
    "terraform destroy",
    "kubectl delete",
    "aws s3 rb",
    "gsutil rm",
    # Resource control
    "sudo ",
    "su ",
    # Agent self-modification
    "uninstall",
    "remove --purge",
    # Federation-level destructive
    "expel",
    "decommission",
    "secede",
]

DESTRUCTIVE_TOOL_NAMES: list[str] = [
    "shell",
    "bash",
    "exec",
    "system",
    "spawn",
    "delete_file",
    "remove_file",
    "write_file",
    "execute_sql",
    "run_query",
    "deploy",
    "destroy",
    "terminate",
    "batch_update",
    "bulk_delete",
]

# Operations that get HITL_REQUIRED automatically
HIGH_RISK_TOOLS: list[str] = [
    "shell",
    "bash",
    "exec",
    "system",
    "terraform",
    "kubectl",
]


@dataclass
class GateDecision:
    """A single gate decision with verifiable evidence.

    Attributes:
        decision_id: Unique identifier for this decision.
        operation: The operation being gated.
        tool_name: The tool/function name.
        args: The arguments to the operation.
        verdict: ALLOW, BLOCK, or HITL_REQUIRED.
        severity: Severity score (0.0–1.0).
        reason: Human-readable reason for the verdict.
        agent_id: The agent that attempted the operation.
        timestamp: When the decision was made.
        hitl_approved: Whether HITL approval was granted (None if not required).
        signature: Ed25519 hex signature of the decision evidence.
        signer_fingerprint: Fingerprint of the signing key.
    """

    decision_id: str = field(default_factory=lambda: f"gate-{uuid.uuid4().hex[:12]}")
    operation: str = ""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    verdict: GateVerdict = GateVerdict.ALLOW
    severity: float = 0.0
    reason: str = ""
    agent_id: str = ""
    timestamp: float = field(default_factory=time.time)
    hitl_approved: bool | None = None
    signature: str = ""
    signer_fingerprint: str = ""

    def evidence_message(self) -> bytes:
        """Canonical evidence message for Ed25519 signing."""
        return json.dumps(
            {
                "decision_id": self.decision_id,
                "operation": self.operation,
                "tool_name": self.tool_name,
                "verdict": self.verdict.value,
                "severity": self.severity,
                "reason": self.reason,
                "agent_id": self.agent_id,
                "timestamp": self.timestamp,
                "hitl_approved": self.hitl_approved,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def verify_evidence(self, public_key_pem: str) -> bool:
        """Verify the Ed25519 signature on this decision.

        Args:
            public_key_pem: PEM-encoded Ed25519 public key.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self.signature or self.signature in ("unsigned", "sign_error"):
            return False
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        try:
            return Ed25519KeyPair.verify(
                public_key_pem,
                bytes.fromhex(self.signature),
                self.evidence_message(),
            )
        except (ValueError, Exception):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "operation": self.operation,
            "tool_name": self.tool_name,
            "args_preview": {k: str(v)[:100] for k, v in self.args.items()},
            "verdict": self.verdict.value,
            "severity": self.severity,
            "reason": self.reason,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "hitl_approved": self.hitl_approved,
            "signature": self.signature,
            "signer_fingerprint": self.signer_fingerprint,
        }


class DestructiveOperationGate:
    """Default-on gate that blocks destructive operations unless confirmed.

    The gate is active by default (``enabled=True``). Every operation is
    scored against destructive patterns; if severity exceeds
    ``hitl_threshold``, the operation is BLOCK'd or HITL_REQUIRED'd.

    All decisions are Ed25519-signed when a signer is configured.
    """

    def __init__(
        self,
        enabled: bool = True,
        hitl_threshold: float = 0.5,
        block_above: float = 0.8,
        patterns: list[str] | None = None,
        tool_names: list[str] | None = None,
        signer: Any = None,
        audit_logger: Any = None,
    ) -> None:
        self._enabled = enabled
        self._hitl_threshold = hitl_threshold
        self._block_above = block_above
        self._patterns = patterns or list(DESTRUCTIVE_PATTERNS)
        self._tool_names = tool_names or list(DESTRUCTIVE_TOOL_NAMES)
        self._signer = signer
        self._audit_logger = audit_logger
        self._decisions: list[GateDecision] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def evaluate(
        self,
        operation: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> GateDecision:
        """Evaluate an operation against the destructive gate.

        Args:
            operation: Description of the operation (e.g. "delete_file").
            tool_name: The tool/function being called.
            args: Arguments to the operation.
            agent_id: ID of the agent attempting the operation.

        Returns:
            A :class:`GateDecision` with verdict and evidence.
        """
        args = args or {}
        args_str = json.dumps(args, sort_keys=True).lower()
        op_lower = operation.lower()
        tool_lower = tool_name.lower()

        # Calculate severity based on pattern matches
        severity = 0.0
        matched_patterns: list[str] = []

        # Check tool name against destructive tool list
        if any(dt in tool_lower for dt in self._tool_names):
            severity = max(severity, 0.5)

        # Check tool name against high-risk list (auto BLOCK)
        if any(hr in tool_lower for hr in HIGH_RISK_TOOLS):
            severity = max(severity, 0.9)
            matched_patterns.append("high_risk_tool")

        # Check operation name against destructive patterns
        for pattern in self._patterns:
            if pattern.lower() in op_lower:
                matched_patterns.append(pattern)
                severity = max(severity, 0.7)
            elif pattern.lower() in args_str:
                matched_patterns.append(f"arg:{pattern}")
                severity = max(severity, 0.6)

        # Check for dangerous argument patterns
        if severity < 0.5:
            for key, val in args.items():
                key_lower = key.lower()
                val_str = str(val).lower()
                if any(dp in key_lower for dp in ("password", "secret", "key", "token")):
                    severity = max(severity, 0.3)
                if "path" in key_lower and any(
                    dp in val_str for dp in ("/etc", "/var", "/usr", "..")
                ):
                    severity = max(severity, 0.5)

        # Determine verdict
        verdict = GateVerdict.ALLOW
        reason = "Operation allowed — below gate thresholds"

        if not self._enabled:
            verdict = GateVerdict.ALLOW
            reason = "Gate is disabled"

        elif severity >= self._block_above:
            verdict = GateVerdict.BLOCK
            reason = f"Destructive pattern detected: {', '.join(matched_patterns[:3])}"

        elif severity >= self._hitl_threshold:
            verdict = GateVerdict.HITL_REQUIRED
            reason = f"Human confirmation required (severity={severity:.2f})"

        decision = GateDecision(
            operation=operation,
            tool_name=tool_name,
            args=args,
            verdict=verdict,
            severity=round(severity, 3),
            reason=reason,
            agent_id=agent_id,
        )

        # Sign the decision if a signer is configured
        if self._signer is not None:
            try:
                sig_bytes = self._signer.sign(decision.evidence_message())
                decision.signature = sig_bytes.hex()
                decision.signer_fingerprint = self._signer.fingerprint
            except Exception:
                decision.signature = "sign_error"
        else:
            decision.signature = "unsigned"

        self._decisions.append(decision)

        # Audit log
        self._log_audit(decision)

        return decision

    def confirm_hitl(
        self,
        decision: GateDecision,
        approved: bool,
        approver_id: str = "",
    ) -> GateDecision:
        """Record a HITL confirmation for a previous decision.

        Updates the decision's ``hitl_approved`` field and re-signs
        the evidence message.
        """
        if decision.verdict != GateVerdict.HITL_REQUIRED:
            return decision

        decision.hitl_approved = approved
        decision.verdict = GateVerdict.ALLOW if approved else GateVerdict.BLOCK
        decision.reason = (
            f"Human {approver_id} approved" if approved else f"Human {approver_id} denied"
        )
        decision.timestamp = time.time()

        # Re-sign
        if self._signer is not None:
            try:
                sig_bytes = self._signer.sign(decision.evidence_message())
                decision.signature = sig_bytes.hex()
            except Exception:
                decision.signature = "sign_error"

        self._log_audit(decision)
        return decision

    def _log_audit(self, decision: GateDecision) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log(
                event_type="destructive_gate.evaluate",
                actor=f"gate:{decision.agent_id}",
                detail=decision.to_dict(),
            )
        except Exception:
            pass

    def recent_decisions(
        self,
        count: int = 10,
        verdict: GateVerdict | None = None,
    ) -> list[GateDecision]:
        """Return recent decisions, optionally filtered by verdict."""
        filtered = self._decisions
        if verdict is not None:
            filtered = [d for d in filtered if d.verdict == verdict]
        return filtered[-count:]

    def summary(self) -> dict[str, Any]:
        """Return a summary of gate activity."""
        total = len(self._decisions)
        blocked = sum(1 for d in self._decisions if d.verdict == GateVerdict.BLOCK)
        hitl = sum(1 for d in self._decisions if d.verdict == GateVerdict.HITL_REQUIRED)
        allowed = sum(1 for d in self._decisions if d.verdict == GateVerdict.ALLOW)
        return {
            "enabled": self._enabled,
            "hitl_threshold": self._hitl_threshold,
            "block_above": self._block_above,
            "total_decisions": total,
            "blocked": blocked,
            "hitl_required": hitl,
            "allowed": allowed,
            "signer_configured": self._signer is not None,
        }


__all__ = [
    "DESTRUCTIVE_PATTERNS",
    "DESTRUCTIVE_TOOL_NAMES",
    "DestructiveOperationGate",
    "GateDecision",
    "GateVerdict",
]
