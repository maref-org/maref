"""
maref.sentinel.drift — 能力漂移检测

对比 SignedAgentCard 声明能力与 ESF/NE 实际观测行为,
检测 Agent 是否超出声明范围 (如声明 network_read 但实际 execve bash)。

任何漂移产出 CapabilityDriftReport,写入 UnifiedAuditStore 并触发
ThreatGovernanceBridge。CRITICAL 漂移 (如未声明 ptrace/setuid) 自动
触发 QuarantineProtocol。
"""

from __future__ import annotations

from maref.sentinel.drift.capability_drift_detector import (
    CapabilityDriftDetector,
    CapabilityDriftReport,
    DriftItem,
    DriftSeverity,
    DriftType,
)

__all__: list[str] = [
    "CapabilityDriftDetector",
    "CapabilityDriftReport",
    "DriftItem",
    "DriftSeverity",
    "DriftType",
]

__version__ = "0.37.0-m2.2"
