"""Agent-as-a-Judge 法官接口与规则实现（方案 C M1/M2）。

法官对执行轨迹（Trace）进行仲裁，输出带证据引用的裁决（Verdict）。
支持规则法官（RuleJudge，基于策略模式匹配）与可扩展的 LLM 法官
（JudgeProvider 注入点）。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Protocol

from maref.governance.trace import Trace, Verdict, VerdictDecision

_WORD_RE = re.compile(r"\w+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """把文本拆成词级 token（A11 词边界）。

    ``\\w+`` 同时覆盖英文单词、下划线复合词与中文连续串。词边界匹配
    消除子串误报（如 ``privilege`` 不命中 ``privilege_escalation``）。
    """
    return _WORD_RE.findall(text.lower())


def _pattern_matches(blob_tokens: list[str], pattern: str) -> bool:
    """判断 pattern 是否为 blob token 序列的连续子序列。

    中文 token 允许子串包含（中文无空格分词）；英文/复合词要求精确
    token 相等，避免词内子串误报。
    """
    pat_tokens = _tokens(pattern)
    if not pat_tokens:
        return False
    width = len(pat_tokens)
    for i in range(len(blob_tokens) - width + 1):
        matched = True
        for j in range(width):
            blob_tok = blob_tokens[i + j]
            pat_tok = pat_tokens[j]
            if _CJK_RE.search(pat_tok):
                if pat_tok not in blob_tok:
                    matched = False
                    break
            elif blob_tok != pat_tok:
                matched = False
                break
        if matched:
            return True
    return False


class Judge(ABC):
    """法官抽象接口。"""

    name: str = "judge"
    # 法官归属（组织/DID）。非 None 且与被审 agent 同源时法官必须回避
    # （P0-4 recusal），防止「法官评审自己」的自审盲区。
    affiliation: str | None = None

    @abstractmethod
    def arbitrate(self, trace: Trace, verdict_schema: dict[str, Any] | None = None) -> Verdict:
        """对轨迹进行仲裁，返回带证据引用的裁决。"""


class JudgeProvider(Protocol):
    """LLM 法官提供方协议（M2 接入点）。

    外部接入方实现该协议即可把任意模型作为法官。返回的 dict 应含
    ``decision``（pass/flag/block）、``reasoning``、``confidence``。
    """

    def arbitrate(
        self, trace: Trace, verdict_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


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

    affiliation = None  # 规则法官全局中立，无归属、永不回避

    def arbitrate(
        self,
        trace: Trace,
        verdict_schema: dict[str, Any] | None = None,
    ) -> Verdict:
        block_evidence: list[str] = []
        flag_evidence: list[str] = []
        for step in trace.steps:
            blob_tokens = _tokens(f"{step.action} {step.decision}")
            for pattern in self._block_patterns:
                if _pattern_matches(blob_tokens, pattern):
                    block_evidence.append(
                        f"{step.agent_id}:{step.action}@{step.ts:.2f} (block:{pattern})"
                    )
                    break
            for pattern in self._flag_patterns:
                if _pattern_matches(blob_tokens, pattern):
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

    def __init__(
        self,
        provider: JudgeProvider,
        name: str = "provider-judge",
        affiliation: str | None = None,
    ) -> None:
        self._provider = provider
        self.name = name
        # 外部法官归属（组织/DID）：与被审 agent 同源时 recusal 回避。
        self.affiliation = affiliation

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
