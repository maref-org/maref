"""Inbound 安全层 — 输入侧归一化与门禁 (v0.56 新增)。

Lexsi D6 实测沉淀: 编码攻击必须先在输入侧还原, 语义层的安全机制 (含
inference-time steering) 对编码输入无效。
"""

from maref.security.inbound.gate import (
    DEFAULT_DENY_PATTERNS,
    InboundDecision,
    InboundNormalizationGate,
    InboundVerdict,
)
from maref.security.inbound.normalization import (
    MAX_CANDIDATES,
    MAX_INPUT_CHARS,
    DecodedCandidate,
    decode_candidates,
)

__all__ = [
    "DEFAULT_DENY_PATTERNS",
    "DecodedCandidate",
    "InboundDecision",
    "InboundNormalizationGate",
    "InboundVerdict",
    "MAX_CANDIDATES",
    "MAX_INPUT_CHARS",
    "decode_candidates",
]
