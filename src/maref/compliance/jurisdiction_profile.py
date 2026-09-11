"""JurisdictionProfile — 监管适配层核心数据模型（v0.45.0 方案 G G1）。

将「治理策略」与「司法辖区监管要求」解耦：同一治理动作按目标辖区
映射到不同的强制级别（OBSERVE / ADVISORY / ENFORCE），使 MAREF
从"单套策略"走向"多辖区自适应合规"。

预置三档监管画像：
- ``cn`` 中国生成式 AI 办法（CAC 网信办）
- ``eu`` 欧盟 AI Act
- ``global_south`` 全球南方（巴西/印度/东南亚等）

设计依据: docs/plans/2026-08-03-v0.45.0-iteration-plan.md §2.1 G1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.compliance.registry import Jurisdiction, Regulation, RegulationType


class EnforcementLevel(str, Enum):
    """动作处置强制级别（observe → advisory → enforce）。"""

    OBSERVE = "observe"
    ADVISORY = "advisory"
    ENFORCE = "enforce"


_ENFORCEMENT_SEVERITY: dict[EnforcementLevel, int] = {
    EnforcementLevel.OBSERVE: 0,
    EnforcementLevel.ADVISORY: 1,
    EnforcementLevel.ENFORCE: 2,
}


class RegulationCode(str, Enum):
    """法规代码 — 作为 profile 内法规引用键。"""

    CN_GENERATIVE_AI = "cn_generative_ai_measures"
    CN_CSL = "cn_csl"
    CN_PIPL = "cn_pipl"
    EU_AI_ACT = "eu_ai_act"
    EU_GDPR = "eu_gdpr"
    BR_LGPD = "br_lgpd"
    IN_DPDP = "in_dpdp"
    ZA_POPIA = "za_popia"


@dataclass(frozen=True)
class JurisdictionProfile:
    """一个司法辖区的监管画像。

    Attributes:
        code: 辖区代码（cn / eu / global_south / custom）。
        name: 辖区名称。
        regulations: 该辖区适用的法规列表。
        enforcement_table: 风险等级 → 强制级别映射（决定 ENFORCE 门槛）。
        data_sovereignty_required: 是否要求数据留在本辖区。
        consent_required: 是否要求用户同意（个人数据）。
        cross_border_approval_required: 跨境数据是否需审批。
        human_oversight_for_high_risk: 高风险动作是否强制人工监督。
    """

    code: str
    name: str
    regulations: list[Regulation] = field(default_factory=list)
    enforcement_table: dict[str, EnforcementLevel] = field(default_factory=dict)
    data_sovereignty_required: bool = False
    consent_required: bool = False
    cross_border_approval_required: bool = False
    human_oversight_for_high_risk: bool = False

    def enforcement_for_risk(self, risk_level: Any) -> EnforcementLevel:
        """返回该辖区下给定风险等级对应的强制级别。

        ``risk_level`` 接受 :class:`~maref.governance.geopolitical_risk.RiskLevel`
        或 :class:`~maref.governance.risk_classifier.RiskLevel`。注意两套枚举
        ``value`` 大小写不一致（geopolitical 为小写，classifier 为大写），
        此处统一转为小写匹配。

        未显式配置的风险等级按 fail-safe 处理：回退到表内最严格档
        （ENFORCE > ADVISORY > OBSERVE）；空表返回 OBSERVE。
        """
        key = str(risk_level.value).lower()
        if key in self.enforcement_table:
            return self.enforcement_table[key]
        # fail-safe：未知风险等级按表内最严格档处理（不得 fail-open 降级）。
        if not self.enforcement_table:
            return EnforcementLevel.OBSERVE
        return max(
            self.enforcement_table.values(),
            key=lambda level: _ENFORCEMENT_SEVERITY[level],
        )

    def governance_scope_enforcement(self, scope: str) -> EnforcementLevel:
        """返回给定治理维度在该辖区的强制级别（v0.45.0 G3 语义修正）。

        治理维度（state_machine/drift/consensus/memory/audit）非动作，
        不适用动作风险分级。按治理维度语义归类：
        - 跨组织/共识类维度（consensus、state_machine）→ 辖区最严格档
        - 数据/记忆类维度（memory、audit、drift）→ 辖区高风险档
          （enforcement_table["high"]，无则用最严格档）
        """
        _CROSS_ORG_SCOPES = {"consensus", "state_machine"}
        if scope in _CROSS_ORG_SCOPES:
            return self._max_enforcement()
        high = self.enforcement_table.get("high")
        if high is not None:
            return high
        return self._max_enforcement()

    def _max_enforcement(self) -> EnforcementLevel:
        if not self.enforcement_table:
            return EnforcementLevel.OBSERVE
        return max(
            self.enforcement_table.values(),
            key=lambda level: _ENFORCEMENT_SEVERITY[level],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "regulations": [
                {
                    "id": r.regulation_id,
                    "name": r.name,
                    "type": r.regulation_type.value,
                }
                for r in self.regulations
            ],
            "enforcement_table": {k: v.value for k, v in self.enforcement_table.items()},
            "data_sovereignty_required": self.data_sovereignty_required,
            "consent_required": self.consent_required,
            "cross_border_approval_required": self.cross_border_approval_required,
            "human_oversight_for_high_risk": self.human_oversight_for_high_risk,
        }


# ---------------------------------------------------------------------------
# 预置三档监管画像
# ---------------------------------------------------------------------------


def _cn_regulations() -> list[Regulation]:
    return [
        Regulation(
            regulation_id=RegulationCode.CN_GENERATIVE_AI.value,
            name="生成式人工智能服务管理暂行办法（CAC 网信办）",
            jurisdiction=Jurisdiction.CHINA,
            regulation_type=RegulationType.AI_GOVERNANCE,
            description="中国生成式 AI 办法 — 内容合规、算法备案、数据合法性",
            requirements=[
                "content_compliance",
                "algorithm_filing",
                "data_legality",
                "labeling",
            ],
            penalty="责令改正、暂停服务、吊销许可",
        ),
        Regulation(
            regulation_id=RegulationCode.CN_CSL.value,
            name="China Cybersecurity Law",
            jurisdiction=Jurisdiction.CHINA,
            regulation_type=RegulationType.CYBERSECURITY,
            description="网络安全法 — 数据本地化、跨境审查",
            requirements=[
                "data_localization",
                "security_assessment",
                "cross_border_transfer_review",
            ],
            penalty="最高 100 万罚款或暂停业务",
        ),
    ]


def _eu_regulations() -> list[Regulation]:
    return [
        Regulation(
            regulation_id=RegulationCode.EU_AI_ACT.value,
            name="EU AI Act",
            jurisdiction=Jurisdiction.EU,
            regulation_type=RegulationType.AI_GOVERNANCE,
            description="欧盟 AI 法案 — 风险分级、透明度、人类监督",
            requirements=[
                "risk_classification",
                "high_risk_requirements",
                "transparency_obligations",
                "human_oversight",
            ],
            penalty="最高全球营业额 6%",
        ),
        Regulation(
            regulation_id=RegulationCode.EU_GDPR.value,
            name="General Data Protection Regulation",
            jurisdiction=Jurisdiction.EU,
            regulation_type=RegulationType.DATA_PROTECTION,
            description="通用数据保护条例 — 最小化、目的限定、同意",
            requirements=[
                "lawful_basis",
                "data_minimization",
                "purpose_limitation",
                "consent",
            ],
            penalty="最高全球营业额 4% 或 2000 万欧元",
        ),
    ]


def _global_south_regulations() -> list[Regulation]:
    return [
        Regulation(
            regulation_id=RegulationCode.BR_LGPD.value,
            name="Brazil LGPD",
            jurisdiction=Jurisdiction.GLOBAL,
            regulation_type=RegulationType.DATA_PROTECTION,
            description="巴西通用数据保护法 — 合法基础、主体权利",
            requirements=["legal_basis", "data_subject_rights", "consent"],
            penalty="最高年营业额 2%",
        ),
        Regulation(
            regulation_id=RegulationCode.IN_DPDP.value,
            name="India DPDP Act",
            jurisdiction=Jurisdiction.INDIA,
            regulation_type=RegulationType.DATA_PROTECTION,
            description="印度数据保护法 — 数据受托人义务、跨境转移",
            requirements=[
                "data_fiduciary_obligations",
                "data_principal_rights",
                "cross_border_transfer",
            ],
            penalty="最高 25 亿卢比",
        ),
        Regulation(
            regulation_id=RegulationCode.ZA_POPIA.value,
            name="South Africa POPIA",
            jurisdiction=Jurisdiction.GLOBAL,
            regulation_type=RegulationType.DATA_PROTECTION,
            description="南非个人信息保护法 — 合法处理、问责",
            requirements=["lawful_processing", "accountability", "security_safeguards"],
            penalty="最高 1000 万兰特",
        ),
    ]


def _build_profile(
    code: str,
    name: str,
    regulations: list[Regulation],
    enforcement_table: dict[str, EnforcementLevel],
    **kwargs: Any,
) -> JurisdictionProfile:
    return JurisdictionProfile(
        code=code,
        name=name,
        regulations=regulations,
        enforcement_table=enforcement_table,
        **kwargs,
    )


# 中国生成式 AI 办法：高风险动作强制监管、内容合规 enforce。
CN_PROFILE = _build_profile(
    code="cn",
    name="China — 生成式人工智能服务管理暂行办法",
    regulations=_cn_regulations(),
    enforcement_table={
        "low": EnforcementLevel.OBSERVE,
        "medium": EnforcementLevel.ADVISORY,
        "high": EnforcementLevel.ENFORCE,
        "critical": EnforcementLevel.ENFORCE,
    },
    data_sovereignty_required=True,
    consent_required=True,
    cross_border_approval_required=True,
    human_oversight_for_high_risk=True,
)

# 欧盟 AI Act：高风险强制、中风险透明义务、极端情况强制。
EU_PROFILE = _build_profile(
    code="eu",
    name="European Union — AI Act + GDPR",
    regulations=_eu_regulations(),
    enforcement_table={
        "low": EnforcementLevel.OBSERVE,
        "medium": EnforcementLevel.ADVISORY,
        "high": EnforcementLevel.ENFORCE,
        "critical": EnforcementLevel.ENFORCE,
    },
    data_sovereignty_required=True,
    consent_required=True,
    cross_border_approval_required=True,
    human_oversight_for_high_risk=True,
)

# 全球南方：以数据保护为主，高风险动作 enforcement，其余 advisory。
GLOBAL_SOUTH_PROFILE = _build_profile(
    code="global_south",
    name="Global South — 数据保护公约（LGPD/DPDP/POPIA）",
    regulations=_global_south_regulations(),
    enforcement_table={
        "low": EnforcementLevel.OBSERVE,
        "medium": EnforcementLevel.ADVISORY,
        "high": EnforcementLevel.ADVISORY,
        "critical": EnforcementLevel.ENFORCE,
    },
    data_sovereignty_required=False,
    consent_required=True,
    cross_border_approval_required=True,
    human_oversight_for_high_risk=False,
)

PROFILE_REGISTRY: dict[str, JurisdictionProfile] = {
    "cn": CN_PROFILE,
    "eu": EU_PROFILE,
    "global_south": GLOBAL_SOUTH_PROFILE,
}


def get_profile(code: str) -> JurisdictionProfile:
    """按代码取辖区画像。

    未知辖区返回 fail-closed 的严格画像（v0.47 R1）：所有风险等级强制
    ENFORCE（此前是宽松 OBSERVE 的 fail-open，监管语义下不应默认放行）。
    """
    known = PROFILE_REGISTRY.get(code)
    if known is not None:
        return known
    return JurisdictionProfile(
        code=code,
        name=code,
        enforcement_table={
            "low": EnforcementLevel.ENFORCE,
            "medium": EnforcementLevel.ENFORCE,
            "high": EnforcementLevel.ENFORCE,
            "irreversible": EnforcementLevel.ENFORCE,
        },
    )


__all__ = [
    "EnforcementLevel",
    "RegulationCode",
    "JurisdictionProfile",
    "CN_PROFILE",
    "EU_PROFILE",
    "GLOBAL_SOUTH_PROFILE",
    "PROFILE_REGISTRY",
    "get_profile",
]
