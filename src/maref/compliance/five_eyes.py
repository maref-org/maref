"""
Five Eyes Compliance — 五眼联盟安全指南映射

将 CISA/Five Eyes Agentic AI 安全指南映射到 MAREF 安全控制项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FiveEyesStandard(str, Enum):
    AGENT_IDENTITY = "agent_identity"
    TRUST_ESCALATION = "trust_escalation"
    CROSS_AGENT_POISONING = "cross_agent_poisoning"
    EMERGENT_BEHAVIOR = "emergent_behavior"
    AUDIT_LOGGING = "audit_logging"
    HUMAN_OVERSIGHT = "human_oversight"
    AGENTIC_AI_SECURITY = "agentic_ai_security"


@dataclass
class FiveEyesControl:
    control_id: str
    name: str
    description: str
    standard: FiveEyesStandard
    implementation_guide: str
    maref_module: str
    status: str = "implemented"


FIVE_EYES_CONTROLS: list[FiveEyesControl] = [
    FiveEyesControl(
        control_id="AI-1",
        name="Agent Identity Verification",
        description="All agents must have verifiable identity credentials",
        standard=FiveEyesStandard.AGENT_IDENTITY,
        implementation_guide="Use ATPKeyPair + ATPCredential for agent identity. Verify via ATPIdentityVerifier.",
        maref_module="agent_identity",
    ),
    FiveEyesControl(
        control_id="AI-2",
        name="Strong Authentication",
        description="Agent-to-agent communication requires cryptographic authentication",
        standard=FiveEyesStandard.AGENT_IDENTITY,
        implementation_guide="Implement ATP handshake (initiate_handshake, complete_handshake) with HMAC signing.",
        maref_module="agent_identity",
    ),
    FiveEyesControl(
        control_id="AI-3",
        name="Credential Lifecycle Management",
        description="Agent credentials must support rotation and revocation",
        standard=FiveEyesStandard.AGENT_IDENTITY,
        implementation_guide="Use DIDRegistry for credential management. Support key rotation via ATPKeyPair expiry.",
        maref_module="agent_identity",
    ),
    FiveEyesControl(
        control_id="TE-1",
        name="Delegation Chain Depth Limit",
        description="Trust escalation attacks prevented by limiting delegation chain depth",
        standard=FiveEyesStandard.TRUST_ESCALATION,
        implementation_guide="Enforce max_depth=5 in DelegationChain.validate(). Rank-based capability propagation.",
        maref_module="trust_chain",
    ),
    FiveEyesControl(
        control_id="TE-2",
        name="Capability Hierarchy Enforcement",
        description="Delegated capabilities must not exceed delegator's own capabilities",
        standard=FiveEyesStandard.TRUST_ESCALATION,
        implementation_guide="Implement rank-based check in _can_delegate: ADMIN>DELEGATE>EXECUTE>WRITE>READ.",
        maref_module="trust_chain",
    ),
    FiveEyesControl(
        control_id="TE-3",
        name="Chain Hash Integrity",
        description="Delegation chain must be tamper-proof using chain hashes",
        standard=FiveEyesStandard.TRUST_ESCALATION,
        implementation_guide="Use get_chain_hash() SHA256 + expected_chain_hash validation in MCPSecurityGate.",
        maref_module="trust_chain",
    ),
    FiveEyesControl(
        control_id="CAP-1",
        name="Shared State Pollution Detection",
        description="Cross-agent state poisoning must be detected and quarantined",
        standard=FiveEyesStandard.CROSS_AGENT_POISONING,
        implementation_guide="SharedStateMonitor tracks mutation rates and quarantines anomalous agents.",
        maref_module="state_monitor",
    ),
    FiveEyesControl(
        control_id="CAP-2",
        name="Message Security Scanning",
        description="Prompt injection in agent messages must be detected and blocked",
        standard=FiveEyesStandard.CROSS_AGENT_POISONING,
        implementation_guide="MessageSecurityScanner scores messages 0-100. Block high-risk injections. Log suspicious content.",
        maref_module="message_security",
    ),
    FiveEyesControl(
        control_id="EB-1",
        name="Behavior Baseline Modeling",
        description="Agent normal behavior must be baselined for anomaly detection",
        standard=FiveEyesStandard.EMERGENT_BEHAVIOR,
        implementation_guide="BehaviorMonitor builds baseline over initial samples. 3-sigma threshold for anomaly detection.",
        maref_module="behavior_monitor",
    ),
    FiveEyesControl(
        control_id="EB-2",
        name="Emergent Behavior Detection",
        description="Multi-agent emergent/shadow behavior must be detected",
        standard=FiveEyesStandard.EMERGENT_BEHAVIOR,
        implementation_guide="BehaviorMonitor records emergent patterns from multi-agent interaction history.",
        maref_module="behavior_monitor",
    ),
    FiveEyesControl(
        control_id="AL-1",
        name="Immutable Audit Trail",
        description="All security decisions must be recorded in immutable audit log",
        standard=FiveEyesStandard.AUDIT_LOGGING,
        implementation_guide="AuditLogger with frozen AuditEntry dataclass. Append-only JSONL format.",
        maref_module="governance_audit",
    ),
    FiveEyesControl(
        control_id="AL-2",
        name="Audit Log Export",
        description="Audit logs must be exportable in standard formats",
        standard=FiveEyesStandard.AUDIT_LOGGING,
        implementation_guide="Support syslog (RFC 5424) and JSON export with time-range filtering.",
        maref_module="governance_audit",
    ),
    FiveEyesControl(
        control_id="HO-1",
        name="Human-in-the-Loop",
        description="High-risk agent actions require human approval",
        standard=FiveEyesStandard.HUMAN_OVERSIGHT,
        implementation_guide="Use HITLRouter for approval workflows. CircuitBreaker for blocking unsafe actions.",
        maref_module="hitl",
    ),
]


class FiveEyesMapper:
    def __init__(self) -> None:
        self._controls_by_standard: dict[FiveEyesStandard, list[FiveEyesControl]] = {}
        self._controls_by_module: dict[str, list[FiveEyesControl]] = {}
        for c in FIVE_EYES_CONTROLS:
            self._controls_by_standard.setdefault(c.standard, []).append(c)
            self._controls_by_module.setdefault(c.maref_module, []).append(c)

    def get_controls(self, standard: FiveEyesStandard) -> list[FiveEyesControl]:
        return list(self._controls_by_standard.get(standard, []))

    def get_controls_by_maref_module(self, module_name: str) -> list[FiveEyesControl]:
        return list(self._controls_by_module.get(module_name, []))

    def generate_compliance_report(self) -> dict[str, Any]:
        total = len(FIVE_EYES_CONTROLS)
        implemented = sum(1 for c in FIVE_EYES_CONTROLS if c.status == "implemented")
        return {
            "overall_compliance": round(implemented / total * 100, 1) if total > 0 else 0.0,
            "standards": [
                {
                    "standard_id": s.value,
                    "controls": [c.control_id for c in self.get_controls(s)],
                    "compliance_rate": round(
                        sum(1 for c in self.get_controls(s) if c.status == "implemented") / len(self.get_controls(s)) * 100, 1
                    ),
                }
                for s in FiveEyesStandard
                if self.get_controls(s)
            ],
        }
