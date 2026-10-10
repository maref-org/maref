"""风险分级显式化（框架 3.0 附件 1 五级 + 附件 2 四维度）。

《人工智能安全治理框架3.0》要求把风险显式分级、让处置流程可追溯：
- 附件1 二/三：安全风险分级五级（低 / 一般 / 较大 / 重大 / 特别重大），
  分级要素含客体类别、影响程度、影响范围、可恢复性；
- 附件2 二.1(2)：智能体动作须按风险级别匹配安全控制措施。

本模块是 ``governance/risk_classifier`` 的**只读适配层**（不改其语义）：
复用其权威分级 ``classify_action_server``（调用方 metadata 只升不降），
映射为框架五级并补齐四维度，产出可审计的 ``GradedRisk``。

设计: docs/plans/2026-10-02-maref-framework-3-0-compliance-mapping-plan.md P2
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maref.governance.risk_classifier import RiskLevel, classify_action_server


# 附件1：风险五级（顺序 = 严重度递增）
class CACRiskGrade(StrEnum):
    LOW = "低"
    GENERAL = "一般"
    LARGE = "较大"
    MAJOR = "重大"
    SPECIAL_MAJOR = "特别重大"


_GRADE_ORDER: dict[CACRiskGrade, int] = {
    CACRiskGrade.LOW: 0,
    CACRiskGrade.GENERAL: 1,
    CACRiskGrade.LARGE: 2,
    CACRiskGrade.MAJOR: 3,
    CACRiskGrade.SPECIAL_MAJOR: 4,
}


# 附件2：四维度分级要素
class RiskDimension(StrEnum):
    OBJECT_CATEGORY = "客体类别"
    IMPACT_SEVERITY = "影响程度"
    IMPACT_SCOPE = "影响范围"
    RECOVERABILITY = "可恢复性"


# 现有四挡 → 框架五级的基础映射（IRREVERSIBLE 的升级分支见 grade_action）
_BASE_GRADE_MAP: dict[RiskLevel, CACRiskGrade] = {
    RiskLevel.LOW: CACRiskGrade.LOW,
    RiskLevel.MEDIUM: CACRiskGrade.GENERAL,
    RiskLevel.HIGH: CACRiskGrade.LARGE,
    RiskLevel.IRREVERSIBLE: CACRiskGrade.MAJOR,
}

# 特别重大触发范围
_SPECIAL_SCOPES = ("global", "cross_org", "production")

# 处置流程（与风险级别绑定的安全控制）
GRADE_FLOW: dict[CACRiskGrade, str] = {
    CACRiskGrade.LOW: "自动放行",
    CACRiskGrade.GENERAL: "记录后放行",
    CACRiskGrade.LARGE: "需人工审批（ApprovalEngine）",
    CACRiskGrade.MAJOR: "强制人工审批 + 审批台账留痕（approval_ledger）",
    CACRiskGrade.SPECIAL_MAJOR: "阻断 + 治理级复核 + 强制人工审批（fail-closed）",
}

# 客体类别规则（按序首命中）
_OBJECT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("销毁性", ("delete", "drop", "destroy", "truncate", "wipe", "purge", "rm_")),
    ("凭据类", ("key", "secret", "credential", "token", "password", "cert", "pem")),
    (
        "发布/外发类",
        ("publish", "release", "deploy", "post", "upload", "send", "email", "transfer", "payment"),
    ),
    ("写入类", ("write", "append", "create", "edit", "modify", "mkdir", "spawn")),
    ("读取类", ("read", "get", "list", "query", "search", "view", "stat")),
)
_OBJECT_DEFAULT = "其他"


@dataclass(frozen=True)
class GradedRisk:
    """框架口径的风险分级结果（五级 + 四维度 + 处置流程）。"""

    action: str
    grade: CACRiskGrade
    dimensions: dict[RiskDimension, str] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    source_level: str = ""

    @property
    def flow(self) -> str:
        return GRADE_FLOW[self.grade]

    def explain(self) -> str:
        """审计可读结论：该操作被定为 X 级、走 Y 流程。"""
        return f"动作 {self.action!r} 定为「{self.grade.value}」级，处置：{self.flow}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "grade": self.grade.value,
            "grade_order": _GRADE_ORDER[self.grade],
            "dimensions": {dim.value: val for dim, val in self.dimensions.items()},
            "reasons": list(self.reasons),
            "source_level": self.source_level,
            "flow": self.flow,
        }


def _object_category(action: str) -> str:
    normalized = action.lower()
    for category, keywords in _OBJECT_RULES:
        if any(kw in normalized for kw in keywords):
            return category
    return _OBJECT_DEFAULT


def grade_action(
    action: str,
    metadata: dict[str, Any] | None = None,
    trusted: dict[str, Any] | None = None,
) -> GradedRisk:
    """把动作分级为框架五级 + 四维度。

    复用 ``classify_action_server``（权威、只升不降），不改其语义；
    在其四挡结果上做确定性映射，并对「不可逆 + 全局/跨组织/生产」升级为特别重大。
    """
    assessment = classify_action_server(action, metadata, trusted)

    grade = _BASE_GRADE_MAP[assessment.risk_level]
    if (
        assessment.risk_level is RiskLevel.IRREVERSIBLE
        and assessment.impact_scope in _SPECIAL_SCOPES
    ):
        grade = CACRiskGrade.SPECIAL_MAJOR

    dimensions: dict[RiskDimension, str] = {
        RiskDimension.OBJECT_CATEGORY: _object_category(action),
        RiskDimension.IMPACT_SEVERITY: assessment.risk_level.value,
        RiskDimension.IMPACT_SCOPE: assessment.impact_scope,
        RiskDimension.RECOVERABILITY: "可恢复" if assessment.reversible else "不可恢复",
    }
    return GradedRisk(
        action=action,
        grade=grade,
        dimensions=dimensions,
        reasons=tuple(assessment.reasons),
        source_level=assessment.risk_level.value,
    )


def exceeds(grade: CACRiskGrade, max_grade: CACRiskGrade) -> bool:
    """grade 是否超过 max_grade（用于阈值比对）。"""
    return _GRADE_ORDER[grade] > _GRADE_ORDER[max_grade]


def _cmd_grade(action: str, scope: str | None, reversible: bool, as_json: bool) -> int:
    metadata: dict[str, Any] = {}
    if scope:
        metadata["impact_scope"] = scope
    if not reversible:
        metadata["reversible"] = False
    result = grade_action(action, metadata)
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.explain())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m maref.compliance.cac.risk_grading",
        description="框架 3.0 风险分级（五级 + 四维度）",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("grade", help="对动作分级")
    p.add_argument("action")
    p.add_argument("--scope", default=None, help="impact_scope，如 global/production")
    p.add_argument("--not-reversible", action="store_true", help="标记不可恢复")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "grade":
        return _cmd_grade(args.action, args.scope, not args.not_reversible, args.json)
    return 2


__all__ = [
    "CACRiskGrade",
    "GRADE_FLOW",
    "GradedRisk",
    "RiskDimension",
    "exceeds",
    "grade_action",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
