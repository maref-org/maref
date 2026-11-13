"""authorization_level.py — 交易授权分级（GB/Z 185.9 表4 对齐）。

《人工智能 智能体互联 第9部分：智能体交易》7.2.1 将授权分为三级，
并要求"风险评价为高风险的交易应采用 L1 级"：

    L1  每次交易需智能体委托方确认        实时通知、明确同意
    L2  预先授权一定范围和有效期          授权范围明确、有效期限制
    L3  预先配置规则，自动执行            条件约束、限额控制

本模块只做三件事：把级别与风险档映射成枚举、校验"该级别是否满足该风险"、
把级别与凭证标识整理成审计字段。不涉及业务决策本身。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthorizationLevel(str, Enum):
    """授权级别，取值与标准表4 一致。"""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class RiskLevel(str, Enum):
    """交易风险档，由业务应用方按自身管理规则评定。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: 高风险必须 L1；中风险允许 L2 及更严；低风险允许 L3 及更严。
_MIN_LEVEL_FOR_RISK: dict[RiskLevel, AuthorizationLevel] = {
    RiskLevel.HIGH: AuthorizationLevel.L1,
    RiskLevel.MEDIUM: AuthorizationLevel.L2,
    RiskLevel.LOW: AuthorizationLevel.L3,
}

#: 严格度排序，数值越小越严格。
_STRICTNESS: dict[AuthorizationLevel, int] = {
    AuthorizationLevel.L1: 1,
    AuthorizationLevel.L2: 2,
    AuthorizationLevel.L3: 3,
}

_DESCRIPTION: dict[AuthorizationLevel, str] = {
    AuthorizationLevel.L1: "每次交易需智能体委托方确认；实时通知、明确同意",
    AuthorizationLevel.L2: "预先授权一定范围和有效期；授权范围明确、有效期限制",
    AuthorizationLevel.L3: "预先配置规则，自动执行；条件约束、限额控制",
}


@dataclass(frozen=True)
class AuthorizationCheck:
    """一次授权级别合规性判定。"""

    level: AuthorizationLevel
    risk: RiskLevel
    satisfied: bool
    reason: str


def coerce_level(value: str | AuthorizationLevel) -> AuthorizationLevel:
    """把 "l1"/"L1"/"1" 之类的输入规范成枚举；未知值 fail-closed 抛错。"""
    if isinstance(value, AuthorizationLevel):
        return value
    raw = str(value).strip().upper()
    if raw.startswith("L"):
        raw = raw[1:]
    if raw in ("1", "2", "3"):
        return AuthorizationLevel(f"L{raw}")
    raise ValueError(f"未知授权级别：{value!r}，应为 L1/L2/L3")


def coerce_risk(value: str | RiskLevel) -> RiskLevel:
    """把 high/medium/low 规范成枚举；未知值 fail-closed 抛错。"""
    if isinstance(value, RiskLevel):
        return value
    try:
        return RiskLevel(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"未知风险档：{value!r}，应为 high/medium/low") from exc


def required_level(risk: str | RiskLevel) -> AuthorizationLevel:
    """该风险档要求的最宽授权级别（高风险 → L1）。"""
    return _MIN_LEVEL_FOR_RISK[coerce_risk(risk)]


def check(level: str | AuthorizationLevel, risk: str | RiskLevel) -> AuthorizationCheck:
    """校验授权级别是否满足风险要求。

    级别严格度高于或等于要求即通过（例如高风险下 L1 通过，L3 不通过）。
    """
    lv = coerce_level(level)
    rk = coerce_risk(risk)
    need = _MIN_LEVEL_FOR_RISK[rk]
    ok = _STRICTNESS[lv] <= _STRICTNESS[need]
    if ok:
        reason = f"{rk.value} 风险要求 {need.value}，实际 {lv.value}，满足"
    else:
        reason = f"{rk.value} 风险要求 {need.value}，实际 {lv.value}，不满足"
    return AuthorizationCheck(level=lv, risk=rk, satisfied=ok, reason=reason)


def describe(level: str | AuthorizationLevel) -> str:
    """返回标准表4 对该级别的表述（直接用于意见/报告引用）。"""
    return _DESCRIPTION[coerce_level(level)]


def audit_fields(
    level: str | AuthorizationLevel,
    risk: str | RiskLevel,
    credential_id: str = "",
    subject: str = "",
) -> dict[str, str]:
    """整理成审计记录字段（与 GB/Z 185.8 表7 的可选属性对齐）。

    返回值可直接作为 ``AuditLogger.log(..., **{"primary_subject": ...})`` 的
    键值来源，也可写入 metadata。
    """
    lv = coerce_level(level)
    rk = coerce_risk(risk)
    fields = {
        "authorization_level": lv.value,
        "risk_level": rk.value,
        "authorization_satisfied": "true" if check(lv, rk).satisfied else "false",
    }
    if credential_id:
        fields["authorization_credential_id"] = credential_id
    if subject:
        fields["primary_subject"] = subject
    return fields


__all__ = [
    "AuthorizationLevel",
    "RiskLevel",
    "AuthorizationCheck",
    "audit_fields",
    "check",
    "coerce_level",
    "coerce_risk",
    "describe",
    "required_level",
]
