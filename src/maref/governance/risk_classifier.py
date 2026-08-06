"""决策分级授权 — 动作风险分级（方案 D M1）。

按动作的可逆性、影响面、涉及主体（资金/生死/外部发布/跨组织）将动作
分级为 LOW / MEDIUM / HIGH / IRREVERSIBLE。分级结果供 task_preflight
与 AuthorizationScope 校验使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """动作风险分级。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    IRREVERSIBLE = "IRREVERSIBLE"


# 敏感主体关键词：命中任一即触发更高风险分级（词表可后续扩充）。
_SENSITIVE_TERMS: tuple[str, ...] = (
    "payment",
    "transfer",
    "withdraw",
    "refund",
    "fund",
    "medical",
    "health",
    "life",
    "mortality",
    "external_publish",
    "release",
    "deploy",
    "production",
    "cross_org",
    "federation",
    "delete",
    "drop",
    "destroy",
    "revoke",
    "terminate",
    "force",
)

# 不可逆动作前缀：命中即 IRREVERSIBLE。
_IRREVERSIBLE_PREFIXES: tuple[str, ...] = (
    "delete:",
    "drop:",
    "destroy:",
    "revoke:",
    "terminate:",
    "force:",
    "publish:",
    "release:",
    "deploy:",
    "transfer:",
    "withdraw:",
    "payment:",
)


@dataclass
class RiskAssessment:
    """一次动作的风险分级结果。"""

    action: str
    risk_level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    reversible: bool = True
    impact_scope: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "risk_level": self.risk_level.value,
            "reasons": list(self.reasons),
            "reversible": self.reversible,
            "impact_scope": self.impact_scope,
        }


def _classify_action_floor(action: str) -> RiskAssessment:
    """按动作字符串本身推导不可降级风险下限（v0.52 M2-C3a）。

    强制 ``impact_scope=local`` / ``reversible=True`` 的悲观基线，
    使分级只反映动作字符串固有的风险信号（不可逆前缀、敏感主体、
    中等写操作），屏蔽调用方自报 metadata 的降级意图。
    """
    return classify_action(action, {"impact_scope": "local", "reversible": True})


def classify_action_server(
    action: str,
    metadata: dict[str, Any] | None = None,
    trusted: dict[str, Any] | None = None,
) -> RiskAssessment:
    """服务端权威分级 — 调用方 metadata 只能升级、不能降级（v0.52 M2-C3a）。

    设计背景：:func:`classify_action` 直接信任调用方自报的
    ``impact_scope`` / ``reversible``，攻击者可宣称 local/reversible 把
    高风险动作降级。本函数引入「动作字符串推导的风险下限」：
    metadata（不可信）与 trusted（服务端注入的可信上下文）仅在
    不降低下限的前提下生效。

    Args:
        action: 动作标识。
        metadata: 调用方自报上下文（视为不可信，仅可升级风险）。
        trusted: 服务端注入的可信上下文（如网关探测到的跨域标志）。

    Returns:
        RiskAssessment：风险不低于动作字符串推导的下限。
    """
    metadata = metadata or {}
    trusted = trusted or {}
    floor = _classify_action_floor(action)

    candidate_metadata = dict(metadata)
    candidate_metadata.update(trusted)
    candidate = classify_action(action, candidate_metadata)

    if _RISK_ORDER[candidate.risk_level] >= _RISK_ORDER[floor.risk_level]:
        return candidate
    return floor


def classify_action(action: str, metadata: dict[str, Any] | None = None) -> RiskAssessment:
    """对动作进行风险分级。

    Args:
        action: 动作标识，形如 ``file.read``、``payment:transfer``。
        metadata: 可选上下文（影响面、涉及主体等）。

    Returns:
        RiskAssessment：分级结果与分级依据。
    """
    metadata = metadata or {}
    normalized = action.lower()
    reasons: list[str] = []
    impact_scope = str(metadata.get("impact_scope", "local"))
    reversible = bool(metadata.get("reversible", True))

    for prefix in _IRREVERSIBLE_PREFIXES:
        if normalized.startswith(prefix):
            reasons.append(f"irreversible action prefix: {prefix}")
            return RiskAssessment(
                action=action,
                risk_level=RiskLevel.IRREVERSIBLE,
                reasons=reasons,
                reversible=False,
                impact_scope=impact_scope,
            )

    if impact_scope in ("global", "cross_org", "production"):
        reasons.append(f"global/cross-org/production impact: {impact_scope}")
        return RiskAssessment(
            action=action,
            risk_level=RiskLevel.HIGH,
            reasons=reasons,
            reversible=reversible,
            impact_scope=impact_scope,
        )

    if not reversible:
        reasons.append("flagged non-reversible")
        return RiskAssessment(
            action=action,
            risk_level=RiskLevel.HIGH,
            reasons=reasons,
            reversible=False,
            impact_scope=impact_scope,
        )

    hit_terms = [t for t in _SENSITIVE_TERMS if t in normalized]
    if hit_terms:
        reasons.append(f"sensitive subject terms: {', '.join(hit_terms)}")
        return RiskAssessment(
            action=action,
            risk_level=RiskLevel.HIGH,
            reasons=reasons,
            reversible=reversible,
            impact_scope=impact_scope,
        )

    if action.startswith(("file.write", "file.append", "process.spawn", "network.send")):
        reasons.append("moderate write/spawn/net effect")
        return RiskAssessment(
            action=action,
            risk_level=RiskLevel.MEDIUM,
            reasons=reasons,
            reversible=reversible,
            impact_scope=impact_scope,
        )

    return RiskAssessment(
        action=action,
        risk_level=RiskLevel.LOW,
        reasons=["low-risk read-only action"],
        reversible=reversible,
        impact_scope=impact_scope,
    )


_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.IRREVERSIBLE: 3,
}


def risk_exceeds(level: RiskLevel, max_level: RiskLevel) -> bool:
    """判断 ``level`` 是否超出 ``max_level`` 的授权上限。"""
    return _RISK_ORDER[level] > _RISK_ORDER[max_level]
