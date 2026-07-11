# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0

"""地缘政治风险评估层.

防御威胁 M-003（地缘政治风险）：评估 AI 模型部署的司法管辖合规性、
数据主权要求、出口管制与制裁风险。

核心组件:
    - RiskLevel: 四级风险枚举（LOW/MEDIUM/HIGH/CRITICAL）
    - Jurisdiction: 司法管辖区定义（含制裁状态、数据主权要求）
    - JurisdictionMapper: 数据流风险评估器
    - GeoPoliticalRiskAssessor: 综合地缘政治风险评估器
    - SovereignAIValidator: 关键基础设施部署验证器

风险等级映射:
    - CRITICAL: 制裁管辖区（RU/IR/KP）→ force_halt=True
    - HIGH: 数据主权管辖区跨境数据流
    - MEDIUM: 非盟友管辖区
    - LOW: 同管辖区内部数据流

Usage:
    from maref.governance.geopolitical_risk import GeoPoliticalRiskAssessor

    assessor = GeoPoliticalRiskAssessor()
    assessment = assessor.assess(
        model_provider="OpenAI",
        deployment_jurisdiction="US",
        data_flows=[{"source": "US", "target": "EU"}],
    )
    if assessment.force_halt:
        print(f"Blocked: {assessment.recommendations}")
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """风险等级枚举."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __ge__(self, other: RiskLevel) -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return order[self] >= order[other]

    def __gt__(self, other: RiskLevel) -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return order[self] > order[other]

    def __le__(self, other: RiskLevel) -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return order[self] <= order[other]

    def __lt__(self, other: RiskLevel) -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return order[self] < order[other]


@dataclass
class Jurisdiction:
    """司法管辖区定义."""

    code: str
    """管辖区代码，如 "US", "EU", "CN"."""

    name: str
    """管辖区全名."""

    risk_level: RiskLevel
    """该管辖区的基础风险等级."""

    data_sovereignty_required: bool
    """是否要求数据主权（数据必须留在本管辖区）."""

    sanctions_active: bool = False
    """是否处于制裁状态."""

    export_controlled: bool = False
    """是否受出口管制."""


@dataclass
class DataFlowRisk:
    """数据流风险评估结果."""

    source: str
    """数据源管辖区代码."""

    target: str
    """数据目标管辖区代码."""

    risk_level: RiskLevel
    """该数据流的风险等级."""

    requires_cross_border_approval: bool
    """是否需要跨境数据传输审批."""

    reason: str
    """风险判定原因."""


@dataclass
class RiskAssessment:
    """综合风险评估报告."""

    overall_risk: RiskLevel
    """整体风险等级（取所有维度最高值）."""

    jurisdiction_risks: dict[str, RiskLevel]
    """各管辖区风险等级."""

    recommendations: list[str]
    """风险缓解建议."""

    force_halt: bool
    """是否应强制停机（CRITICAL 时为 True）."""

    assessed_at: datetime.datetime
    """评估时间戳."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_risk": self.overall_risk.value,
            "jurisdiction_risks": {k: v.value for k, v in self.jurisdiction_risks.items()},
            "recommendations": self.recommendations,
            "force_halt": self.force_halt,
            "assessed_at": self.assessed_at.isoformat(),
        }


@dataclass
class SovereignAIValidationResult:
    """主权 AI 验证结果."""

    valid: bool
    """是否通过验证."""

    violations: list[str] = field(default_factory=list)
    """违规描述列表."""

    jurisdiction: str = ""
    """部署管辖区."""

    is_critical_infra: bool = False
    """是否为关键基础设施部署."""


# 内置司法管辖区注册表
JURISDICTION_REGISTRY: dict[str, Jurisdiction] = {
    "US": Jurisdiction("US", "United States", RiskLevel.LOW, False),
    "EU": Jurisdiction("EU", "European Union", RiskLevel.LOW, True),
    "UK": Jurisdiction("UK", "United Kingdom", RiskLevel.LOW, False),
    "SG": Jurisdiction("SG", "Singapore", RiskLevel.LOW, False),
    "JP": Jurisdiction("JP", "Japan", RiskLevel.LOW, False),
    "AU": Jurisdiction("AU", "Australia", RiskLevel.LOW, False),
    "CN": Jurisdiction("CN", "China", RiskLevel.MEDIUM, True),
    "IN": Jurisdiction("IN", "India", RiskLevel.MEDIUM, False),
    "BR": Jurisdiction("BR", "Brazil", RiskLevel.MEDIUM, False),
    "RU": Jurisdiction(
        "RU", "Russia", RiskLevel.CRITICAL, True, sanctions_active=True, export_controlled=True
    ),
    "IR": Jurisdiction(
        "IR", "Iran", RiskLevel.CRITICAL, True, sanctions_active=True, export_controlled=True
    ),
    "KP": Jurisdiction(
        "KP", "North Korea", RiskLevel.CRITICAL, True, sanctions_active=True, export_controlled=True
    ),
}


def _get_jurisdiction(code: str) -> Jurisdiction:
    """获取管辖区定义，未知代码返回 HIGH 风险的默认管辖区."""
    return JURISDICTION_REGISTRY.get(
        code,
        Jurisdiction(code, f"Unknown ({code})", RiskLevel.HIGH, True),
    )


class JurisdictionMapper:
    """司法管辖区映射器 — 评估数据流风险."""

    def map_data_flow(
        self,
        source_jurisdiction: str,
        target_jurisdiction: str,
        data_categories: list[str] | None = None,
    ) -> DataFlowRisk:
        """评估数据流风险.

        Args:
            source_jurisdiction: 数据源管辖区代码.
            target_jurisdiction: 数据目标管辖区代码.
            data_categories: 数据类别（如 ["pii", "phi"]），影响风险但不改变基础逻辑.

        Returns:
            DataFlowRisk 包含风险等级与原因.
        """
        src = _get_jurisdiction(source_jurisdiction)
        tgt = _get_jurisdiction(target_jurisdiction)

        # 同管辖区 → LOW
        if source_jurisdiction == target_jurisdiction:
            return DataFlowRisk(
                source=source_jurisdiction,
                target=target_jurisdiction,
                risk_level=RiskLevel.LOW,
                requires_cross_border_approval=False,
                reason="Same jurisdiction data flow",
            )

        # 任一方制裁 → CRITICAL
        if src.sanctions_active or tgt.sanctions_active:
            return DataFlowRisk(
                source=source_jurisdiction,
                target=target_jurisdiction,
                risk_level=RiskLevel.CRITICAL,
                requires_cross_border_approval=True,
                reason=f"Sanctions active: {src.code} or {tgt.code}",
            )

        # 任一方要求数据主权 + 跨境 → HIGH
        if src.data_sovereignty_required or tgt.data_sovereignty_required:
            return DataFlowRisk(
                source=source_jurisdiction,
                target=target_jurisdiction,
                risk_level=RiskLevel.HIGH,
                requires_cross_border_approval=True,
                reason="Cross-border flow involving data sovereignty jurisdiction",
            )

        # 出口管制 → HIGH
        if src.export_controlled or tgt.export_controlled:
            return DataFlowRisk(
                source=source_jurisdiction,
                target=target_jurisdiction,
                risk_level=RiskLevel.HIGH,
                requires_cross_border_approval=True,
                reason="Export-controlled jurisdiction involved",
            )

        # 跨境但无特殊限制 → MEDIUM
        return DataFlowRisk(
            source=source_jurisdiction,
            target=target_jurisdiction,
            risk_level=RiskLevel.MEDIUM,
            requires_cross_border_approval=True,
            reason="Cross-border data flow requires approval",
        )


class GeoPoliticalRiskAssessor:
    """地缘政治风险评估器 — 综合评估部署风险."""

    def __init__(self, mapper: JurisdictionMapper | None = None) -> None:
        self._mapper = mapper or JurisdictionMapper()

    def assess(
        self,
        model_provider: str,
        deployment_jurisdiction: str,
        data_flows: list[dict[str, Any]],
    ) -> RiskAssessment:
        """综合评估地缘政治风险.

        Args:
            model_provider: 模型供应商名称（如 "OpenAI", "Anthropic"）.
            deployment_jurisdiction: 部署管辖区代码.
            data_flows: 数据流列表，每项含 source/target 键.

        Returns:
            RiskAssessment 包含整体风险、各管辖区风险、建议。
        """
        jurisdiction_risks: dict[str, RiskLevel] = {}
        recommendations: list[str] = []
        overall_risk = RiskLevel.LOW

        # 1. 检查部署管辖区的制裁状态
        deploy_juris = _get_jurisdiction(deployment_jurisdiction)
        jurisdiction_risks[deployment_jurisdiction] = deploy_juris.risk_level
        if deploy_juris.risk_level > overall_risk:
            overall_risk = deploy_juris.risk_level

        if deploy_juris.sanctions_active:
            recommendations.append(
                f"BLOCK: Deployment jurisdiction {deployment_jurisdiction} is under sanctions"
            )

        # 2. 评估每个数据流的跨辖风险
        for flow in data_flows:
            source = flow.get("source", "")
            target = flow.get("target", "")
            if not source or not target:
                continue

            flow_risk = self._mapper.map_data_flow(source, target)
            # Use RiskLevel's custom __gt__ operator (not .value string comparison,
            # which would order "critical" < "high" < "low" < "medium" alphabetically)
            jurisdiction_risks[source] = max(
                jurisdiction_risks.get(source, RiskLevel.LOW),
                flow_risk.risk_level,
            )
            jurisdiction_risks[target] = max(
                jurisdiction_risks.get(target, RiskLevel.LOW),
                flow_risk.risk_level,
            )

            if flow_risk.risk_level > overall_risk:
                overall_risk = flow_risk.risk_level

            if flow_risk.risk_level >= RiskLevel.HIGH:
                recommendations.append(
                    f"Review data flow {source}->{target}: {flow_risk.reason}"
                )

        # 3. 生成建议
        if overall_risk >= RiskLevel.CRITICAL:
            recommendations.append("FORCE HALT: Critical geopolitical risk detected")
        elif overall_risk >= RiskLevel.HIGH:
            recommendations.append("Require cross-border data transfer approval")
        elif overall_risk >= RiskLevel.MEDIUM:
            recommendations.append("Monitor data flows for compliance changes")

        if not recommendations:
            recommendations.append("No geopolitical risk concerns detected")

        return RiskAssessment(
            overall_risk=overall_risk,
            jurisdiction_risks=jurisdiction_risks,
            recommendations=recommendations,
            force_halt=overall_risk >= RiskLevel.CRITICAL,
            assessed_at=datetime.datetime.now(),
        )


class SovereignAIValidator:
    """主权 AI 验证器 — 关键基础设施部署合规.

    确保关键基础设施（如电网、金融系统、通信）的 AI 部署
    在受信司法管辖区内，且数据不出境。
    """

    # 关键基础设施必须部署在受信管辖区
    TRUSTED_INFRA_JURISDICTIONS = {"US", "EU", "UK", "JP", "AU", "SG"}

    # 关键基础设施类型
    CRITICAL_INFRA_TYPES = {
        "power_grid",
        "financial_system",
        "telecommunications",
        "water_treatment",
        "transportation",
        "healthcare",
        "government",
    }

    def validate_critical_infra(
        self,
        deployment: dict[str, Any],
    ) -> SovereignAIValidationResult:
        """验证关键基础设施部署是否合规.

        Args:
            deployment: 部署描述字典，含:
                - jurisdiction: 部署管辖区代码
                - infra_type: 基础设施类型
                - data_residency: 数据实际存储位置
                - model_provider: 模型供应商

        Returns:
            SovereignAIValidationResult 包含验证结果与违规描述.
        """
        jurisdiction = deployment.get("jurisdiction", "")
        infra_type = deployment.get("infra_type", "")
        data_residency = deployment.get("data_residency", "")
        is_critical = infra_type in self.CRITICAL_INFRA_TYPES

        violations: list[str] = []

        if is_critical:
            # 关键基础设施必须在受信管辖区
            if jurisdiction not in self.TRUSTED_INFRA_JURISDICTIONS:
                violations.append(
                    f"Critical infrastructure ({infra_type}) must be deployed in "
                    f"trusted jurisdiction, got {jurisdiction}"
                )

            # 数据必须留在部署管辖区
            if data_residency and data_residency != jurisdiction:
                violations.append(
                    f"Critical infrastructure data must reside in {jurisdiction}, "
                    f"got {data_residency}"
                )

        return SovereignAIValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            jurisdiction=jurisdiction,
            is_critical_infra=is_critical,
        )


__all__ = [
    "RiskLevel",
    "Jurisdiction",
    "DataFlowRisk",
    "RiskAssessment",
    "SovereignAIValidationResult",
    "JURISDICTION_REGISTRY",
    "JurisdictionMapper",
    "GeoPoliticalRiskAssessor",
    "SovereignAIValidator",
]
