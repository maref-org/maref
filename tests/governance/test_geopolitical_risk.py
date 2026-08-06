"""Tests for GeoPoliticalRiskAssessor — 地缘政治风险评估层.

覆盖:
- RiskLevel 枚举值与比较运算符
- JURISDICTION_REGISTRY 注册表内容
- JurisdictionMapper 数据流风险映射
- GeoPoliticalRiskAssessor 综合评估（制裁→CRITICAL→force_halt）
- SovereignAIValidator 关键基础设施部署验证

防御威胁: G-001 至 G-004 (地缘政治层威胁)
"""

from __future__ import annotations

from maref.governance.geopolitical_risk import (
    JURISDICTION_REGISTRY,
    GeoPoliticalRiskAssessor,
    JurisdictionMapper,
    RiskLevel,
    SovereignAIValidator,
)


class TestRiskLevel:
    """RiskLevel 枚举值与比较运算符."""

    def test_enum_values(self) -> None:
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_comparison_operators(self) -> None:
        assert RiskLevel.CRITICAL > RiskLevel.HIGH
        assert RiskLevel.HIGH > RiskLevel.MEDIUM
        assert RiskLevel.MEDIUM > RiskLevel.LOW
        assert RiskLevel.LOW < RiskLevel.CRITICAL
        assert RiskLevel.HIGH >= RiskLevel.HIGH
        assert RiskLevel.MEDIUM <= RiskLevel.HIGH
        assert RiskLevel.CRITICAL >= RiskLevel.CRITICAL


class TestJurisdictionRegistry:
    """JURISDICTION_REGISTRY 注册表内容验证."""

    def test_data_sovereignty_required(self) -> None:
        """EU 和 CN 要求数据主权."""
        assert JURISDICTION_REGISTRY["EU"].data_sovereignty_required is True
        assert JURISDICTION_REGISTRY["CN"].data_sovereignty_required is True
        assert JURISDICTION_REGISTRY["US"].data_sovereignty_required is False

    def test_sanctioned_jurisdictions(self) -> None:
        """RU/IR/KP 处于制裁状态."""
        for code in ("RU", "IR", "KP"):
            jur = JURISDICTION_REGISTRY[code]
            assert jur.sanctions_active is True
            assert jur.risk_level == RiskLevel.CRITICAL
            assert jur.export_controlled is True

    def test_low_risk_jurisdictions(self) -> None:
        """US/EU/UK/SG/JP/AU 为 LOW 风险."""
        for code in ("US", "EU", "UK", "SG", "JP", "AU"):
            assert JURISDICTION_REGISTRY[code].risk_level == RiskLevel.LOW


class TestJurisdictionMapper:
    """JurisdictionMapper 数据流风险映射."""

    def test_cross_border_flow_high_risk(self) -> None:
        """US→CN 数据流 → HIGH（CN 要求数据主权，无制裁）."""
        mapper = JurisdictionMapper()
        risk = mapper.map_data_flow("US", "CN")
        assert risk.risk_level == RiskLevel.HIGH
        assert risk.requires_cross_border_approval is True
        assert risk.source == "US"
        assert risk.target == "CN"

    def test_same_jurisdiction_low_risk(self) -> None:
        """US→US 同管辖区 → LOW."""
        mapper = JurisdictionMapper()
        risk = mapper.map_data_flow("US", "US")
        assert risk.risk_level == RiskLevel.LOW
        assert risk.requires_cross_border_approval is False

    def test_sanctioned_flow_critical(self) -> None:
        """US→RU 数据流 → CRITICAL（RU 制裁）."""
        mapper = JurisdictionMapper()
        risk = mapper.map_data_flow("US", "RU")
        assert risk.risk_level == RiskLevel.CRITICAL
        assert risk.requires_cross_border_approval is True

    def test_jurisdiction_mapper_unknown_code(self) -> None:
        """未知管辖区代码 → 默认 HIGH 风险 + 数据主权要求."""
        mapper = JurisdictionMapper()
        risk = mapper.map_data_flow("US", "XX")
        # XX 未知 → _get_jurisdiction 返回 HIGH + data_sovereignty_required=True
        # US→XX 跨境 + 数据主权 → HIGH
        assert risk.risk_level == RiskLevel.HIGH
        assert risk.requires_cross_border_approval is True


class TestGeoPoliticalRiskAssessor:
    """GeoPoliticalRiskAssessor 综合评估."""

    def test_sanctioned_jurisdiction_critical(self) -> None:
        """RU 部署 → overall_risk=CRITICAL, force_halt=True."""
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="TestCorp",
            deployment_jurisdiction="RU",
            data_flows=[],
        )
        assert assessment.overall_risk == RiskLevel.CRITICAL
        assert assessment.force_halt is True
        assert "RU" in assessment.jurisdiction_risks

    def test_force_halt_on_critical(self) -> None:
        """KP 部署 → force_halt=True."""
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="TestCorp",
            deployment_jurisdiction="KP",
            data_flows=[],
        )
        assert assessment.force_halt is True
        assert assessment.overall_risk == RiskLevel.CRITICAL

    def test_recommendations_generated(self) -> None:
        """高风险场景 → recommendations 非空，含 FORCE HALT."""
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="TestCorp",
            deployment_jurisdiction="RU",
            data_flows=[{"source": "US", "target": "CN"}],
        )
        assert len(assessment.recommendations) > 0
        assert any("FORCE HALT" in r for r in assessment.recommendations)

    def test_low_risk_deployment(self) -> None:
        """US 部署 + 同辖区数据流 → LOW, force_halt=False."""
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="OpenAI",
            deployment_jurisdiction="US",
            data_flows=[{"source": "US", "target": "US"}],
        )
        assert assessment.overall_risk == RiskLevel.LOW
        assert assessment.force_halt is False

    def test_to_dict_serialization(self) -> None:
        """RiskAssessment.to_dict() 可序列化."""
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="TestCorp",
            deployment_jurisdiction="US",
            data_flows=[],
        )
        d = assessment.to_dict()
        assert "overall_risk" in d
        assert "jurisdiction_risks" in d
        assert "recommendations" in d
        assert "force_halt" in d
        assert "assessed_at" in d

    def test_critical_flow_jurisdiction_risk_correct(self) -> None:
        """Regression: 数据流涉及制裁辖区时 jurisdiction_risks 必须正确记录 CRITICAL.

        之前 max(key=lambda r: r.value) 按字符串字典序比较，
        导致 "critical" < "low"，CRITICAL 被错误降级为 LOW。
        """
        assessor = GeoPoliticalRiskAssessor()
        assessment = assessor.assess(
            model_provider="TestCorp",
            deployment_jurisdiction="US",
            data_flows=[{"source": "US", "target": "RU"}],
        )
        # RU 是制裁辖区 → 数据流 CRITICAL
        assert assessment.jurisdiction_risks["RU"] == RiskLevel.CRITICAL
        assert assessment.overall_risk == RiskLevel.CRITICAL
        assert assessment.force_halt is True


class TestSovereignAIValidator:
    """SovereignAIValidator 关键基础设施部署验证."""

    def test_sovereign_ai_validator_rejects_adversarial(self) -> None:
        """关键基础设施部署在非受信辖区（CN）→ 拒绝."""
        validator = SovereignAIValidator()
        result = validator.validate_critical_infra(
            {
                "jurisdiction": "CN",
                "infra_type": "power_grid",
                "data_residency": "CN",
                "model_provider": "TestCorp",
            }
        )
        assert result.valid is False
        assert len(result.violations) > 0
        assert result.is_critical_infra is True
        assert result.jurisdiction == "CN"

    def test_sovereign_ai_validator_accepts_trusted(self) -> None:
        """关键基础设施部署在受信辖区（US）+ 数据留境 → 通过."""
        validator = SovereignAIValidator()
        result = validator.validate_critical_infra(
            {
                "jurisdiction": "US",
                "infra_type": "power_grid",
                "data_residency": "US",
                "model_provider": "OpenAI",
            }
        )
        assert result.valid is True
        assert result.violations == []
        assert result.is_critical_infra is True
        assert result.jurisdiction == "US"

    def test_non_critical_infra_always_valid(self) -> None:
        """非关键基础设施类型 → 永远通过."""
        validator = SovereignAIValidator()
        result = validator.validate_critical_infra(
            {
                "jurisdiction": "RU",
                "infra_type": "web_app",
                "data_residency": "RU",
            }
        )
        assert result.valid is True
        assert result.is_critical_infra is False

    def test_data_residency_mismatch_rejected(self) -> None:
        """关键基础设施数据不在部署辖区 → 拒绝."""
        validator = SovereignAIValidator()
        result = validator.validate_critical_infra(
            {
                "jurisdiction": "US",
                "infra_type": "financial_system",
                "data_residency": "CN",
            }
        )
        assert result.valid is False
        assert any("data must reside" in v.lower() for v in result.violations)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
