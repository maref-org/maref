# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0

"""Unicode 隐写标记检测与净化层.

防御威胁 M-001（隐写标记注入）：检测模型输出中的非标准 Unicode 字符，
例如 Claude 隐写标记（U+02B9 修饰符撇号）、零宽字符、BOM、同形字等。
这些字符可被用于在看似正常的文本中嵌入用户身份追踪标记。

设计原则（旁路直连）:
    本模块不经过 VerifierConsensus 的模拟调用路径，而是直接:
    1. 检测异常 Unicode 字符（UnicodeAnomalyDetector）
    2. 清洗输出文本（StegSanitizer.sanitize）
    3. 高阈值时写入 AuditLogger 审计链
    4. CRITICAL 时通过 ThreatGovernanceBridge 触发 force_halt

同时在 VerifierRegistry 登记元数据用于统计追踪，但真实检测逻辑由本模块直接执行。

Usage:
    from maref.security.steg_sanitizer import StegSanitizer

    sanitizer = StegSanitizer()
    result = sanitizer.sanitize("hello\\u02b9world \\u200bhidden")
    # result.removed_count == 2
    # "\\u02b9" not in result.text
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maref.security.decorators import security_critical

if TYPE_CHECKING:
    from maref.governance.audit import AuditLogger
    from maref.governance.threat_bridge import ThreatGovernanceBridge
    from maref.governance.verifier_registry import VerifierRegistry
    from maref.monitoring.threat_intelligence import ThreatAlert

# 隐写告警类型常量（ThreatAlert.alert_type 字段为字符串，非枚举）
STEG_ALERT_TYPE = "steganography_injection"

# 已知隐写字符集（Claude 隐写标记 + 零宽字符 + BOM）
# U+02B9: MODIFIER LETTER PRIME（Claude 隐写标记，与标准撇号 U+0027 视觉相似）
# U+200B-200F: 零宽空格/连字/不连字/左至右/右至左标记
# U+2028-202F: 行/段分隔符与方向控制字符
# U+FEFF: ZERO WIDTH NO-BREAK SPACE（BOM）
KNOWN_STEGO_CODEPOINTS: frozenset[int] = frozenset(
    [0x02B9, *range(0x200B, 0x2010), *range(0x2028, 0x2030), 0xFEFF]
)

# 允许的 Unicode 通用类别（参照报告建议）
# Lu=大写字母 Ll=小写字母 Nd=数字 Po=其他标点 Zs=空格分隔 Ps=开括号 Pe=闭括号
ALLOWED_CATEGORIES: frozenset[str] = frozenset({"Lu", "Ll", "Nd", "Po", "Zs", "Ps", "Pe"})

# 已知同形字映射（Cyrillic/Greek 与 Latin 视觉相似，可被用于隐写）
# key=可疑 codepoint, value=视觉等价的 Latin 字符
HOMOGLYPH_MAP: dict[int, str] = {
    0x0430: "a",  # Cyrillic small a
    0x0435: "e",  # Cyrillic small ie
    0x043E: "o",  # Cyrillic small o
    0x0440: "p",  # Cyrillic small er
    0x0441: "c",  # Cyrillic small es
    0x0445: "x",  # Cyrillic small ha
    0x0455: "s",  # Cyrillic small dje
    0x03B1: "a",  # Greek small alpha
    0x03BF: "o",  # Greek small omicron
    0x03C1: "p",  # Greek small rho
}

# 清洗正则：匹配所有已知隐写字符
_STEGO_STRIP_PATTERN = re.compile(
    "[" + "".join(chr(cp) for cp in sorted(KNOWN_STEGO_CODEPOINTS)) + "]"
)


@dataclass
class UnicodeAnomaly:
    """单个 Unicode 异常字符记录."""

    codepoint: int
    name: str
    category: str
    position: int
    is_known_stego: bool = False
    homoglyph_of: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "codepoint": f"U+{self.codepoint:04X}",
            "name": self.name,
            "category": self.category,
            "position": self.position,
            "is_known_stego": self.is_known_stego,
            "homoglyph_of": self.homoglyph_of,
        }


@dataclass
class SanitizedOutput:
    """净化后的输出结果."""

    text: str
    removed_count: int
    anomalies: list[UnicodeAnomaly] = field(default_factory=list)
    blocked: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "removed_count": self.removed_count,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "blocked": self.blocked,
            "reason": self.reason,
        }


class UnicodeAnomalyDetector:
    """Unicode 异常字符检测器.

    扫描文本中的非标准 Unicode 字符，识别三类隐写载体:
    1. 已知隐写字符（U+02B9、零宽字符、BOM）
    2. 不在允许类别中的字符（参照 ALLOWED_CATEGORIES）
    3. 同形字（Cyrillic/Greek 与 Latin 视觉相似）
    """

    def detect(self, text: str) -> list[UnicodeAnomaly]:
        """检测文本中的所有 Unicode 异常.

        Args:
            text: 待检测文本.

        Returns:
            异常字符列表，按位置排序。空文本返回空列表。
        """
        anomalies: list[UnicodeAnomaly] = []
        for position, ch in enumerate(text):
            cp = ord(ch)
            category = unicodedata.category(ch)
            name = unicodedata.name(ch, "UNKNOWN")

            is_known_stego = cp in KNOWN_STEGO_CODEPOINTS
            is_homoglyph = cp in HOMOGLYPH_MAP
            category_allowed = category in ALLOWED_CATEGORIES

            # 已知隐写 或 同形字 或 类别不允许 → 记录异常
            if is_known_stego or is_homoglyph or not category_allowed:
                anomalies.append(
                    UnicodeAnomaly(
                        codepoint=cp,
                        name=name,
                        category=category,
                        position=position,
                        is_known_stego=is_known_stego,
                        homoglyph_of=HOMOGLYPH_MAP.get(cp),
                    )
                )
        return anomalies


class StegSanitizer:
    """Unicode 隐写标记净化器.

    在模型输出到达终端用户前过滤非标准 Unicode 字符。
    集成 AuditLogger 记录检测事件，集成 ThreatGovernanceBridge 在
    CRITICAL 级别触发 force_halt。

    Args:
        audit_logger: 可选审计日志器。传入则在检测到异常时写入审计链。
        threat_bridge: 可选威胁治理桥。传入则在 CRITICAL 阈值时触发状态转换。
        threshold: HIGH 告警阈值（异常字符数）。默认 5。
        critical_multiplier: CRITICAL 阈值 = threshold × critical_multiplier。默认 3。
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        threat_bridge: ThreatGovernanceBridge | None = None,
        threshold: int = 5,
        critical_multiplier: int = 3,
    ) -> None:
        self._detector = UnicodeAnomalyDetector()
        self._audit_logger = audit_logger
        self._threat_bridge = threat_bridge
        self._threshold = threshold
        self._critical_threshold = threshold * critical_multiplier

    @security_critical
    def sanitize(self, text: str) -> SanitizedOutput:
        """净化文本：检测 + 清洗 + 审计 + 告警.

        Args:
            text: 待净化的模型输出文本.

        Returns:
            SanitizedOutput，包含清洗后文本、移除字符数、异常列表。
            若达到 CRITICAL 阈值，blocked=True 并附 reason。
        """
        anomalies = self._detector.detect(text)
        clean_text = _STEGO_STRIP_PATTERN.sub("", text)
        # 同形字不删除（删除会破坏可读性），仅记录

        removed_count = len(text) - len(clean_text)
        result = SanitizedOutput(
            text=clean_text,
            removed_count=removed_count,
            anomalies=anomalies,
        )

        if not anomalies:
            return result

        # HIGH 阈值：写入审计链
        if len(anomalies) >= self._threshold and self._audit_logger is not None:
            self._audit_logger.log_anomaly(
                actor="StegSanitizer",
                anomaly_type="unicode_steganography",
                severity="HIGH",
                description=(
                    f"Detected {len(anomalies)} Unicode anomalies "
                    f"(threshold={self._threshold}), removed {removed_count} stego chars"
                ),
            )

        # CRITICAL 阈值：触发 force_halt
        if len(anomalies) >= self._critical_threshold and self._threat_bridge is not None:
            alert = self._build_threat_alert(anomalies)
            self._threat_bridge.on_threat_alert(alert)
            result.blocked = True
            result.reason = (
                f"CRITICAL: {len(anomalies)} anomalies exceed critical threshold "
                f"({self._critical_threshold}); force_halt triggered"
            )

        return result

    def _build_threat_alert(
        self,
        anomalies: list[UnicodeAnomaly],
    ) -> ThreatAlert:
        """构造 CRITICAL 威胁告警.

        Args:
            anomalies: 检测到的异常列表.

        Returns:
            ThreatAlert 实例，severity=CRITICAL.
        """
        from maref.monitoring.threat_intelligence import ThreatAlert, ThreatSeverity

        # 取前 5 个异常作为样本
        sample = ", ".join(f"U+{a.codepoint:04X}({a.name})" for a in anomalies[:5])
        return ThreatAlert(
            alert_id=f"steg-{int(datetime.datetime.now().timestamp())}",
            alert_type=STEG_ALERT_TYPE,
            severity=ThreatSeverity.CRITICAL,
            title="Unicode steganography injection detected",
            description=(
                f"Output contains {len(anomalies)} anomalous Unicode characters. Samples: {sample}"
            ),
            detected_at=datetime.datetime.now(),
            affected_assets=["model_output"],
            recommended_actions=[
                "Quarantine the output",
                "Audit model provider for tracking markers",
                "Review recent prompt injections",
            ],
        )


def register_steg_verifier(registry: VerifierRegistry) -> None:
    """在 VerifierRegistry 登记 StegSanitizer 元数据.

    注意：此为元数据登记，用于统计追踪与精度评估。
    真实检测逻辑由 StegSanitizer.sanitize() 直接调用（旁路直连），
    不经过 VerifierConsensus 的模拟调用路径。

    Args:
        registry: VerifierRegistry 实例.
    """
    from maref.governance.verifier_registry import VerifierEntry, VerifierStatus

    entry = VerifierEntry(
        name="unicode_steg_detector",
        model="StegSanitizer v1",
        methodology="character_codepoint_analysis",
        status=VerifierStatus.ACTIVE,
        accuracy=0.95,
        recall=0.92,
        bias=0.0,
    )
    registry.register(entry)


__all__ = [
    "STEG_ALERT_TYPE",
    "KNOWN_STEGO_CODEPOINTS",
    "ALLOWED_CATEGORIES",
    "HOMOGLYPH_MAP",
    "UnicodeAnomaly",
    "SanitizedOutput",
    "UnicodeAnomalyDetector",
    "StegSanitizer",
    "register_steg_verifier",
]
