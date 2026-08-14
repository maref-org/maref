"""ContactReputation — 外部联系人可信度 (v0.52.1 G3-A4)。

评估 agent 发起出站通信的接收方可信度。首次联系的外部主体起始低可信，
连续良性交互后递增。与 ``OutboundMessageGate`` 联动: 低可信联系人 +
社交工程信号 → 升级 HITL。

设计:
- 以 (recipient, channel) 为键维护信誉分 0.0~1.0
- 起始分由渠道风险决定 (文件传输/外部陌生域 起始更低)
- 良性交互 (门禁放行且无信号) 递增; 命中信号递减
- ``ContactTier``: UNTRUSTED / UNKNOWN / TRUSTED / VERIFIED
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.security.outbound.message import OutboundChannel


class ContactTier(str, Enum):
    """联系人信誉等级枚举。"""

    UNTRUSTED = "untrusted"  # 0.0 ~ 0.3 — 高风险, 出站需人工确认
    UNKNOWN = "unknown"  # 0.3 ~ 0.6 — 默认起始区间
    TRUSTED = "trusted"  # 0.6 ~ 0.9 — 常规放行, 仍保留抽检
    VERIFIED = "verified"  # 0.9 ~ 1.0 — 已验证, 低风险放行

    @property
    def label(self) -> str:
        return {
            ContactTier.UNTRUSTED: "不可信",
            ContactTier.UNKNOWN: "未知",
            ContactTier.TRUSTED: "可信",
            ContactTier.VERIFIED: "已验证",
        }[self]


@dataclass
class ContactRecord:
    """单个联系人信誉记录。

    Attributes:
        recipient: 接收方地址。
        channel: 渠道。
        score: 信誉分 0.0~1.0。
        interaction_count: 累计交互次数。
        verified: 是否经人工/权威验证。
        last_seen: 最近交互时间戳。
    """

    recipient: str
    channel: str
    score: float = 0.4
    interaction_count: int = 0
    verified: bool = False
    last_seen: float = field(default_factory=time.time)

    @property
    def tier(self) -> ContactTier:
        if self.verified:
            return ContactTier.VERIFIED
        if self.score >= 0.9:
            return ContactTier.VERIFIED
        if self.score >= 0.6:
            return ContactTier.TRUSTED
        if self.score >= 0.3:
            return ContactTier.UNKNOWN
        return ContactTier.UNTRUSTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipient": self.recipient,
            "channel": self.channel,
            "score": round(self.score, 3),
            "tier": self.tier.value,
            "interaction_count": self.interaction_count,
            "verified": self.verified,
            "last_seen": self.last_seen,
        }


# 渠道起始信誉分 (高风险渠道起始更低)
_CHANNEL_BASE_SCORES: dict[OutboundChannel, float] = {
    OutboundChannel.EMAIL: 0.4,
    OutboundChannel.SLACK: 0.4,
    OutboundChannel.DISCORD: 0.4,
    OutboundChannel.A2A: 0.5,
    OutboundChannel.MCP: 0.5,
    OutboundChannel.TOOL: 0.4,
    OutboundChannel.FILE_TRANSFER: 0.2,  # 在线文件传输 (AISI 场景高危渠道)
    OutboundChannel.HTTP: 0.3,
    OutboundChannel.OTHER: 0.4,
}

# 单次交互信誉增减步长
_SCORE_INCREASE = 0.05
_SCORE_DECREASE = 0.2
_MAX_SCORE = 1.0
_MIN_SCORE = 0.0


class ContactReputation:
    """外部联系人信誉管理器。

    Usage::

        reputation = ContactReputation()
        record = reputation.get("bob@example.com", OutboundChannel.EMAIL)
        reputation.report_benign(...)   # 良性交互 → 加分
        reputation.report_violation(...)  # 命中 SE/载荷 → 减分
    """

    def __init__(self) -> None:
        self._records: dict[str, ContactRecord] = {}

    def _key(self, recipient: str, channel: OutboundChannel) -> str:
        return f"{channel.value}:{recipient.lower()}"

    def get(self, recipient: str, channel: OutboundChannel) -> ContactRecord:
        """获取联系人信誉记录 (不存在则创建, 起始分由渠道决定)。

        Args:
            recipient: 接收方地址。
            channel: 传输渠道。

        Returns:
            联系人的 ContactRecord。
        """
        key = self._key(recipient, channel)
        record = self._records.get(key)
        if record is None:
            base = _CHANNEL_BASE_SCORES.get(channel, 0.4)
            record = ContactRecord(
                recipient=recipient,
                channel=channel.value,
                score=base,
            )
            self._records[key] = record
        return record

    def report_benign(self, recipient: str, channel: OutboundChannel) -> ContactRecord:
        """报告一次良性交互 (门禁放行且无信号) → 信誉分小幅递增。"""
        record = self.get(recipient, channel)
        record.score = min(_MAX_SCORE, record.score + _SCORE_INCREASE)
        record.interaction_count += 1
        record.last_seen = time.time()
        return record

    def report_violation(self, recipient: str, channel: OutboundChannel) -> ContactRecord:
        """报告一次违规 (命中 SE/载荷/被拒) → 信誉分大幅递减。"""
        record = self.get(recipient, channel)
        record.score = max(_MIN_SCORE, record.score - _SCORE_DECREASE)
        record.interaction_count += 1
        record.last_seen = time.time()
        return record

    def verify(self, recipient: str, channel: OutboundChannel) -> ContactRecord:
        """人工/权威验证联系人 → 直接置为 VERIFIED。"""
        record = self.get(recipient, channel)
        record.verified = True
        record.score = _MAX_SCORE
        return record

    def all_records(self) -> list[ContactRecord]:
        """返回全部联系人记录 (审计/报告用)。"""
        return list(self._records.values())
