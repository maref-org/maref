"""框架 3.0 风险分级（P2）测试。"""

from __future__ import annotations

from maref.compliance.cac.risk_grading import (
    GRADE_FLOW,
    CACRiskGrade,
    RiskDimension,
    exceeds,
    grade_action,
)
from maref.governance.risk_classifier import RiskLevel, classify_action


class TestEnums:
    def test_grade_enum_complete(self):
        assert len(CACRiskGrade) == 5
        assert {g.value for g in CACRiskGrade} == {"低", "一般", "较大", "重大", "特别重大"}

    def test_dimension_enum_complete(self):
        assert len(RiskDimension) == 4
        assert {d.value for d in RiskDimension} == {
            "客体类别",
            "影响程度",
            "影响范围",
            "可恢复性",
        }

    def test_grade_flow_covers_all_levels(self):
        assert set(GRADE_FLOW) == set(CACRiskGrade)


class TestGradeAction:
    def test_typical_actions_reproducible(self):
        for action in ("delete:prod-db", "publish:article", "file.write:config"):
            first = grade_action(action)
            second = grade_action(action)
            assert first == second
            assert isinstance(first.grade, CACRiskGrade)

    def test_irreversible_local_is_major(self):
        result = grade_action("delete:prod-db", {"impact_scope": "local"})
        assert result.grade is CACRiskGrade.MAJOR

    def test_irreversible_global_is_special_major(self):
        result = grade_action("delete:prod-db", {"impact_scope": "global"})
        assert result.grade is CACRiskGrade.SPECIAL_MAJOR

    def test_read_is_low(self):
        assert grade_action("read:doc").grade is CACRiskGrade.LOW

    def test_file_write_is_general(self):
        assert grade_action("file.write:config").grade is CACRiskGrade.GENERAL

    def test_self_reported_metadata_cannot_downgrade(self):
        result = grade_action("delete:prod-db", {"impact_scope": "local", "reversible": True})
        assert result.grade in (CACRiskGrade.MAJOR, CACRiskGrade.SPECIAL_MAJOR)

    def test_dimensions_complete(self):
        result = grade_action("delete:prod-db")
        assert set(result.dimensions) == set(RiskDimension)

    def test_object_category_detected(self):
        assert grade_action("delete:prod-db").dimensions[RiskDimension.OBJECT_CATEGORY] == "销毁性"
        assert grade_action("read:doc").dimensions[RiskDimension.OBJECT_CATEGORY] == "读取类"

    def test_recoverability_dimension(self):
        assert grade_action("delete:prod-db").dimensions[RiskDimension.RECOVERABILITY] == "不可恢复"

    def test_explain_and_flow(self):
        result = grade_action("delete:prod-db")
        assert "重大" in result.explain()
        assert result.flow == GRADE_FLOW[CACRiskGrade.MAJOR]

    def test_to_dict_serializable(self):
        data = grade_action("delete:prod-db").to_dict()
        assert data["grade"] in {g.value for g in CACRiskGrade}
        assert set(data["dimensions"]) == {d.value for d in RiskDimension}
        assert isinstance(data["reasons"], list)


class TestThreshold:
    def test_exceeds(self):
        assert exceeds(CACRiskGrade.SPECIAL_MAJOR, CACRiskGrade.MAJOR)
        assert not exceeds(CACRiskGrade.LOW, CACRiskGrade.GENERAL)

    def test_exceeds_equal_is_false(self):
        assert not exceeds(CACRiskGrade.MAJOR, CACRiskGrade.MAJOR)


class TestClassifierRegression:
    """现有 risk_classifier 行为不变（P2 验收断言 3）。"""

    def test_governance_four_levels_intact(self):
        assert classify_action("delete:prod-db").risk_level is RiskLevel.IRREVERSIBLE
        assert classify_action("file.write:config").risk_level is RiskLevel.MEDIUM
        assert classify_action("read:doc").risk_level is RiskLevel.LOW
        assert (
            classify_action("x", {"impact_scope": "global"}).risk_level is RiskLevel.HIGH
        )
