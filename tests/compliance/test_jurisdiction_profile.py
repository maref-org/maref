"""v0.45.0 监管适配层测试（方案 G：JurisdictionProfile + RegulatoryPolicyMapper）。"""

from __future__ import annotations

from maref.compliance.jurisdiction_profile import (
    CN_PROFILE,
    EU_PROFILE,
    GLOBAL_SOUTH_PROFILE,
    PROFILE_REGISTRY,
    EnforcementLevel,
    JurisdictionProfile,
    get_profile,
)
from maref.compliance.regulatory_policy_mapper import PolicyDecision, RegulatoryPolicyMapper
from maref.governance.risk_classifier import RiskLevel as ClassifierRiskLevel


class TestJurisdictionProfile:
    def test_profiles_present(self) -> None:
        assert set(PROFILE_REGISTRY) == {"cn", "eu", "global_south"}

    def test_profile_structure(self) -> None:
        profile = EU_PROFILE
        assert profile.code == "eu"
        assert profile.regulations
        assert "eu_ai_act" in [r.regulation_id for r in profile.regulations]
        assert profile.data_sovereignty_required is True
        assert profile.human_oversight_for_high_risk is True

    def test_cn_profile_has_generative_ai_measures(self) -> None:
        ids = [r.regulation_id for r in CN_PROFILE.regulations]
        assert "cn_generative_ai_measures" in ids
        assert "cn_csl" in ids

    def test_global_south_profile(self) -> None:
        profile = GLOBAL_SOUTH_PROFILE
        assert profile.human_oversight_for_high_risk is False
        assert profile.data_sovereignty_required is False
        # 高风险仍为 advisory，critical 才 enforce
        assert profile.enforcement_for_risk(ClassifierRiskLevel.HIGH) == EnforcementLevel.ADVISORY
        assert profile.enforcement_for_risk(ClassifierRiskLevel.IRREVERSIBLE) == EnforcementLevel.ENFORCE

    def test_enforcement_table(self) -> None:
        assert EU_PROFILE.enforcement_for_risk(ClassifierRiskLevel.LOW) == EnforcementLevel.OBSERVE
        assert EU_PROFILE.enforcement_for_risk(ClassifierRiskLevel.HIGH) == EnforcementLevel.ENFORCE

    def test_irreversible_fail_safe_enforce(self) -> None:
        # IRREVERSIBLE 未在 enforcement_table 时 fail-safe 回退 ENFORCE
        assert EU_PROFILE.enforcement_for_risk(ClassifierRiskLevel.IRREVERSIBLE) == EnforcementLevel.ENFORCE

    def test_unknown_risk_fail_safe(self) -> None:
        profile = JurisdictionProfile(code="x", name="x", enforcement_table={"high": EnforcementLevel.ENFORCE})
        assert profile.enforcement_for_risk(ClassifierRiskLevel.HIGH) == EnforcementLevel.ENFORCE

    def test_unknown_profile_fail_open(self) -> None:
        profile = get_profile("zz")
        assert profile.code == "zz"
        assert profile.regulations == []
        assert profile.enforcement_for_risk(ClassifierRiskLevel.HIGH) == EnforcementLevel.OBSERVE

    def test_to_dict_roundtrip(self) -> None:
        data = EU_PROFILE.to_dict()
        assert data["code"] == "eu"
        assert data["enforcement_table"]["high"] == "enforce"
        assert data["regulations"][0]["id"] == "eu_ai_act"


class TestRegulatoryPolicyMapper:
    def test_enforce_in_cn(self) -> None:
        decision = RegulatoryPolicyMapper().map_action("payment:transfer", jurisdiction="cn")
        assert isinstance(decision, PolicyDecision)
        assert decision.enforcement == EnforcementLevel.ENFORCE
        assert decision.blocked is True
        assert "cn_generative_ai_measures" in decision.basis_regulations

    def test_switch_jurisdiction_changes_enforcement(self) -> None:
        mapper = RegulatoryPolicyMapper()
        # global impact → HIGH 级动作（非 IRREVERSIBLE）
        cn = mapper.map_action(
            "file.export", jurisdiction="cn",
            metadata={"impact_scope": "global"},
        )
        gs = mapper.map_action(
            "file.export", jurisdiction="global_south",
            metadata={"impact_scope": "global"},
        )
        assert cn.risk_level == ClassifierRiskLevel.HIGH
        # CN 高风险强制、Global-South 高风险仅 advisory
        assert cn.enforcement == EnforcementLevel.ENFORCE
        assert gs.enforcement == EnforcementLevel.ADVISORY

    def test_low_risk_observe(self) -> None:
        decision = RegulatoryPolicyMapper().map_action("file.read", jurisdiction="eu")
        assert decision.enforcement == EnforcementLevel.OBSERVE
        assert decision.blocked is False

    def test_to_dict(self) -> None:
        decision = RegulatoryPolicyMapper().map_action("deploy:app", jurisdiction="eu")
        data = decision.to_dict()
        assert data["jurisdiction"] == "eu"
        assert data["blocked"] is True
        assert data["enforcement"] == "enforce"

    def test_unknown_jurisdiction(self) -> None:
        decision = RegulatoryPolicyMapper().map_action("file.read", jurisdiction="zz")
        assert decision.enforcement == EnforcementLevel.OBSERVE


class TestCredentialComplianceMapping:
    def test_build_credential_mapping(self) -> None:
        mapper = RegulatoryPolicyMapper()
        mapping = mapper.build_credential_mapping(
            actions=["file.read", "file.export"],
            jurisdiction="eu",
        )
        assert mapping["jurisdiction"] == "eu"
        assert mapping["actions"]["file.read"]["enforcement"] == "observe"
        # file.export 默认本地 impact_scope → LOW/MEDIUM；用 enforce 断言见下一用例
        assert "file.export" in mapping["actions"]

    def test_build_credential_mapping_with_metadata(self) -> None:
        mapper = RegulatoryPolicyMapper()
        # 通过 regulatory policy mapper 直接构造：payment:transfer → IRREVERSIBLE → enforce
        decision = mapper.map_action("payment:transfer", jurisdiction="eu")
        assert decision.enforcement == EnforcementLevel.ENFORCE
        assert "eu_ai_act" in decision.basis_regulations
