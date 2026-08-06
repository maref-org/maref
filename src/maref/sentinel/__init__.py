"""
maref.sentinel — 运行时观测神经

三层观测架构的中间层 (观测神经):
- 上游: 平台 backend (ESF/eBPF/ETW/psutil) + Probe 套件
- 下游: ThreatGovernanceBridge (治理脑) + QuarantineProtocol (进程生命周期)

所有 ObservationEvent 必须带 HMAC-SHA256 签名,作为不可篡改的审计证据。

参见:
- ADR-006 Sentinel 三层观测架构
- ADR-007 平台观测策略矩阵
- .missions/v0.37.0-runtime-observability/validation-contract.md
"""

from __future__ import annotations

from maref.sentinel.addons import SentinelMitmAddon
from maref.sentinel.consent import (
    CONSENT_OPERATIONS,
    ConsentDecision,
    ConsentOutcome,
    JustInTimeConsent,
)
from maref.sentinel.daemon import Daemon, SentinelDaemon
from maref.sentinel.drift import (
    CapabilityDriftDetector,
    CapabilityDriftReport,
    DriftItem,
    DriftSeverity,
    DriftType,
)
from maref.sentinel.event import (
    ATTACK_TYPES,
    SEVERITY_LEVELS,
    AttackType,
    ObservationEvent,
    Severity,
    compute_event_hash,
    verify_event_hash,
)
from maref.sentinel.forensic import EvidenceBundle, ForensicSnapshot
from maref.sentinel.probes import (
    EnvProbe,
    FileProbe,
    FlowRecord,
    NetworkEgressProbe,
    Probe,
    ProbeConfig,
    ProcessProbe,
    PromptBaselineProbe,
    PromptSubmission,
    TimezoneProbe,
)
from maref.sentinel.quarantine import (
    CgroupFreezerStrategy,
    NoopStrategy,
    QuarantineProtocol,
    QuarantineReason,
    QuarantineRecord,
    QuarantineStatus,
    QuarantineStrategy,
    SandboxExecStrategy,
    SigstopStrategy,
)
from maref.sentinel.reputation import (
    AgentReputationRegistry,
    AgentState,
    ReputationChangeReason,
    ReputationRecord,
)

__all__: list[str] = [
    # Daemon
    "Daemon",
    "SentinelDaemon",
    # Event
    "ObservationEvent",
    "Severity",
    "AttackType",
    "SEVERITY_LEVELS",
    "ATTACK_TYPES",
    "compute_event_hash",
    "verify_event_hash",
    # Forensic
    "ForensicSnapshot",
    "EvidenceBundle",
    # Probes
    "Probe",
    "ProbeConfig",
    "ProcessProbe",
    "EnvProbe",
    "FileProbe",
    "TimezoneProbe",
    "NetworkEgressProbe",
    "FlowRecord",
    "PromptBaselineProbe",
    "PromptSubmission",
    # Addons
    "SentinelMitmAddon",
    # Quarantine (M1.3)
    "QuarantineProtocol",
    "QuarantineRecord",
    "QuarantineReason",
    "QuarantineStatus",
    "QuarantineStrategy",
    "NoopStrategy",
    "SigstopStrategy",
    "SandboxExecStrategy",
    "CgroupFreezerStrategy",
    # Consent (M1.3)
    "JustInTimeConsent",
    "ConsentDecision",
    "ConsentOutcome",
    "CONSENT_OPERATIONS",
    # Reputation (M1.3)
    "AgentReputationRegistry",
    "AgentState",
    "ReputationRecord",
    "ReputationChangeReason",
    # Drift (M2.2)
    "CapabilityDriftDetector",
    "CapabilityDriftReport",
    "DriftItem",
    "DriftSeverity",
    "DriftType",
]

__version__ = "0.37.0-m2.2"
