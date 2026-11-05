"""ConversationalInboundGate — 跨轮拼接检测。

问题 (Lexsi 多轮审计实测): cross_turn_assembly 类攻击把有害请求拆到多轮,
单轮看都无害, 拼起来才是完整请求。单轮门禁对这类攻击拦截率为 0。

做法:
1. 每轮先跑单轮门禁 (InboundNormalizationGate)
2. 再把最近 window 轮的文本拼接后重跑一次门禁
3. 拼接后若命中 deny -> 升级为 DENY (标记 cross_turn)
4. 窗口有界, 可 reset; 不跨会话泄漏

边界:
- 只对文本型攻击有效; 语义型分片 (m21 "that verb") 仍检测不到
- 窗口越大误报面越大, 默认 6 轮
"""

from __future__ import annotations

from collections import deque

from maref.security.inbound.gate import (
    InboundDecision,
    InboundNormalizationGate,
    InboundVerdict,
)

_SEP = "\n"


class ConversationalInboundGate:
    """带短期记忆的入站门禁 (跨轮拼接)。

    Args:
        gate: 底层单轮门禁; 默认新建一个。
        window: 保留最近多少轮参与拼接。
    """

    def __init__(self, gate: InboundNormalizationGate | None = None, *, window: int = 6) -> None:
        self.gate = gate or InboundNormalizationGate()
        self.window = max(2, int(window))
        self._turns: deque[str] = deque(maxlen=self.window)
        self._turns_since_deny = 0

    def reset(self) -> None:
        self._turns.clear()
        self._turns_since_deny = 0

    @property
    def turns_seen(self) -> int:
        return len(self._turns)

    def check_turn(self, text: str) -> InboundVerdict:
        """检查一轮输入。单轮命中直接返回; 否则看拼接是否命中。"""
        single = self.gate.check(text)
        if single.decision is InboundDecision.DENY:
            self.reset()
            return single

        self._turns.append(text)
        if len(self._turns) < 2:
            return single

        combined = _SEP.join(self._turns)
        joint = self.gate.check(combined)
        if joint.decision is InboundDecision.DENY:
            self.reset()
            return InboundVerdict(
                decision=InboundDecision.DENY,
                original=text,
                normalized=joint.normalized,
                methods=joint.methods,
                matched=joint.matched,
                reason=f"cross-turn assembly ({len(self._turns)} turns): {joint.reason}",
                elapsed_ms=joint.elapsed_ms,
                input_digest=joint.input_digest,
            )
        return single


__all__ = ["ConversationalInboundGate"]
