"""Outbound guardrail — 出站消息护栏 (v0.52.1 G3)。

拦截 agent → 外部人类/第三方平台的出站通信中的社交工程与恶意载荷。
对位 AISI 欺骗测试发现 ②（社交工程攻击）与发现 ③（提示注入攻击）。

模块组成:
- ``message`` — OutboundMessage 出站消息模型
- ``social_engineering`` — SocialEngineeringDetector 8 类 SE 模式检测
- ``payload`` — OutboundPayloadSanitizer 出站载荷消毒
- ``contact`` — ContactReputation 外部联系人可信度
- ``gate`` — OutboundMessageGate 策略门禁 (ALLOW / HITL / DENY)
"""

from __future__ import annotations

from maref.security.outbound.contact import ContactReputation, ContactTier
from maref.security.outbound.gate import (
    BlockedOutboundError,
    GateDecision,
    OutboundMessageGate,
    OutboundVerdict,
)
from maref.security.outbound.guard import OutboundGuard
from maref.security.outbound.message import (
    OutboundAttachment,
    OutboundChannel,
    OutboundMessage,
    RecipientType,
)
from maref.security.outbound.payload import (
    OutboundPayloadSanitizer,
    PayloadFlag,
    PayloadSanitizeResult,
)
from maref.security.outbound.social_engineering import (
    SePattern,
    SeSignal,
    SocialEngineeringDetector,
)

__all__ = [
    "OutboundMessage",
    "OutboundAttachment",
    "OutboundChannel",
    "RecipientType",
    "SocialEngineeringDetector",
    "SePattern",
    "SeSignal",
    "OutboundPayloadSanitizer",
    "PayloadFlag",
    "PayloadSanitizeResult",
    "ContactReputation",
    "ContactTier",
    "OutboundMessageGate",
    "GateDecision",
    "OutboundVerdict",
    "BlockedOutboundError",
    "OutboundGuard",
]
