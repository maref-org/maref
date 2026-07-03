"""
AgentReputationRegistry — Agent 信用分注册表

基于 SignedAgentCard + 历史违规计数,为每个 Agent 维护 0-100 的信用分。
信用分 < 30 触发强制 quarantine。

扣分规则 (与 validation-contract.md 第十一节一致):
- CRITICAL 告警: -30 分
- HIGH 告警: -10 分
- MEDIUM 告警: -5 分
- LOW 告警: -1 分
- consent 拒绝 (高权限操作被用户拒绝): -20 分

阈值:
- force_quarantine_threshold = 30 (低于此值强制隔离)
- warning_threshold = 60 (低于此值告警,不隔离)
- initial_score = 100 (新注册 Agent)

所有信用分变更写入 UnifiedAuditStore,带 HMAC 签名,不可篡改 (1.3-A6)。

接口契约:
- 1.3-A5: 初始分 100,每次 CRITICAL -30,HIGH -10,低于 30 触发 quarantine
- 1.3-A6: 信用分变更写入 UnifiedAuditStore,不可篡改
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.sentinel.event import ObservationEvent, Severity


class ReputationChangeReason(str, Enum):
    """信用分变更原因"""

    INITIAL_REGISTER = "initial_register"  # 注册初始分
    CRITICAL_ALERT = "critical_alert"  # CRITICAL 告警扣分
    HIGH_ALERT = "high_alert"  # HIGH 告警扣分
    MEDIUM_ALERT = "medium_alert"  # MEDIUM 告警扣分
    LOW_ALERT = "low_alert"  # LOW 告警扣分
    CONSENT_DENIED = "consent_denied"  # 高权限操作被用户拒绝
    RECOVERY_BONUS = "recovery_bonus"  # 长期无违规的恢复加分
    MANUAL_ADJUST = "manual_adjust"  # 人工调整
    RESET = "reset"  # 重置


# 扣分/加分映射 (与 validation-contract.md 第十一节一致)
_SEVERITY_PENALTY: dict[Severity, int] = {
    Severity.CRITICAL: -30,
    Severity.HIGH: -10,
    Severity.MEDIUM: -5,
    Severity.LOW: -1,
}

# 默认阈值
FORCE_QUARANTINE_THRESHOLD: int = 30
WARNING_THRESHOLD: int = 60
INITIAL_SCORE: int = 100
MIN_SCORE: int = 0
MAX_SCORE: int = 100

# consent 拒绝的扣分
CONSENT_DENIED_PENALTY: int = -20


@dataclass(frozen=True)
class ReputationRecord:
    """信用分变更记录 — 不可变,HMAC 签名

    Attributes:
        record_id: UUID v4
        agent_id: Agent ID
        old_score: 变更前分数
        new_score: 变更后分数
        delta: 分数变化 (正=加分,负=扣分)
        reason: 变更原因
        trigger_event_id: 触发变更的 ObservationEvent.event_id (可选)
        changed_at: 变更时间戳
        hmac_signature: HMAC-SHA256 签名
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    old_score: int = 0
    new_score: int = 0
    delta: int = 0
    reason: ReputationChangeReason = ReputationChangeReason.MANUAL_ADJUST
    trigger_event_id: str = ""
    changed_at: float = field(default_factory=lambda: time.time())
    hmac_signature: str = ""

    def with_hash(self, hmac_key: bytes) -> ReputationRecord:
        """返回带 HMAC 签名的不可变副本"""
        new_sig = compute_reputation_hash(self, hmac_key)
        return ReputationRecord(
            record_id=self.record_id,
            agent_id=self.agent_id,
            old_score=self.old_score,
            new_score=self.new_score,
            delta=self.delta,
            reason=self.reason,
            trigger_event_id=self.trigger_event_id,
            changed_at=self.changed_at,
            hmac_signature=new_sig,
        )

    def verify(self, hmac_key: bytes) -> bool:
        """验证 HMAC 签名 — 任何篡改返回 False"""
        if not self.hmac_signature:
            return False
        expected = compute_reputation_hash(self, hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)


def compute_reputation_hash(record: ReputationRecord, hmac_key: bytes) -> str:
    """计算 ReputationRecord 的 HMAC-SHA256 签名

    payload = f"{record_id}|{agent_id}|{old_score}|{new_score}|{delta}|{reason.value}|{changed_at:.6f}"
    """
    payload = (
        f"{record.record_id}|"
        f"{record.agent_id}|"
        f"{record.old_score}|"
        f"{record.new_score}|"
        f"{record.delta}|"
        f"{record.reason.value}|"
        f"{record.changed_at:.6f}"
    )
    return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class AgentState:
    """Agent 运行时状态 (可变,内部使用)"""

    agent_id: str
    score: int = INITIAL_SCORE
    registered_at: float = field(default_factory=lambda: time.time())
    last_violation_at: float = 0.0
    total_violations: int = 0
    history: list[ReputationRecord] = field(default_factory=list)

    @property
    def is_quarantined(self) -> bool:
        return self.score < FORCE_QUARANTINE_THRESHOLD

    @property
    def is_warning(self) -> bool:
        return WARNING_THRESHOLD > self.score >= FORCE_QUARANTINE_THRESHOLD


class AgentReputationRegistry:
    """Agent 信用分注册表 — 维护 0-100 信用分,低分触发隔离

    Usage:
        registry = AgentReputationRegistry(
            hmac_key=key,
            audit_callback=my_audit_logger,
            quarantine_callback=my_quarantine_proto.quarantine,
        )
        registry.register("agent-claude-code-v1")
        # ... sentinel 检测到 CRITICAL 事件 ...
        record = await registry.apply_event(event, agent_id="agent-claude-code-v1")
        if record.new_score < FORCE_QUARANTINE_THRESHOLD:
            # quarantine_callback 已自动触发
            logger.warning("Agent %s force-quarantined", "agent-claude-code-v1")

    保证:
    - 初始分 100,CRITICAL -30,HIGH -10,MEDIUM -5,LOW -1 (1.3-A5)
    - 信用分 < 30 自动触发 quarantine_callback (1.3-A5)
    - 所有变更写 HMAC 签名的 ReputationRecord 到 audit_callback (1.3-A6)
    - 信用分 clamp 到 [0, 100],不会越界
    """

    def __init__(
        self,
        hmac_key: bytes,
        audit_callback: Any = None,
        quarantine_callback: Any = None,
        force_quarantine_threshold: int = FORCE_QUARANTINE_THRESHOLD,
        warning_threshold: int = WARNING_THRESHOLD,
        initial_score: int = INITIAL_SCORE,
    ) -> None:
        """初始化信用分注册表

        Args:
            hmac_key: HMAC-SHA256 签名密钥
            audit_callback: 审计回调 (ReputationRecord -> None/Awaitable),每次分数变更调用
            quarantine_callback: 隔离回调 (agent_id, reason) -> None/Awaitable,
                当分数 < force_quarantine_threshold 时自动调用
            force_quarantine_threshold: 强制隔离阈值 (默认 30)
            warning_threshold: 告警阈值 (默认 60)
            initial_score: 新注册 Agent 初始分 (默认 100)
        """
        self._hmac_key = hmac_key
        self._audit_callback = audit_callback
        self._quarantine_callback = quarantine_callback
        self._force_quarantine_threshold = force_quarantine_threshold
        self._warning_threshold = warning_threshold
        self._initial_score = initial_score
        self._agents: dict[str, AgentState] = {}

    def register(self, agent_id: str, initial_score: int | None = None) -> ReputationRecord:
        """注册新 Agent,授予初始信用分

        Args:
            agent_id: Agent ID (从 SignedAgentCard.agent_id 解析)
            initial_score: 初始分 (None = 用默认 initial_score)

        Returns:
            注册记录 (reason=INITIAL_REGISTER)

        Raises:
            ValueError: agent_id 已注册
        """
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id} already registered")

        score = self._initial_score if initial_score is None else initial_score
        score = _clamp_score(score)

        record = ReputationRecord(
            agent_id=agent_id,
            old_score=0,
            new_score=score,
            delta=score,
            reason=ReputationChangeReason.INITIAL_REGISTER,
        ).with_hash(self._hmac_key)

        state = AgentState(agent_id=agent_id, score=score)
        state.history.append(record)
        self._agents[agent_id] = state

        # 同步推送审计 (register 是同步方法)
        self._fire_and_forget_audit(record)
        return record

    def score(self, agent_id: str) -> int:
        """获取 Agent 当前信用分

        Returns:
            信用分 (0-100),未注册 Agent 返回 0
        """
        state = self._agents.get(agent_id)
        return state.score if state else 0

    def is_quarantined(self, agent_id: str) -> bool:
        """检查 Agent 是否应被隔离 (信用分 < 阈值)"""
        return self.score(agent_id) < self._force_quarantine_threshold

    def is_warning(self, agent_id: str) -> bool:
        """检查 Agent 是否处于告警区 (阈值间)"""
        s = self.score(agent_id)
        return self._warning_threshold > s >= self._force_quarantine_threshold

    def history(self, agent_id: str) -> list[ReputationRecord]:
        """获取 Agent 的信用分变更历史"""
        state = self._agents.get(agent_id)
        return list(state.history) if state else []

    async def apply_event(
        self,
        event: ObservationEvent,
        agent_id: str,
    ) -> ReputationRecord:
        """应用 ObservationEvent 到 Agent 信用分

        根据 event.severity 扣分:
        - CRITICAL: -30
        - HIGH: -10
        - MEDIUM: -5
        - LOW: -1

        若扣分后分数 < force_quarantine_threshold,自动触发 quarantine_callback。

        Args:
            event: 触发扣分的 ObservationEvent
            agent_id: 被扣分的 Agent ID

        Returns:
            信用分变更记录

        Raises:
            KeyError: agent_id 未注册
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not registered")

        penalty = _SEVERITY_PENALTY.get(event.severity, 0)
        reason_map = {
            Severity.CRITICAL: ReputationChangeReason.CRITICAL_ALERT,
            Severity.HIGH: ReputationChangeReason.HIGH_ALERT,
            Severity.MEDIUM: ReputationChangeReason.MEDIUM_ALERT,
            Severity.LOW: ReputationChangeReason.LOW_ALERT,
        }
        reason = reason_map.get(event.severity, ReputationChangeReason.MANUAL_ADJUST)

        return await self._apply_delta(
            agent_id=agent_id,
            delta=penalty,
            reason=reason,
            trigger_event_id=event.event_id,
        )

    async def apply_consent_denial(
        self,
        agent_id: str,
        operation: str,
    ) -> ReputationRecord:
        """应用 consent 拒绝扣分 (-20)

        当 JustInTimeConsent 拒绝高权限操作时,扣 Agent 信用分 20。

        Args:
            agent_id: 被扣分的 Agent ID
            operation: 被拒绝的操作名

        Returns:
            信用分变更记录
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not registered")

        return await self._apply_delta(
            agent_id=agent_id,
            delta=CONSENT_DENIED_PENALTY,
            reason=ReputationChangeReason.CONSENT_DENIED,
            trigger_event_id=f"consent_denied:{operation}",
        )

    async def apply_recovery_bonus(
        self,
        agent_id: str,
        bonus: int = 5,
    ) -> ReputationRecord:
        """应用恢复加分 (长期无违规的奖励)

        Args:
            agent_id: Agent ID
            bonus: 加分 (默认 +5)

        Returns:
            信用分变更记录
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not registered")

        return await self._apply_delta(
            agent_id=agent_id,
            delta=bonus,
            reason=ReputationChangeReason.RECOVERY_BONUS,
        )

    async def manual_adjust(
        self,
        agent_id: str,
        delta: int,
        note: str = "",
    ) -> ReputationRecord:
        """人工调整信用分

        Args:
            agent_id: Agent ID
            delta: 调整幅度 (正=加分,负=扣分)
            note: 调整备注

        Returns:
            信用分变更记录
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not registered")

        return await self._apply_delta(
            agent_id=agent_id,
            delta=delta,
            reason=ReputationChangeReason.MANUAL_ADJUST,
            trigger_event_id=f"manual:{note}",
        )

    async def reset(self, agent_id: str) -> ReputationRecord:
        """重置 Agent 信用分为初始分

        Args:
            agent_id: Agent ID

        Returns:
            信用分变更记录
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not registered")

        state = self._agents[agent_id]
        old_score = state.score
        new_score = self._initial_score

        record = ReputationRecord(
            agent_id=agent_id,
            old_score=old_score,
            new_score=new_score,
            delta=new_score - old_score,
            reason=ReputationChangeReason.RESET,
        ).with_hash(self._hmac_key)

        state.score = new_score
        state.last_violation_at = 0.0
        state.total_violations = 0
        state.history.append(record)
        await self._emit_audit(record)
        return record

    def list_agents(self) -> list[str]:
        """列出所有已注册 Agent ID"""
        return list(self._agents.keys())

    def snapshot(self) -> dict[str, Any]:
        """返回注册表快照 (调试/健康检查用)"""
        return {
            "agent_count": len(self._agents),
            "force_quarantine_threshold": self._force_quarantine_threshold,
            "warning_threshold": self._warning_threshold,
            "initial_score": self._initial_score,
            "agents": {
                aid: {
                    "score": s.score,
                    "registered_at": s.registered_at,
                    "last_violation_at": s.last_violation_at,
                    "total_violations": s.total_violations,
                    "is_quarantined": s.is_quarantined,
                    "is_warning": s.is_warning,
                    "history_len": len(s.history),
                }
                for aid, s in self._agents.items()
            },
        }

    # ==================== 内部方法 ====================

    async def _apply_delta(
        self,
        agent_id: str,
        delta: int,
        reason: ReputationChangeReason,
        trigger_event_id: str = "",
    ) -> ReputationRecord:
        """应用信用分变更 (内部)"""
        state = self._agents[agent_id]
        old_score = state.score
        new_score = _clamp_score(old_score + delta)
        actual_delta = new_score - old_score

        record = ReputationRecord(
            agent_id=agent_id,
            old_score=old_score,
            new_score=new_score,
            delta=actual_delta,
            reason=reason,
            trigger_event_id=trigger_event_id,
        ).with_hash(self._hmac_key)

        state.score = new_score
        if actual_delta < 0:
            state.last_violation_at = record.changed_at
            state.total_violations += 1
        state.history.append(record)

        await self._emit_audit(record)

        # 检查是否需要触发 quarantine
        if new_score < self._force_quarantine_threshold and self._quarantine_callback:
            try:
                result = self._quarantine_callback(agent_id, reason.value)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # quarantine 回调失败不影响信用分变更
                pass

        return record

    async def _emit_audit(self, record: ReputationRecord) -> None:
        """推送审计记录到 audit_callback (支持同步/异步)"""
        if self._audit_callback is None:
            return
        try:
            result = self._audit_callback(record)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # 审计回调失败不影响信用分变更
            pass

    def _fire_and_forget_audit(self, record: ReputationRecord) -> None:
        """同步上下文中推送审计 (fire-and-forget,异步 callback 安排到事件循环)"""
        if self._audit_callback is None:
            return
        try:
            result = self._audit_callback(record)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    pass
        except Exception:
            pass


def _clamp_score(score: int) -> int:
    """将分数 clamp 到 [MIN_SCORE, MAX_SCORE]"""
    return max(MIN_SCORE, min(MAX_SCORE, score))
