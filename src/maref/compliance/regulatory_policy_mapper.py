"""RegulatoryPolicyMapper — 策略→辖区强制级别映射（v0.45.0 方案 G G2）。

核心职责：把「动作风险分级 × 辖区监管画像」转换为处置策略
（OBSERVE / ADVISORY / ENFORCE），并让 ENFORCE 级动作接入
现有 TrustBoundary 强制校验，形成「策略-执行-证明」闭环。

设计依据: docs/plans/2026-08-03-v0.45.0-iteration-plan.md §2.2 G2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.compliance.jurisdiction_profile import (
    EnforcementLevel,
    JurisdictionProfile,
    get_profile,
)
from maref.governance.risk_classifier import RiskAssessment, RiskLevel, classify_action


@dataclass
class PolicyDecision:
    """一次动作的辖区合规处置决策。"""

    action: str
    jurisdiction: str
    enforcement: EnforcementLevel
    risk_level: RiskLevel
    reasons: list[str]
    basis_regulations: list[str]

    @property
    def blocked(self) -> bool:
        """ENFORCE 级动作需要强制校验（可被 TrustBoundary 阻断）。"""
        return self.enforcement == EnforcementLevel.ENFORCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "jurisdiction": self.jurisdiction,
            "enforcement": self.enforcement.value,
            "risk_level": self.risk_level.value,
            "reasons": list(self.reasons),
            "basis_regulations": list(self.basis_regulations),
            "blocked": self.blocked,
        }


class RegulatoryPolicyMapper:
    """监管适配层策略映射器。

    Usage::

        mapper = RegulatoryPolicyMapper()
        decision = mapper.map_action("payment:transfer", jurisdiction="eu")
        # decision.enforcement == ENFORCE（EU AI Act 高风险）
        # decision.blocked == True → 进入 TrustBoundary 强制校验
    """

    def __init__(self) -> None:
        self._profiles = get_profile  # 函数引用，便于外部替换/测试

    def map_action(
        self,
        action: str,
        jurisdiction: str,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """把动作映射到目标辖区的处置策略。

        Args:
            action: 动作标识（如 ``file.delete``、``payment:transfer``）。
            jurisdiction: 目标辖区代码（cn / eu / global_south / 自定义）。
            metadata: 风险分级上下文（impact_scope/reversible 等）。

        Returns:
            PolicyDecision 含强制级别、风险等级、依据法规。
        """
        profile = self._profiles(jurisdiction)
        assessment = classify_action(action, metadata)
        enforcement = profile.enforcement_for_risk(assessment.risk_level)

        basis = [
            r.regulation_id for r in profile.regulations
            if self._regulation_applies(profile, r.regulation_id, assessment)
        ]

        reasons = self._build_reasons(profile, assessment, enforcement)

        return PolicyDecision(
            action=action,
            jurisdiction=profile.code,
            enforcement=enforcement,
            risk_level=assessment.risk_level,
            reasons=reasons,
            basis_regulations=basis,
        )

    @staticmethod
    def _regulation_applies(
        profile: JurisdictionProfile,
        regulation_id: str,
        assessment: RiskAssessment,
    ) -> bool:
        """判断某法规是否约束给定风险动作。"""
        # 高风险/不可逆动作触发所有 AI 治理类法规；低风险仅数据类法规参考。
        if assessment.risk_level in (RiskLevel.HIGH, RiskLevel.IRREVERSIBLE):
            return True
        # 中低风险动作：仅当 profile 强制该级别时才引用法规（避免过度引用）。
        enforcement = profile.enforcement_for_risk(assessment.risk_level)
        return enforcement != EnforcementLevel.OBSERVE

    @staticmethod
    def _build_reasons(
        profile: JurisdictionProfile,
        assessment: RiskAssessment,
        enforcement: EnforcementLevel,
    ) -> list[str]:
        reasons = list(assessment.reasons)
        if enforcement == EnforcementLevel.ENFORCE:
            reasons.append(
                f"辖区 {profile.code} 对该风险级别动作实施强制监管"
            )
            if profile.human_oversight_for_high_risk:
                reasons.append("高风险动作要求人工监督（human oversight）")
        elif enforcement == EnforcementLevel.ADVISORY:
            reasons.append(f"辖区 {profile.code} 建议审慎执行（advisory）")
        else:
            reasons.append(f"辖区 {profile.code} 仅记录不干预（observe）")
        return reasons

    def build_credential_mapping(
        self,
        actions: list[str],
        jurisdiction: str,
    ) -> dict[str, Any]:
        """为治理凭证构建按辖区的合规映射（v0.45.0 方案 G G3）。

        遍历凭证 scope 中的动作，逐动作映射到目标辖区的强制级别与
        依据法规，形成对监管的"证明输出"。

        Args:
            actions: 凭证声称覆盖的动作标识列表。
            jurisdiction: 目标辖区代码。

        Returns:
            compliance_mapping dict（含 jurisdiction、profile_name、actions）。
        """
        profile = self._profiles(jurisdiction)
        action_map: dict[str, dict[str, Any]] = {}
        for action in actions:
            decision = self.map_action(action, jurisdiction=jurisdiction)
            action_map[action] = {
                "enforcement": decision.enforcement.value,
                "risk_level": decision.risk_level.value,
                "regulations": list(decision.basis_regulations),
            }
        return {
            "jurisdiction": profile.code,
            "profile_name": profile.name,
            "actions": action_map,
        }


__all__ = ["PolicyDecision", "RegulatoryPolicyMapper"]
