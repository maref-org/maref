"""治理轨迹 — Agent-as-a-Judge 的数据来源（方案 C M1）。

在执行链路上记录 ``TraceStep``，作为法官仲裁的输入。轨迹可复用现有
审计链（audit_bus.py）作为来源，也可由调用方直接构造。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class TraceStep:
    """单步执行轨迹。"""

    agent_id: str
    action: str
    decision: str
    context_hash: str = ""
    ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "action": self.action,
            "decision": self.decision,
            "context_hash": self.context_hash,
            "ts": self.ts,
            "metadata": dict(self.metadata),
        }


@dataclass
class Trace:
    """一段完整执行轨迹，由多个 TraceStep 组成。"""

    trace_id: str
    agent_id: str
    steps: list[TraceStep] = field(default_factory=list)

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    @property
    def size(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "steps": [s.to_dict() for s in self.steps],
        }


class VerdictDecision(str, Enum):
    """法官裁决结论。"""

    PASS = "pass"
    FLAG = "flag"
    BLOCK = "block"


@dataclass
class Verdict:
    """法官对某条轨迹的裁决结果。"""

    decision: VerdictDecision
    reasoning: str
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    judge_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasoning": self.reasoning,
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "judge_name": self.judge_name,
        }

    @property
    def approved(self) -> bool:
        """将裁决映射为共识表决的布尔值。"""
        return self.decision == VerdictDecision.PASS
