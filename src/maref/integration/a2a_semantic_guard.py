"""A2A semantic integrity + covert-channel guard — 语义层完整性 (P2-11).

Ed25519 签名（``integration/a2a_secure_transport``）保证消息**来源与完整性**，但保证不了
**语义与声明任务一致**；已有共谋检测（``sentinel.identity.collusion_detector``）与隐写净化
（``security.steg_sanitizer``）。OWASP ASI07 点名 agent 间通信的 semantic validation 是空白。

本模块补两个缺口：
1. **语义完整性**：声明动作 vs 载荷意图不一致（如声明 ``read`` 但载荷含 ``delete``/``exec``/
   ``curl`` 等越权意图），接入 A2A 消息校验。
2. **隐蔽信道**：Unicode 隐写（复用 :class:`UnicodeAnomalyDetector`）+ timing 低方差规律性
   检测（规律间隔疑似时钟型隐蔽信道）。
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from maref.security.steg_sanitizer import UnicodeAnomalyDetector

DEFAULT_FORBIDDEN_MARKERS: dict[str, frozenset[str]] = {
    "read": frozenset(
        {
            "delete",
            "drop ",
            "truncate",
            "rm -rf",
            "chmod",
            "chown",
            "sudo",
            "exec(",
            "os.system",
            "curl ",
            "wget ",
            "exfiltrat",
            "upload",
        }
    ),
    "query": frozenset({"delete", "update ", "insert ", "drop ", "grant ", "truncate"}),
    "list": frozenset({"delete", "rm -rf", "exec(", "curl ", "wget "}),
}


@dataclass
class SemanticDecision:
    """Result of a declared-action vs payload-intent check."""

    allowed: bool
    reason: str = ""
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "findings": list(self.findings)}


class SemanticIntegrityGuard:
    """Checks A2A message semantics and detects covert channels."""

    def __init__(
        self,
        forbidden_markers: Mapping[str, Sequence[str]] | None = None,
        timing_cv_threshold: float = 0.05,
    ) -> None:
        if timing_cv_threshold < 0:
            raise ValueError("timing_cv_threshold must be >= 0")
        source = forbidden_markers if forbidden_markers is not None else DEFAULT_FORBIDDEN_MARKERS
        self._forbidden: dict[str, frozenset[str]] = {
            action: frozenset(markers) for action, markers in source.items()
        }
        self._cv_threshold = timing_cv_threshold
        self._detector = UnicodeAnomalyDetector()

    def check(self, declared_action: str, payload: str) -> SemanticDecision:
        """Verify the payload intent does not contradict the declared action."""
        markers = self._forbidden.get(declared_action)
        if not markers:
            return SemanticDecision(True, f"no semantic policy for action '{declared_action}'")
        text = (payload or "").lower()
        hits = sorted(marker for marker in markers if marker in text)
        if hits:
            return SemanticDecision(
                False,
                f"payload intent contradicts declared action '{declared_action}'",
                hits,
            )
        return SemanticDecision(True, "payload consistent with declared action")

    def detect_unicode_covert_channel(self, payload: str) -> list[str]:
        """Return codepoints of anomalous Unicode characters (potential stego)."""
        return [f"U+{anomaly.codepoint:04X}" for anomaly in self._detector.detect(payload or "")]

    def detect_timing_covert_channel(self, intervals: Sequence[float]) -> bool:
        """Flag suspiciously regular message intervals (low coefficient of variation)."""
        values = [float(value) for value in intervals]
        if len(values) < 3:
            return False
        mean = statistics.fmean(values)
        if mean <= 0:
            return False
        try:
            deviation = statistics.pstdev(values)
        except statistics.StatisticsError:
            return False
        return (deviation / mean) <= self._cv_threshold

    def inspect(
        self,
        declared_action: str,
        payload: str,
        intervals: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        """Combined semantic + covert-channel inspection."""
        decision = self.check(declared_action, payload)
        unicode_findings = self.detect_unicode_covert_channel(payload)
        timing_covert = intervals is not None and self.detect_timing_covert_channel(intervals)
        covert = bool(unicode_findings) or timing_covert
        return {
            "allowed": decision.allowed and not covert,
            "semantic": decision.to_dict(),
            "unicode_covert": unicode_findings,
            "timing_covert": timing_covert,
        }
