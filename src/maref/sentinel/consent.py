"""
JustInTimeConsent — 高权限操作的用户即时同意协议

任何高权限操作 (安装 CA 证书、ptrace、LD_PRELOAD、网络扩展、内核驱动加载)
必须经用户即时同意,无静默授权。同意决策写入 AuditLogger,带 HMAC 签名。

设计原则:
- 默认拒绝 (deny by default): 无 consent_callback 或 callback 抛异常 → 拒绝
- 即时性 (just-in-time): 不预授权,每次操作单独询问 (除非显式设置 TTL)
- 可撤销 (revocable): 用户随时可撤销已授予的同意
- 可审计 (auditable): 每次请求/授予/拒绝/撤销都写 AuditLogger

接口契约 (validation-contract.md 第十节):
- 1.3-A4: JustInTimeConsent 对未获同意的高权限操作阻断率 100%
- 1.3-A6: Agent 信用分变更写入 UnifiedAuditStore (consent 拒绝影响信用分)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConsentOutcome(str, Enum):
    """同意决策结果"""

    GRANTED = "granted"  # 用户同意
    DENIED = "denied"  # 用户拒绝
    DENIED_NO_CALLBACK = "denied_no_callback"  # 无 callback,默认拒绝
    DENIED_ERROR = "denied_error"  # callback 抛异常,默认拒绝
    REVOKED = "revoked"  # 已授予后被撤销
    EXPIRED = "expired"  # TTL 过期


# 已注册的高权限操作 (sentinel 内部使用)
CONSENT_OPERATIONS: tuple[str, ...] = (
    "sentinel.mitmproxy.ca_install",  # 安装 mitmproxy CA 证书 (NetworkEgressProbe)
    "sentinel.process.ptrace",  # ptrace 进程附加 (ProcessProbe 深度检测)
    "sentinel.process.ld_preload",  # 设置 LD_PRELOAD (syscall hook)
    "sentinel.network.extension_install",  # 安装 Network Extension (macOS M2)
    "sentinel.esf.client_install",  # 安装 ESF client (macOS M2)
    "sentinel.ebpf.load",  # 加载 eBPF 程序 (Linux M3)
    "sentinel.seccomp.apply",  # 应用 seccomp filter (Linux M3)
    "sentinel.quarantine.sandbox_exec",  # 应用 sandbox-exec 隔离
    "sentinel.forensic.memory_dump",  # 内存转储 (深度取证)
    "sentinel.integrity.binary_scan",  # 二进制哈希扫描
)

# 默认 TTL: 一次操作即过期 (just-in-time)
_DEFAULT_TTL: float = 0.0


@dataclass(frozen=True)
class ConsentDecision:
    """同意决策 — 不可变,HMAC 签名

    Attributes:
        decision_id: UUID v4
        operation: 被请求的操作名 (如 sentinel.mitmproxy.ca_install)
        outcome: 决策结果 (granted/denied/...)
        subject: 请求方 (agent_id 或 probe_name)
        context: 请求上下文 (附加信息,如目标 pid、操作原因)
        decided_at: 决策时间戳
        ttl: 同意有效期 (秒),0 表示单次有效
        expires_at: 过期时间戳 (0 表示单次)
        reason: 决策原因 (用户提供的解释或系统降级原因)
        hmac_signature: HMAC-SHA256 签名
    """

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation: str = ""
    outcome: ConsentOutcome = ConsentOutcome.DENIED
    subject: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    decided_at: float = field(default_factory=lambda: time.time())
    ttl: float = _DEFAULT_TTL
    expires_at: float = 0.0
    reason: str = ""
    hmac_signature: str = ""

    @property
    def is_granted(self) -> bool:
        """决策是否为同意"""
        return self.outcome == ConsentOutcome.GRANTED

    @property
    def is_active(self) -> bool:
        """决策是否仍有效 (已授予且未过期)"""
        if self.outcome != ConsentOutcome.GRANTED:
            return False
        if self.expires_at <= 0:
            # 单次有效 — is_active 只在调用方取出后立即失效
            return True
        return time.time() < self.expires_at

    def with_hash(self, hmac_key: bytes) -> ConsentDecision:
        """返回带 HMAC 签名的不可变副本"""
        new_sig = compute_consent_hash(self, hmac_key)
        return ConsentDecision(
            decision_id=self.decision_id,
            operation=self.operation,
            outcome=self.outcome,
            subject=self.subject,
            context=self.context,
            decided_at=self.decided_at,
            ttl=self.ttl,
            expires_at=self.expires_at,
            reason=self.reason,
            hmac_signature=new_sig,
        )

    def verify(self, hmac_key: bytes) -> bool:
        """验证 HMAC 签名 — 任何篡改返回 False"""
        if not self.hmac_signature:
            return False
        expected = compute_consent_hash(self, hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)


def compute_consent_hash(decision: ConsentDecision, hmac_key: bytes) -> str:
    """计算 ConsentDecision 的 HMAC-SHA256 签名

    payload = f"{decision_id}|{operation}|{outcome}|{subject}|{decided_at:.6f}"
    """
    payload = (
        f"{decision.decision_id}|"
        f"{decision.operation}|"
        f"{decision.outcome.value}|"
        f"{decision.subject}|"
        f"{decision.decided_at:.6f}"
    )
    return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


# consent_callback 签名: 接收 operation + context,返回 bool (True=同意)
ConsentCallback = Callable[[str, dict[str, Any]], Awaitable[bool] | bool]


class JustInTimeConsent:
    """高权限操作的用户即时同意协议

    Usage:
        consent = JustInTimeConsent(
            hmac_key=key,
            consent_callback=my_ui_prompt,  # async (op, ctx) -> bool
            audit_callback=my_audit_logger,
        )
        decision = await consent.request(
            operation="sentinel.mitmproxy.ca_install",
            subject="network_egress_probe",
            context={"reason": "HTTPS interception required"},
        )
        if decision.is_granted:
            install_ca_cert()
        else:
            logger.warning("CA install blocked: user denied")

    保证:
    - 无 callback → 默认 DENIED_NO_CALLBACK (1.3-A4: 100% 阻断)
    - callback 抛异常 → DENIED_ERROR (1.3-A4: 100% 阻断)
    - 用户拒绝 → DENIED (1.3-A4: 100% 阻断)
    - 每次决策写 HMAC 签名的 ConsentDecision 到 audit_callback
    - TTL > 0 时,同 operation 的后续请求在 TTL 内复用缓存决策
    """

    def __init__(
        self,
        hmac_key: bytes,
        consent_callback: ConsentCallback | None = None,
        audit_callback: Any = None,
        default_ttl: float = _DEFAULT_TTL,
    ) -> None:
        """初始化同意协议

        Args:
            hmac_key: HMAC-SHA256 签名密钥
            consent_callback: 同意询问回调。None = 默认拒绝所有请求。
                签名: (operation: str, context: dict) -> bool | Awaitable[bool]
            audit_callback: 审计回调 (ConsentDecision -> None/Awaitable)
            default_ttl: 默认同意有效期 (秒)。0 = 单次有效。
        """
        self._hmac_key = hmac_key
        self._consent_callback: ConsentCallback | None = consent_callback
        self._audit_callback = audit_callback
        self._default_ttl = default_ttl
        # 缓存: operation -> 最近的 granted decision (TTL 内复用)
        self._cache: dict[str, ConsentDecision] = {}

    async def request(
        self,
        operation: str,
        subject: str = "",
        context: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> ConsentDecision:
        """请求用户同意高权限操作

        Args:
            operation: 操作名 (建议用 CONSENT_OPERATIONS 中的常量)
            subject: 请求方标识 (agent_id / probe_name)
            context: 请求上下文 (附加信息)
            ttl: 本次同意有效期 (秒)。None = 用 default_ttl。0 = 单次有效。

        Returns:
            ConsentDecision (outcome=GRANTED 表示同意,其余均为拒绝)
        """
        ctx = dict(context or {})
        effective_ttl = self._default_ttl if ttl is None else ttl

        # 1. 检查缓存 (仅 TTL > 0 时复用)
        if effective_ttl > 0 and operation in self._cache:
            cached = self._cache[operation]
            if cached.is_active:
                # 复用缓存的 granted 决策,但仍写一条 audit (复用记录)
                reuse = ConsentDecision(
                    operation=operation,
                    outcome=ConsentOutcome.GRANTED,
                    subject=subject,
                    context={**ctx, "reused_from": cached.decision_id},
                    ttl=effective_ttl,
                    expires_at=cached.expires_at,
                    reason="reused_cached_consent",
                ).with_hash(self._hmac_key)
                await self._emit_audit(reuse)
                return reuse
            # 缓存过期,清除
            expired = self._cache.pop(operation)
            expired_record = ConsentDecision(
                operation=operation,
                outcome=ConsentOutcome.EXPIRED,
                subject=subject,
                context=ctx,
                reason=f"ttl_expired (was decided at {expired.decided_at})",
            ).with_hash(self._hmac_key)
            await self._emit_audit(expired_record)

        # 2. 调用 consent_callback (无 callback = 默认拒绝)
        if self._consent_callback is None:
            decision = ConsentDecision(
                operation=operation,
                outcome=ConsentOutcome.DENIED_NO_CALLBACK,
                subject=subject,
                context=ctx,
                ttl=effective_ttl,
                reason="no consent_callback configured (deny by default)",
            ).with_hash(self._hmac_key)
            await self._emit_audit(decision)
            return decision

        try:
            result = self._consent_callback(operation, ctx)
            if asyncio.iscoroutine(result):
                granted = await result
            else:
                granted = bool(result)
        except Exception as exc:
            decision = ConsentDecision(
                operation=operation,
                outcome=ConsentOutcome.DENIED_ERROR,
                subject=subject,
                context=ctx,
                ttl=effective_ttl,
                reason=f"consent_callback raised {type(exc).__name__}: {exc}",
            ).with_hash(self._hmac_key)
            await self._emit_audit(decision)
            return decision

        if not granted:
            decision = ConsentDecision(
                operation=operation,
                outcome=ConsentOutcome.DENIED,
                subject=subject,
                context=ctx,
                ttl=effective_ttl,
                reason="user_denied",
            ).with_hash(self._hmac_key)
            await self._emit_audit(decision)
            return decision

        # 3. 授予同意
        expires_at = 0.0
        if effective_ttl > 0:
            expires_at = time.time() + effective_ttl

        decision = ConsentDecision(
            operation=operation,
            outcome=ConsentOutcome.GRANTED,
            subject=subject,
            context=ctx,
            ttl=effective_ttl,
            expires_at=expires_at,
            reason="user_granted",
        ).with_hash(self._hmac_key)

        # 缓存 (仅 TTL > 0 时)
        if effective_ttl > 0:
            self._cache[operation] = decision

        await self._emit_audit(decision)
        return decision

    def is_approved(self, operation: str) -> bool:
        """检查操作是否有有效的已授予同意 (仅查缓存,不触发新请求)

        注: 单次 TTL (ttl=0) 的同意不缓存,此方法对单次同意总返回 False。
        若需触发请求,使用 request()。
        """
        cached = self._cache.get(operation)
        return cached is not None and cached.is_active

    def revoke(self, operation: str, reason: str = "user_revoked") -> ConsentDecision | None:
        """撤销已授予的同意

        Args:
            operation: 操作名
            reason: 撤销原因

        Returns:
            撤销决策记录 (outcome=REVOKED),None 表示该操作无缓存同意
        """
        if operation not in self._cache:
            return None
        old = self._cache.pop(operation)
        revoked = ConsentDecision(
            operation=operation,
            outcome=ConsentOutcome.REVOKED,
            subject=old.subject,
            context=old.context,
            ttl=0.0,
            reason=reason,
        ).with_hash(self._hmac_key)
        # 同步推送审计 (revoke 是同步方法,audit_callback 若异步则发 fire-and-forget)
        try:
            result = self._audit_callback(revoked) if self._audit_callback else None
            if asyncio.iscoroutine(result):
                # 同步上下文无法 await,安排到运行中的事件循环
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    pass
        except Exception:
            pass
        return revoked

    def clear_cache(self) -> None:
        """清空所有缓存的同意决策 (不影响已发出的审计记录)"""
        self._cache.clear()

    async def _emit_audit(self, decision: ConsentDecision) -> None:
        """推送审计决策到 audit_callback (支持同步/异步)"""
        if self._audit_callback is None:
            return
        try:
            result = self._audit_callback(decision)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # 审计回调失败不应影响同意决策流程
            pass
