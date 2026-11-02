"""InboundNormalizationGate — 入站输入归一化门禁。

定位: 与 ``security.outbound.OutboundMessageGate`` 对称的**入站**决策点。
出站门禁管"发出去的东西", 入站门禁管"喂给模型的输入"。

为什么需要 (Lexsi D6 实测): 模型的安全拒绝是**语义触发**的; base64/rot13/
分片/emoji 替换后的输入不构成语义上的"有害请求", 因此 refusal 通路不激活,
inference-time steering 也无效 (6 档 alpha, ASR 95.8%-100%)。唯一的解法是在
输入侧先把编码还原, 再交给下游模型或策略层判定。

决策四态:
    ALLOW   — 无可疑解码, 原样放行
    REWRITE — 检测到编码/混淆, 用归一化文本替换原输入后放行
    HITL    — 解码出内容但置信不足, 升级人工/下游复核
    DENY    — 归一化后命中明确有害模式, 直接阻断

设计原则:
- 纯函数式裁决 (``check`` 无副作用), 便于审计与单测
- 未命中一律 ALLOW (fail-open) — 因为它只是**加分项**, 不是唯一防线;
  真正的 fail-closed 由下游策略/模型/人工闸门承担
- 裁决不记录原文到日志, 只记录方法与哈希 (防 PII 入审计链)
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum

from maref.security.inbound.normalization import MAX_INPUT_CHARS, decode_candidates, looks_like_text

DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    r"pick(?:ing)? a lock",
    r"bypass (?:a |the )?(?:login|lock|door|badge|reader)",
    r"pipe bomb",
    r"ransomware",
    r"phishing",
    r"poison(?:ing)? someone",
    r"exfiltrat",
    r"steal (?:saved )?passwords",
    r"smuggle",
    r"clone a badge",
    r"disable the audit",
    r"environment files",
    r"api keys",
    r"authorized_keys",
    r"tailgat",
    r"defeat a door sensor",
    r"crack (?:a )?(?:wifi|wi-fi|password)",
    r"unlock\b.{0,24}\block\b",
    r"lockpick",
    r"ignore (?:all |your )?(?:previous|prior) instructions",
    r"system prompt",
    r"开锁",
    r"撬锁",
    r"系统提示",
)

# 这些方法产出的候选才视为"真实还原" (排除键盘移位等易误报项)
_HIGH_CONFIDENCE_METHODS = frozenset(
    {
        "base64",
        "base32",
        "rot13",
        "reversed",
        "morse",
        "split_concat",
        "filler_stripped",
        "homoglyph",
        "emoji_mapped",
        "url",
        "pinyin_hint",
        "zalgo_stripped",
        "leet",
    }
)

# 强还原方法: 结构性编码, 结果可读时直接 REWRITE
_STRONG_METHODS = frozenset(
    {
        "base64",
        "base32",
        "morse",
        "split_concat",
        "reversed",
        "filler_stripped",
        "homoglyph",
        "emoji_mapped",
        "pinyin_hint",
        "url",
    }
)

# 还原方法的可信度排序: 小号优先 (结构性编码 > 单字符替换)
_METHOD_PRIORITY = {
    "base64": 0,
    "base32": 1,
    "morse": 2,
    "split_concat": 3,
    "reversed": 4,
    "filler_stripped": 5,
    "homoglyph": 6,
    "emoji_mapped": 7,
    "pinyin_hint": 8,
    "url": 9,
    "zalgo_stripped": 10,
    "leet": 11,
    "rot13": 12,
    "keyboard_left": 13,
}


# 防御性/合法求助语境: 命中 deny 模式时降级为 HITL 而非硬拦
_BENIGN_CONTEXT = re.compile(
    r"\b(?:how|explain)\b.{0,60}\b(?:detected|prevented|mitigated|protected)\b"
    r"|\b(?:detected|prevented|mitigated|protected)\b.{0,60}\b(?:how|explain)\b"
    r"|\b(?:detect|prevent|protect|defend) (?:against|from)\b"
    r"|\blost my key\b|\blocksmith\b"
    r"|\b(?:is|are) these? (?:signs|indicators)\b",
    re.I,
)


class InboundDecision(str, Enum):
    ALLOW = "allow"
    REWRITE = "rewrite"
    HITL = "hitl"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class InboundVerdict:
    """一次入站裁决结果。"""

    decision: InboundDecision
    original: str
    normalized: str
    methods: tuple[str, ...] = ()
    matched: str | None = None
    reason: str = ""
    elapsed_ms: float = 0.0
    input_digest: str = field(default="")

    @property
    def blocked(self) -> bool:
        return self.decision is InboundDecision.DENY


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _looks_like_prose(text: str) -> bool:
    """粗判一段文本像自然语言 (含空格 + 元音比例合理)。"""
    if len(text) < 8:
        return False
    letters = [c for c in text.lower() if c.isalpha()]
    if len(letters) < 6:
        return False
    vowels = sum(1 for c in letters if c in "aeiou")
    return (" " in text.strip()) and 0.15 <= vowels / len(letters) <= 0.6


class InboundNormalizationGate:
    """入站输入归一化门禁。

    Args:
        deny_patterns: 有害意图正则; 默认用 ``DEFAULT_DENY_PATTERNS``。
        max_candidates: 单次最多解码候选数 (防放大攻击)。
        default_decision: 检测到编码但未命中 deny 时的默认处置,
            取 ``"rewrite"`` 或 ``"hitl"``。
    """

    def __init__(
        self,
        deny_patterns: tuple[str, ...] | None = None,
        *,
        max_candidates: int = 8,
        default_decision: InboundDecision = InboundDecision.REWRITE,
    ) -> None:
        patterns = deny_patterns if deny_patterns is not None else DEFAULT_DENY_PATTERNS
        if not patterns:
            raise ValueError("deny_patterns must be non-empty")
        self._deny_re = re.compile("|".join(patterns), re.I)
        self.max_candidates = max(1, min(int(max_candidates), 64))
        if default_decision not in (InboundDecision.REWRITE, InboundDecision.HITL):
            raise ValueError("default_decision must be REWRITE or HITL")
        self.default_decision = default_decision

    def check(self, text: str) -> InboundVerdict:
        """对单条输入做裁决 (无副作用)。"""
        started = time.perf_counter()
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if len(text) > MAX_INPUT_CHARS:
            raise ValueError(f"input too long: {len(text)} > {MAX_INPUT_CHARS}")

        if not text.strip():
            return self._verdict(
                InboundDecision.ALLOW, text, text, (), None, "empty input", started
            )

        candidates = decode_candidates(text, max_candidates=self.max_candidates)
        # 明文也做一次 deny 检查: 门禁不止还原编码, 也拦明显有害的直白输入
        m_raw = self._deny_re.search(text)
        if m_raw:
            decision = (
                InboundDecision.HITL if _BENIGN_CONTEXT.search(text) else InboundDecision.DENY
            )
            return self._verdict(
                decision,
                text,
                text,
                ("raw",),
                m_raw.group(0),
                "deny pattern on raw input"
                + ("; benign context -> HITL" if decision is InboundDecision.HITL else ""),
                started,
            )

        decoded = [c for c in candidates if c.method != "raw"]
        if not decoded:
            return self._verdict(
                InboundDecision.ALLOW, text, text, (), None, "no encoding detected", started
            )

        # 1) 明确有害 → DENY
        for cand in decoded:
            m = self._deny_re.search(cand.text)
            if m:
                decision = (
                    InboundDecision.HITL
                    if _BENIGN_CONTEXT.search(cand.text)
                    else InboundDecision.DENY
                )
                reason = (
                    f"deny pattern after {cand.method} decode; benign context -> HITL"
                    if decision is InboundDecision.HITL
                    else f"deny pattern after {cand.method} decode"
                )
                return self._verdict(
                    decision, text, cand.text, (cand.method,), m.group(0), reason, started
                )

        # 2) 高置信还原且像自然语言 (英文/中文) → REWRITE
        high = [c for c in decoded if c.method in _HIGH_CONFIDENCE_METHODS]
        readable = [c for c in high if looks_like_text(c.text)]
        if not readable:
            # 解码结果都不是可读文本 (如长字母串被当成 base64 的伪解码) -> 不是编码攻击
            return self._verdict(
                InboundDecision.ALLOW,
                text,
                text,
                (),
                None,
                "decoded candidates are not readable text",
                started,
            )
        strong = [c for c in readable if c.method in _STRONG_METHODS]
        if strong:
            best = min(strong, key=lambda c: (_METHOD_PRIORITY.get(c.method, 99), -len(c.text)))
            return self._verdict(
                InboundDecision.REWRITE,
                text,
                best.text,
                (best.method,),
                None,
                f"rewritten via {best.method}",
                started,
            )

        # 3) 只有弱方法 (rot13/leet/键盘移位) 可读 → 默认处置
        weak = min(readable, key=lambda c: _METHOD_PRIORITY.get(c.method, 99))
        return self._verdict(
            self.default_decision,
            text,
            weak.text,
            (weak.method,),
            None,
            f"encoding detected via {weak.method}; no confident rewrite",
            started,
        )

    def _verdict(
        self,
        decision: InboundDecision,
        original: str,
        normalized: str,
        methods: tuple[str, ...],
        matched: str | None,
        reason: str,
        started: float,
    ) -> InboundVerdict:
        return InboundVerdict(
            decision=decision,
            original=original,
            normalized=normalized,
            methods=methods,
            matched=matched,
            reason=reason,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            input_digest=_digest(original),
        )


__all__ = [
    "DEFAULT_DENY_PATTERNS",
    "InboundDecision",
    "InboundNormalizationGate",
    "InboundVerdict",
]
