"""Tests for SocialImpactAssessor."""

from __future__ import annotations

from maref.governance.industry_data import (
    IndustrySector,
    get_high_risk_industries,
    get_industry,
    list_industries,
)
from maref.governance.social_impact import (
    BLOCK_THRESHOLD,
    RESTRICT_THRESHOLD,
    WARN_THRESHOLD,
    DeploymentVerdict,
    ImpactLevel,
    SocialImpactAssessor,
    SocialImpactReport,
)


class TestIndustryData:
    def test_get_known_industry(self) -> None:
        sector = get_industry("C")
        assert sector is not None
        assert sector.code == "C"
        assert sector.name == "Manufacturing"
        assert sector.substitution_rate == 0.55

    def test_get_unknown_industry(self) -> None:
        sector = get_industry("ZZ")
        assert sector is None

    def test_get_case_insensitive(self) -> None:
        sector = get_industry("c")
        assert sector is not None
        assert sector.code == "C"

    def test_list_industries_count(self) -> None:
        sectors = list_industries()
        assert len(sectors) == 19

    def test_list_industries_all_has_code(self) -> None:
        for s in list_industries():
            assert len(s.code) == 1
            assert s.name

    def test_high_risk_threshold_40(self) -> None:
        high = get_high_risk_industries(0.40)
        codes = [s.code for s in high]
        assert "C" in codes  # Manufacturing 0.55
        assert "N" in codes  # Admin 0.55
        assert "H" in codes  # Transport 0.50
        assert "Q" not in codes  # Healthcare 0.15

    def test_high_risk_threshold_50(self) -> None:
        high = get_high_risk_industries(0.50)
        codes = [s.code for s in high]
        assert "C" in codes
        assert "N" in codes
        assert "H" in codes
        assert "G" not in codes  # Retail 0.45

    def test_sector_dataclass(self) -> None:
        sector = IndustrySector(
            code="X", name="Test", description="test", substitution_rate=0.5,
            risk_factors=["a", "b"],
        )
        assert sector.code == "X"
        assert sector.risk_factors == ["a", "b"]


class TestSocialImpactAssessor:
    def test_unknown_industry_returns_low(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("ZZ", 1)
        assert report.impact_level == ImpactLevel.LOW
        assert report.verdict == DeploymentVerdict.ALLOW
        assert "Unknown industry" in report.findings[0]

    def test_low_substitution_manufacturing_single(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("C", 1)
        assert report.substitution_rate == 0.55
        assert report.effective_substitution_rate == 0.55
        assert report.impact_level == ImpactLevel.CRITICAL
        assert report.verdict == DeploymentVerdict.BLOCK

    def test_healthcare_low_impact(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("Q", 1)
        assert report.substitution_rate == 0.15
        assert report.impact_level == ImpactLevel.MEDIUM
        assert report.verdict == DeploymentVerdict.WARN

    def test_education_low_impact(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("P", 1)
        assert report.substitution_rate == 0.20
        assert report.impact_level == ImpactLevel.MEDIUM
        assert report.verdict == DeploymentVerdict.WARN

    def test_public_admin_low_impact(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("O", 1)
        assert report.impact_level == ImpactLevel.MEDIUM
        assert report.verdict == DeploymentVerdict.WARN

    def test_transport_high_impact(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("H", 1)
        assert report.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL)
        assert report.verdict in (DeploymentVerdict.RESTRICT, DeploymentVerdict.BLOCK)

    def test_manufacturing_blocked(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("C", 1)
        assert report.verdict == DeploymentVerdict.BLOCK
        assert report.hitl_tier == "p0_response"

    def test_admin_blocked(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("N", 1)
        assert report.verdict == DeploymentVerdict.BLOCK

    def test_capability_multiplier_increases_rate(self) -> None:
        assessor = SocialImpactAssessor()
        report_base = assessor.assess_deployment("Q", 1)
        report_boosted = assessor.assess_deployment(
            "Q", 1, capabilities=["decision_making", "customer_interaction"]
        )
        assert report_boosted.effective_substitution_rate > report_base.substitution_rate
        impact_rank = {ImpactLevel.LOW: 0, ImpactLevel.MEDIUM: 1, ImpactLevel.HIGH: 2, ImpactLevel.CRITICAL: 3}
        assert impact_rank[report_boosted.impact_level] >= impact_rank[report_base.impact_level]

    def test_physical_control_max_multiplier(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment(
            "Q", 1, capabilities=["physical_control"]
        )
        assert report.effective_substitution_rate == 0.30

    def test_large_deployment_scale_warning(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("Q", 150)
        assert any("Deployment scale" in f for f in report.findings)

    def test_small_deployment_no_scale_warning(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("Q", 10)
        assert not any("Deployment scale" in f for f in report.findings)

    def test_report_to_dict(self) -> None:
        assessor = SocialImpactAssessor()
        report = assessor.assess_deployment("Q", 1)
        d = report.to_dict()
        assert d["industry_code"] == "Q"
        assert d["impact_level"] == "medium"
        assert d["verdict"] == "warn"
        assert d["hitl_tier"] == "p2_log"

    def test_report_dataclass_direct(self) -> None:
        report = SocialImpactReport(
            industry_code="X", industry_name="Test", substitution_rate=0.3,
            effective_substitution_rate=0.3, agent_count=5,
            impact_level=ImpactLevel.MEDIUM, verdict=DeploymentVerdict.WARN,
            hitl_tier="p1_escalate", findings=["test"],
        )
        assert report.industry_code == "X"
        assert report.agent_count == 5

    def test_aggregate_impact_empty(self) -> None:
        assessor = SocialImpactAssessor()
        agg = assessor.compute_aggregate_impact([])
        assert agg["total_agents"] == 0
        assert agg["impact_level"] == "low"

    def test_aggregate_impact_single(self) -> None:
        assessor = SocialImpactAssessor()
        r1 = assessor.assess_deployment("Q", 10)
        agg = assessor.compute_aggregate_impact([r1])
        assert agg["total_agents"] == 10
        assert agg["highest_verdict"] == "warn"

    def test_aggregate_impact_multiple(self) -> None:
        assessor = SocialImpactAssessor()
        r1 = assessor.assess_deployment("Q", 10)
        r2 = assessor.assess_deployment("C", 5)
        agg = assessor.compute_aggregate_impact([r1, r2])
        assert agg["total_agents"] == 15
        assert agg["highest_verdict"] == "block"

    def test_capability_multiplier_capped(self) -> None:
        assessor = SocialImpactAssessor()
        caps = ["decision_making", "content_generation",
                "data_analysis", "customer_interaction", "physical_control"]
        report = assessor.assess_deployment("Q", 1, capabilities=caps)
        assert report.effective_substitution_rate <= 1.0
        assert report.verdict == DeploymentVerdict.BLOCK

    def test_thresholds_are_reasonable(self) -> None:
        assert 0 < WARN_THRESHOLD < RESTRICT_THRESHOLD < BLOCK_THRESHOLD <= 1.0

    def test_all_industries_assessable(self) -> None:
        assessor = SocialImpactAssessor()
        sectors = list_industries()
        for s in sectors:
            report = assessor.assess_deployment(s.code, 1)
            assert report.industry_code == s.code
            assert report.impact_level in ImpactLevel
            assert report.verdict in DeploymentVerdict
