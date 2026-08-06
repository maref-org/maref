"""OutboundMessageGate — 出站消息策略门禁 (v0.52.1 G3-A5)。

出站通信的单入口决策点: 对 ``OutboundMessage`` 执行 社交工程检测 +
载荷消毒 + 联系人信誉 + 渠道风险 的聚合裁决, 输出三态决策。

    门禁三态:
    - ALLOW — 无信号 + 载荷干净 + 联系人可信 → 放行
    - HITL  — 命中 SE 信号/载荷风险/低可信联系人 → 升级人工确认
    - DENY  — 可执行载荷/组合攻击/明确恶意 → 直接阻断

与 sentinel 集成: 裁决产 ``ObservationEvent`` (AttackType=SOCIAL_ENGINEERING,
HMAC 签名), 流入 ``ThreatGovernanceBridge`` → 八卦状态机 (CRITICAL→force_halt)。

设计:
- 纯输入裁决 (gate.check) 不产生副作用; 事件发出由 ``emit_event`` 显式触发
- 阈值可配置 (se_hitl_threshold / payload_deny_flags)
- 供出站通道 (mcp/a2a/tool) 统一挂接, 未挂接通道默认 fail-closed
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.security.outbound.contact import ContactReputation, ContactTier
from maref.security.outbound.message import (
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
    SeSignal,
    SocialEngineeringDetector,
)
from maref.sentinel.event import AttackType, ObservationEvent, Severity


class GateDecision(str, Enum):
    """门禁三态决策。"""

    ALLOW = "allow"
    HITL = "hitl"  # 需人工确认
    DENY = "deny"

    @property
    def label(self) -> str:
        return {
            GateDecision.ALLOW: "放行",
            GateDecision.HITL: "人工确认",
            GateDecision.DENY: "阻断",
        }[self]


@dataclass
class OutboundVerdict:
    """出站消息门禁裁决结果。

    Attributes:
        decision: 门禁决策。
        reasons: 决策理由列表 (审计)。
        se_signals: 命中的社交工程信号。
        payload_result: 载荷检测结果。
        contact_tier: 联系人信誉等级。
        message_id: 关联的出站消息 ID。
        checked_at: 裁决时间戳。
        event: 若触发事件发出则为 ObservationEvent (否则 None)。
    """

    decision: GateDecision
    reasons: list[str] = field(default_factory=list)
    se_signals: list[SeSignal] = field(default_factory=list)
    payload_result: PayloadSanitizeResult = field(default_factory=PayloadSanitizeResult)
    contact_tier: ContactTier = ContactTier.UNKNOWN
    message_id: str = ""
    checked_at: float = field(default_factory=time.time)
    event: ObservationEvent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "decision_label": self.decision.label,
            "reasons": self.reasons,
            "se_signals": [s.to_dict() for s in self.se_signals],
            "payload": self.payload_result.to_dict(),
            "contact_tier": self.contact_tier.value,
            "message_id": self.message_id,
            "checked_at": self.checked_at,
        }


# 直接阻断的载荷标记 (可执行/附件可执行/压缩包宏)
_DENY_PAYLOAD_FLAGS: frozenset[PayloadFlag] = frozenset(
    {
        PayloadFlag.EXECUTABLE,
        PayloadFlag.ATTACHMENT_EXECUTABLE,
        PayloadFlag.ATTACHMENT_ARCHIVE_MACRO,
    }
)

# 高危出站渠道: 任何信号/载荷命中即升级
_HIGH_RISK_CHANNELS: frozenset[OutboundChannel] = frozenset(
    {
        OutboundChannel.FILE_TRANSFER,
        OutboundChannel.HTTP,
    }
)


class OutboundMessageGate:
    """出站消息门禁。

    Usage::

        gate = OutboundMessageGate()
        verdict = gate.check(message)
        if verdict.decision == GateDecision.HITL:
            # 升级 human/decision_api.py 人工确认
            ...
        elif verdict.decision == GateDecision.DENY:
            raise BlockedOutboundError(...)

    Attributes:
        detector: 社交工程检测器。
        sanitizer: 载荷消毒器。
        reputation: 联系人信誉管理器。
        hmac_key: sentinel 事件 HMAC 签名密钥 (None = 不发出事件)。
    """

    def __init__(
        self,
        detector: SocialEngineeringDetector | None = None,
        sanitizer: OutboundPayloadSanitizer | None = None,
        reputation: ContactReputation | None = None,
        hmac_key: bytes | None = None,
        se_hitl_threshold: float = 0.7,
    ) -> None:
        self.detector = detector or SocialEngineeringDetector()
        self.sanitizer = sanitizer or OutboundPayloadSanitizer()
        self.reputation = reputation or ContactReputation()
        self.hmac_key = hmac_key
        self.se_hitl_threshold = se_hitl_threshold

    # -- 主入口 --

    def check(self, message: OutboundMessage) -> OutboundVerdict:
        """对出站消息执行聚合裁决。

        Args:
            message: 待发送的出站消息。

        Returns:
            OutboundVerdict, 含三态决策与完整证据。
        """
        reasons: list[str] = []

        # 1. 社交工程检测 (正文 + 附件文件名)
        scan_text = message.body
        if message.attachments:
            names = "; ".join(a.filename for a in message.attachments)
            scan_text = f"{scan_text}\n{names}"
        se_signals, se_count = self.detector.detect_combined(scan_text)

        # 2. 载荷消毒
        payload_result = self.sanitizer.sanitize(
            body=message.body,
            attachments=message.attachments,
        )

        # 3. 联系人信誉
        record = self.reputation.get(message.recipient, message.channel)
        contact_tier = record.tier

        # 4. 聚合裁决
        decision = self._decide(
            message=message,
            se_signals=se_signals,
            se_count=se_count,
            payload_result=payload_result,
            contact_tier=contact_tier,
            reasons=reasons,
        )

        verdict = OutboundVerdict(
            decision=decision,
            reasons=reasons,
            se_signals=se_signals,
            payload_result=payload_result,
            contact_tier=contact_tier,
            message_id=message.message_id,
        )

        # 5. 信誉反馈: 恶意 → 减分; 良性 → 加分
        if decision == GateDecision.DENY or (
            decision == GateDecision.HITL and (se_signals or payload_result.blocked)
        ):
            self.reputation.report_violation(message.recipient, message.channel)
        elif decision == GateDecision.ALLOW:
            self.reputation.report_benign(message.recipient, message.channel)

        # 6. 发出 sentinel 事件 (可配置 hmac_key)
        if decision != GateDecision.ALLOW and self.hmac_key is not None:
            verdict.event = self._build_event(message, verdict)

        return verdict

    def emit_event(self, verdict: OutboundVerdict, message: OutboundMessage) -> ObservationEvent:
        """为已产出的裁决显式构造 sentinel 事件 (供调用方主动上报)。"""
        return self._build_event(message, verdict)

    # -- 内部裁决 --

    def _decide(
        self,
        message: OutboundMessage,
        se_signals: list[SeSignal],
        se_count: int,
        payload_result: PayloadSanitizeResult,
        contact_tier: ContactTier,
        reasons: list[str],
    ) -> GateDecision:
        # DENY 优先级 1: 可执行/附件可执行载荷
        deny_flags = [f for f in payload_result.flags if f in _DENY_PAYLOAD_FLAGS]
        if deny_flags:
            reasons.append(
                "阻断: 出站载荷含可执行内容 "
                f"({', '.join(f.value for f in deny_flags)})"
            )
            return GateDecision.DENY

        # DENY 优先级 2: 凭证索取 + 代码诱饵 组合 (明确恶意攻击链)
        combos = {s.pattern.value for s in se_signals}
        if "credential_harvest" in combos and "code_lure" in combos:
            reasons.append("阻断: 凭证索取 + 代码诱饵 组合攻击")
            return GateDecision.DENY
        if "credential_harvest" in combos and "link_redirect" in combos:
            reasons.append("阻断: 凭证索取 + 链接重定向 组合攻击")
            return GateDecision.DENY

        # DENY 优先级 3: 高置信 SE 信号 (≥0.95) 对真实人类
        high_conf = [s for s in se_signals if s.confidence >= 0.95]
        if high_conf and message.recipient_type == RecipientType.HUMAN:
            reasons.append(
                "阻断: 对真实人类的强社交工程信号 "
                f"({', '.join(s.pattern.value for s in high_conf)})"
            )
            return GateDecision.DENY

        # HITL 优先级 1: 载荷风险 (非直接可执行但可疑)
        if payload_result.blocked:
            reasons.append(
                f"人工确认: 载荷风险标记 {', '.join(f.value for f in payload_result.flags)}"
            )
            return GateDecision.HITL

        # HITL 优先级 2: 组合 SE 模式 (2+ 种同时命中)
        if se_count >= 2:
            reasons.append(
                f"人工确认: 组合社交工程模式 ({se_count} 种: "
                f"{', '.join(s.pattern.value for s in se_signals)})"
            )
            return GateDecision.HITL

        # HITL 优先级 3: 单模式高置信或命中高危渠道
        strong = [s for s in se_signals if s.confidence >= self.se_hitl_threshold]
        if strong or message.channel in _HIGH_RISK_CHANNELS and se_signals:
            reasons.append(
                f"人工确认: 社交工程信号 "
                f"({', '.join(s.pattern.value for s in (strong or se_signals))})"
            )
            return GateDecision.HITL

        # HITL 优先级 4: 联系人不可信 + 存在任何信号/对人发送
        if contact_tier == ContactTier.UNTRUSTED:
            if se_signals or message.recipient_type == RecipientType.HUMAN:
                reasons.append("人工确认: 联系人不可信且存在风险上下文")
                return GateDecision.HITL

        # 高危渠道 + 面向外部人类 → 保守人工确认
        if (
            message.channel in _HIGH_RISK_CHANNELS
            and message.recipient_type == RecipientType.HUMAN
        ):
            reasons.append("人工确认: 高危渠道向真实人类发送")
            return GateDecision.HITL

        # 默认放行 (低风险)
        reasons.append("放行: 无风险信号")
        return GateDecision.ALLOW

    # -- sentinel 事件构造 --

    def _build_event(
        self,
        message: OutboundMessage,
        verdict: OutboundVerdict,
    ) -> ObservationEvent:
        severity = (
            Severity.CRITICAL
            if verdict.decision == GateDecision.DENY
            else Severity.HIGH
        )
        evidence: dict[str, Any] = {
            "channel": message.channel.value,
            "recipient": message.recipient,
            "recipient_type": message.recipient_type.value,
            "sender_agent_id": message.sender_agent_id,
            "decision": verdict.decision.value,
            "se_patterns": [s.pattern.value for s in verdict.se_signals],
            "payload_flags": [f.value for f in verdict.payload_result.flags],
            "contact_tier": verdict.contact_tier.value,
            "reasons": verdict.reasons,
        }
        event = ObservationEvent(
            event_id=str(uuid.uuid4()),
            ts=time.time(),
            source="outbound_gate",
            severity=severity,
            subject=message.sender_agent_id,
            attack_type=AttackType.SOCIAL_ENGINEERING,
            evidence=evidence,
        )
        if self.hmac_key is not None:
            event = event.with_hash(self.hmac_key)
        return event


class BlockedOutboundError(Exception):
    """出站消息被门禁阻断。"""

    def __init__(self, verdict: OutboundVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"OutboundMessageGate 阻断出站消息: {verdict.decision.value} — "
            f"{'; '.join(verdict.reasons)}"
        )


class HITLRequiredError(Exception):
    """出站消息需人工确认 (HITL) 且未获批准, 不得发送。

    由 ``OutboundGuard`` 在 HITL 决策且未配置人工放行时抛出 (fail-closed),
    防止"升级人工"环节被绕过 — 底层 sender 不会被调用。
    """

    def __init__(self, verdict: OutboundVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"OutboundMessageGate 出站消息需人工确认: {verdict.decision.value} — "
            f"{'; '.join(verdict.reasons)}"
        )
