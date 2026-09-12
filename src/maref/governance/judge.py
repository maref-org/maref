"""Agent-as-a-Judge 法官接口与规则实现（方案 C M1/M2）。

法官对执行轨迹（Trace）进行仲裁，输出带证据引用的裁决（Verdict）。
支持规则法官（RuleJudge，基于策略模式匹配）与可扩展的 LLM 法官
（JudgeProvider 注入点）。
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
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


class AttackEntropyTracker:
    """攻击分布熵跟踪器（T-P0-2）。

    依据：不可能锁（arXiv 2608.01388）——固定 FSA 的 recall 上界受攻击分布
    top-k 集中度约束（攻击分布熵解释 76% 方差）。攻击分布熵上升说明攻击模式
    正在多样化，规则集覆盖可能不足，应触发不变量进化（而非继续加词表）。

    度量：
      - Shannon 熵 ``H = -Σ p_i·log2(p_i)``（bits）
      - 归一化熵 ``H_norm = H / log2(k)`` ∈ [0, 1]，k = 已观测模式数
      - ``should_evolve()``：归一化熵 ≥ 阈值 → 建议触发不变量进化
    """

    def __init__(self, evolve_threshold: float = 0.85) -> None:
        self._evolve_threshold = evolve_threshold
        self._counts: Counter[str] = Counter()
        self._total = 0

    def record(self, patterns: list[str]) -> None:
        """记录本轮命中的模式（每个模式计一次）。"""
        for p in patterns:
            self._counts[p] += 1
            self._total += 1

    def entropy(self) -> float:
        """攻击分布 Shannon 熵（bits）。无样本时为 0。"""
        if self._total == 0:
            return 0.0
        h = 0.0
        for c in self._counts.values():
            p = c / self._total
            h -= p * math.log2(p)
        return h

    def normalized_entropy(self) -> float:
        """归一化熵 H/log2(k) ∈ [0,1]。k≤1 时为 0。"""
        k = len(self._counts)
        if k <= 1:
            return 0.0
        return self.entropy() / math.log2(k)

    def observed_classes(self) -> int:
        return len(self._counts)

    def should_evolve(self) -> bool:
        """熵 ≥ 阈值 → 建议触发不变量进化（不变量集是 RSI 变异对象）。"""
        return self.observed_classes() > 1 and self.normalized_entropy() >= self._evolve_threshold

    def snapshot(self) -> dict[str, Any]:
        return {
            "entropy_bits": round(self.entropy(), 4),
            "normalized_entropy": round(self.normalized_entropy(), 4),
            "observed_classes": self.observed_classes(),
            "total_hits": self._total,
            "evolve_threshold": self._evolve_threshold,
            "should_evolve": self.should_evolve(),
        }


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
        entropy_tracker: AttackEntropyTracker | None = None,
    ) -> None:
        self._block_patterns = block_patterns
        self._flag_patterns = flag_patterns
        self._entropy = entropy_tracker or AttackEntropyTracker()

    affiliation = None  # 规则法官全局中立，无归属、永不回避

    def entropy_snapshot(self) -> dict[str, Any]:
        """攻击分布熵快照（T-P0-2）。

        ``should_evolve=True`` 表示攻击模式多样性已超过阈值，调用方应触发
        不变量进化（RSI 变异对象 = 不变量集），而非继续扩充词表。
        """
        return self._entropy.snapshot()

    def arbitrate(
        self,
        trace: Trace,
        verdict_schema: dict[str, Any] | None = None,
    ) -> Verdict:
        block_evidence: list[str] = []
        flag_evidence: list[str] = []
        hit_patterns: list[str] = []
        for step in trace.steps:
            blob_tokens = _tokens(f"{step.action} {step.decision}")
            for pattern in self._block_patterns:
                if _pattern_matches(blob_tokens, pattern):
                    block_evidence.append(
                        f"{step.agent_id}:{step.action}@{step.ts:.2f} (block:{pattern})"
                    )
                    hit_patterns.append(f"block:{pattern}")
                    break
            for pattern in self._flag_patterns:
                if _pattern_matches(blob_tokens, pattern):
                    flag_evidence.append(
                        f"{step.agent_id}:{step.action}@{step.ts:.2f} (flag:{pattern})"
                    )
                    hit_patterns.append(f"flag:{pattern}")
                    break
        self._entropy.record(hit_patterns)

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
