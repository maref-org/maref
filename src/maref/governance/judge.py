"""Agent-as-a-Judge 法官接口与规则实现（方案 C M1/M2）。

法官对执行轨迹（Trace）进行仲裁，输出带证据引用的裁决（Verdict）。
支持规则法官（RuleJudge，基于策略模式匹配）与可扩展的 LLM 法官
（JudgeProvider 注入点）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from maref.governance.trace import Trace, Verdict, VerdictDecision


class Judge(ABC):
    """法官抽象接口。"""

    name: str = "judge"

    @abstractmethod
    def arbitrate(self, trace: Trace, verdict_schema: dict[str, Any] | None = None) -> Verdict:
        """对轨迹进行仲裁，返回带证据引用的裁决。"""


class JudgeProvider(Protocol):
    """LLM 法官提供方协议（M2 接入点）。

    外部接入方实现该协议即可把任意模型作为法官。返回的 dict 应含
    ``decision``（pass/flag/block）、``reasoning``、``confidence``。
    """

    def arbitrate(self, trace: Trace, verdict_schema: dict[str, Any] | None = None) -> dict[str, Any]: ...


# 越权/违规模式：命中即 BLOCK。
_BLOCK_PATTERNS: tuple[str, ...] = (
    "bypass",
    "escalation_privilege",
    "privilege",
    "exfiltrate",
    "exfiltration",
    "override_deny",
    "cross_org_write",
    "force_trip",
    "unapproved",
)

# 违规风险模式：命中即 FLAG。
_FLAG_PATTERNS: tuple[str, ...] = (
    "retry",
    "fallback",
    "degraded",
    "circuit_breaker_trip",
    "warning",
    "approximate",
    "best_effort",
)


class RuleJudge(Judge):
    """基于策略模式匹配的规则法官。

    对轨迹中每一步 action/decision 进行模式检查：
    - 命中越权/违规模式 → BLOCK
    - 命中风险模式 → FLAG
    - 其余 → PASS
    """

    name = "rule-judge"

    def __init__(
        self,
        block_patterns: tuple[str, ...] = _BLOCK_PATTERNS,
        flag_patterns: tuple[str, ...] = _FLAG_PATTERNS,
    ) -> None:
        self._block_patterns = block_patterns
        self._flag_patterns = flag_patterns

    def arbitrate(
        self,
        trace: Trace,
        verdict_schema: dict[str, Any] | None = None,
    ) -> Verdict:
        block_evidence: list[str] = []
        flag_evidence: list[str] = []
        for step in trace.steps:
            blob = f"{step.action} {step.decision}".lower()
            for pattern in self._block_patterns:
                if pattern in blob:
                    block_evidence.append(
                        f"{step.agent_id}:{step.action}@{step.ts:.2f} (block:{pattern})"
                    )
                    break
            for pattern in self._flag_patterns:
                if pattern in blob:
                    flag_evidence.append(
                        f"{step.agent_id}:{step.action}@{step.ts:.2f} (flag:{pattern})"
                    )
                    break

        if block_evidence:
            return Verdict(
                decision=VerdictDecision.BLOCK,
                reasoning=f"命中越权/违规模式：{', '.join(block_evidence[:3])}",
                evidence_refs=block_evidence[:5],
                confidence=0.95,
                judge_name=self.name,
            )
        if flag_evidence:
            return Verdict(
                decision=VerdictDecision.FLAG,
                reasoning=f"命中风险模式：{', '.join(flag_evidence[:3])}",
                evidence_refs=flag_evidence[:5],
                confidence=0.6,
                judge_name=self.name,
            )
        return Verdict(
            decision=VerdictDecision.PASS,
            reasoning=f"轨迹 {trace.trace_id} 未命中违规或风险模式",
            evidence_refs=[],
            confidence=0.8,
            judge_name=self.name,
        )


class ProviderJudge(Judge):
    """包装 JudgeProvider 的法官适配器（M2）。"""

    name = "provider-judge"

    def __init__(self, provider: JudgeProvider, name: str = "provider-judge") -> None:
        self._provider = provider
        self.name = name

    def arbitrate(
        self,
        trace: Trace,
        verdict_schema: dict[str, Any] | None = None,
    ) -> Verdict:
        result = self._provider.arbitrate(trace, verdict_schema)
        decision = VerdictDecision(result.get("decision", "pass"))
        return Verdict(
            decision=decision,
            reasoning=str(result.get("reasoning", "")),
            evidence_refs=list(result.get("evidence_refs", [])),
            confidence=float(result.get("confidence", 0.5)),
            judge_name=self.name,
        )
