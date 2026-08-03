"""TrustBoundaryManager — 单 Agent 权限边界强制实施层（v0.44.0 S1）。

把「决策分级授权」从"预检建议"升级为"执行时强制门禁"：
- 每个动作执行前必须经过边界校验（风险分级 ≤ 授权范围 + 目标域白名单）
- 越界动作抛 ``E1006``（BOUNDARY_VIOLATION）并写审计日志
- 未配置授权范围时按 fail-closed 处理（HIGH/IRREVERSIBLE 一律拒绝）

对接现有能力：
- :func:`~maref.governance.risk_classifier.classify_action` — 风险分级
- :class:`~maref.identity.credential.AuthorizationScope` — 授权范围证书
- :class:`~maref.exceptions.MAREFError` — E1006 错误模型
- :class:`~maref.governance.audit.AuditLogger` / ``audit_bus`` — 审计记录

设计依据: docs/plans/2026-08-03-v0.44.0-iteration-plan.md §2.1 S1
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.exceptions import ErrorCode, MAREFError
from maref.governance.risk_classifier import RiskAssessment, RiskLevel, classify_action
from maref.identity.credential import AuthorizationScope

_DEFAULT_ALLOWED_DOMAINS: set[str] = {"local", "filesystem", "readonly"}


@dataclass
class BoundaryDecision:
    """一次边界校验的裁决结果。"""

    action: str
    agent_id: str
    allowed: bool
    reason: str
    assessment: RiskAssessment
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "agent_id": self.agent_id,
            "allowed": self.allowed,
            "reason": self.reason,
            "risk_level": self.assessment.risk_level.value,
            "checked_at": self.checked_at,
        }


class BoundaryViolationError(MAREFError):
    """越界动作被边界管理器阻断。"""

    def __init__(
        self,
        action: str,
        agent_id: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.BOUNDARY_VIOLATION,
            message=(
                f"TrustBoundary 阻断越界动作: agent={agent_id} action={action} "
                f"reason={reason}"
            ),
            details={"action": action, "agent_id": agent_id, "reason": reason, **(details or {})},
        )


class TrustBoundaryManager:
    """单 Agent 权限边界的强制实施层。

    用法::

        boundary = TrustBoundaryManager(scope=my_scope, audit_logger=logger)
        boundary.check("file.delete", agent_id="agent-01")  # 越界则抛 E1006

    Attributes:
        allowed_domains: 允许访问的目标域集合（目标文件/服务白名单）。
        fail_closed: True 时未提供授权范围即拒绝 HIGH/IRREVERSIBLE。
    """

    def __init__(
        self,
        scope: AuthorizationScope | None = None,
        audit_logger: Any | None = None,
        allowed_domains: set[str] | None = None,
        fail_closed: bool = True,
    ) -> None:
        self.scope = scope
        self._audit_logger = audit_logger
        self.allowed_domains = set(allowed_domains or _DEFAULT_ALLOWED_DOMAINS)
        self.fail_closed = fail_closed
        self._decisions: list[BoundaryDecision] = []

    # -- 主入口 --

    def check(
        self,
        action: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> BoundaryDecision:
        """校验动作是否在权限边界内。

        Args:
            action: 动作标识（如 ``file.delete``、``payment:transfer``）。
            agent_id: 执行主体。
            metadata: 风险分级上下文（impact_scope/reversible 等）。

        Returns:
            通过时返回 allowed=True 的 BoundaryDecision。

        Raises:
            BoundaryViolationError: 动作越界时抛出 E1006。
        """
        decision = self._evaluate(action, agent_id, metadata)
        self._decisions.append(decision)
        self._record_audit(decision)
        if not decision.allowed:
            raise BoundaryViolationError(
                action=action,
                agent_id=agent_id,
                reason=decision.reason,
                details=decision.to_dict(),
            )
        return decision

    def check_no_raise(
        self,
        action: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> BoundaryDecision:
        """校验动作边界，不抛异常，返回裁决结果。

        适用于需要软判定（如预检/打分）的场景。
        """
        decision = self._evaluate(action, agent_id, metadata)
        self._decisions.append(decision)
        self._record_audit(decision)
        return decision

    # -- 内部 --

    def _evaluate(
        self,
        action: str,
        agent_id: str,
        metadata: dict[str, Any] | None,
    ) -> BoundaryDecision:
        assessment = classify_action(action, metadata)

        # 目标域白名单校验：跨域访问未授权 → 阻断。
        impact_scope = assessment.impact_scope
        if impact_scope not in self.allowed_domains:
            return BoundaryDecision(
                action=action,
                agent_id=agent_id,
                allowed=False,
                reason=f"impact_scope '{impact_scope}' 不在允许域 {sorted(self.allowed_domains)} 内",
                assessment=assessment,
            )

        # LOW/MEDIUM 自动放行（无论是否有 scope）。
        if assessment.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):
            return BoundaryDecision(
                action=action,
                agent_id=agent_id,
                allowed=True,
                reason=f"风险等级 {assessment.risk_level.value} 自动放行",
                assessment=assessment,
            )

        # HIGH/IRREVERSIBLE 必须显式授权。
        if self.scope is None:
            if self.fail_closed:
                return BoundaryDecision(
                    action=action,
                    agent_id=agent_id,
                    allowed=False,
                    reason=(
                        f"风险等级 {assessment.risk_level.value} 需要授权范围证书，"
                        "未配置（fail-closed）"
                    ),
                    assessment=assessment,
                )
            return BoundaryDecision(
                action=action,
                agent_id=agent_id,
                allowed=True,
                reason="无授权范围但 fail_closed=False — 放行（不推荐）",
                assessment=assessment,
            )

        if self.scope.is_expired():
            return BoundaryDecision(
                action=action,
                agent_id=agent_id,
                allowed=False,
                reason="授权范围证书已过期",
                assessment=assessment,
            )

        if not self.scope.allows_action(action, assessment.risk_level.value):
            return BoundaryDecision(
                action=action,
                agent_id=agent_id,
                allowed=False,
                reason=(
                    f"动作超出授权范围（max_risk_level={self.scope.max_risk_level}）"
                ),
                assessment=assessment,
            )

        return BoundaryDecision(
            action=action,
            agent_id=agent_id,
            allowed=True,
            reason=f"风险等级 {assessment.risk_level.value} 授权范围内放行",
            assessment=assessment,
        )

    def _record_audit(self, decision: BoundaryDecision) -> None:
        if self._audit_logger is None:
            return
        entry = {
            "event_type": "trust_boundary_check",
            "outcome": "allowed" if decision.allowed else "blocked",
            "action": decision.action,
            "agent_id": decision.agent_id,
            "risk_level": decision.assessment.risk_level.value,
            "reason": decision.reason,
            "timestamp": decision.checked_at,
        }
        try:
            if hasattr(self._audit_logger, "append"):
                self._audit_logger.append(entry)
            elif hasattr(self._audit_logger, "log"):
                self._audit_logger.log(entry)
        except Exception:
            # 审计失败不应阻断动作执行；由上层审计完整性检查兜底。
            pass

    # -- 查询 --

    @property
    def decisions(self) -> list[BoundaryDecision]:
        return list(self._decisions)

    def recent_decisions(self, limit: int = 50) -> list[BoundaryDecision]:
        return list(self._decisions[-limit:])

    def blocked_count(self) -> int:
        return sum(1 for d in self._decisions if not d.allowed)


__all__ = ["BoundaryDecision", "BoundaryViolationError", "TrustBoundaryManager"]
