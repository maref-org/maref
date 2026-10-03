"""《人工智能安全治理框架3.0》MAREF 映射模块测试。

验收要点：
- 7 组防范措施齐全；
- 全部引用的 module_path / symbol 真实存在（fail-closed，禁止吹牛）；
- 缺口（partial/missing）如实标注，不把碎片包装成已覆盖；
- Markdown 渲染幂等。
"""

from __future__ import annotations

import pytest

from maref.compliance.cac.framework_3_0 import (
    CATEGORIES,
    MAPS,
    STATUS_COVERED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    FrameworkMapping,
    coverage_report,
    effective_status,
    gaps,
    render_markdown,
    verify_mapping,
    verify_module_paths,
    verify_report,
)


class TestMappingCompleteness:
    """映射矩阵的完整性与结构。"""

    def test_all_seven_categories_present(self):
        assert len(CATEGORIES) == 7
        mapped = {m.category for m in MAPS}
        assert mapped == set(CATEGORIES), f"缺失类别: {set(CATEGORIES) - mapped}"

    def test_every_category_has_entries(self):
        for category in CATEGORIES:
            entries = [m for m in MAPS if m.category == category]
            assert entries, f"{category} 无映射条目"

    def test_every_mapping_has_required_fields(self):
        for m in MAPS:
            assert m.category
            assert m.clause, f"{m.category} 缺 clause"
            assert m.requirement, f"{m.clause} 缺 requirement"
            assert m.maref_implementation, f"{m.clause} 缺 maref_implementation"
            assert m.status in (STATUS_COVERED, STATUS_PARTIAL, STATUS_MISSING)

    def test_missing_entries_have_no_module_path(self):
        for m in MAPS:
            if m.status == STATUS_MISSING:
                assert m.module_path == "", f"{m.clause} missing 条目不应有 module_path"
                assert m.symbol == ""

    def test_covered_entries_have_module_and_symbol(self):
        for m in MAPS:
            if m.status in (STATUS_COVERED, STATUS_PARTIAL):
                assert m.module_path, f"{m.clause} 覆盖条目必须有 module_path"
                assert m.symbol, f"{m.clause} 覆盖条目必须有 symbol"


class TestPathVerification:
    """fail-closed 路径校验。"""

    def test_all_referenced_modules_exist(self):
        failures = verify_module_paths()
        assert failures == [], f"存在臆造模块引用: {failures}"

    def test_verify_report_passes(self):
        report = verify_report()
        assert report["pass"] is True
        assert report["failed"] == 0
        assert report["total"] == report["passed"]

    def test_nonexistent_module_fails(self):
        bogus = FrameworkMapping(
            category=CATEGORIES[0],
            clause="测试",
            requirement="测试",
            maref_implementation="测试",
            module_path="maref.no.such.module.xyz",
            symbol="Whatever",
            status=STATUS_COVERED,
        )
        result = verify_mapping(bogus)
        assert result["ok"] is False
        assert result["reason"] == "module-not-found"

    def test_nonexistent_symbol_fails(self):
        bogus = FrameworkMapping(
            category=CATEGORIES[0],
            clause="测试",
            requirement="测试",
            maref_implementation="测试",
            module_path="maref.governance.risk_classifier",
            symbol="ThisSymbolDoesNotExist",
            status=STATUS_COVERED,
        )
        result = verify_mapping(bogus)
        assert result["ok"] is False
        assert result["reason"] == "symbol-not-found"

    def test_explicit_missing_reported(self):
        declared = FrameworkMapping(
            category=CATEGORIES[6],
            clause="测试",
            requirement="测试",
            maref_implementation="测试",
            module_path="",
            symbol="",
            status=STATUS_MISSING,
        )
        result = verify_mapping(declared)
        assert result["ok"] is False
        assert result["reason"] == "declared-missing"


class TestCoverageAndGaps:
    """覆盖统计与缺口。"""

    def test_coverage_report_self_consistent(self):
        report = coverage_report()
        assert report["total"] == len(MAPS)
        assert sum(report["by_status"].values()) == len(MAPS)
        # 各分类之和等于总数
        assert sum(
            sum(row.values()) for row in report["by_category"].values()
        ) == len(MAPS)

    def test_gaps_match_non_covered(self):
        expected = [m for m in MAPS if effective_status(m) != STATUS_COVERED]
        assert gaps() == expected
        assert all(effective_status(m) in (STATUS_PARTIAL, STATUS_MISSING) for m in gaps())

    def test_openclaw_only_degrades_when_module_absent(self):
        """闭源依赖模块缺失时，covered 降级为 partial 且路径校验不判失败（单源双仓自洽）。"""
        m = FrameworkMapping(
            category=CATEGORIES[0],
            clause="test",
            requirement="r",
            maref_implementation="i",
            module_path="maref._definitely_absent_module",
            symbol="X",
            status=STATUS_COVERED,
            openclaw_only=True,
        )
        assert effective_status(m) == STATUS_PARTIAL
        result = verify_mapping(m)
        assert result["ok"] is True
        assert result["reason"] == "closed-source-dependency-absent"

    def test_openclaw_only_present_keeps_covered(self):
        """闭源依赖模块存在时维持 covered（开发仓行为不变）。"""
        m = FrameworkMapping(
            category=CATEGORIES[0],
            clause="test",
            requirement="r",
            maref_implementation="i",
            module_path="maref.identity.did_registry",
            symbol="AgentDID",
            status=STATUS_COVERED,
            openclaw_only=True,
        )
        assert effective_status(m) == STATUS_COVERED

    def test_decommission_gap_is_reported(self):
        """第7类停用管理的编排缺口必须如实暴露。"""
        decommission_gaps = [m for m in gaps() if m.category == CATEGORIES[6]]
        assert decommission_gaps, "第7类缺口未被如实标注"


class TestRenderMarkdown:
    """白皮书渲染。"""

    def test_render_is_idempotent(self):
        assert render_markdown() == render_markdown()

    def test_render_contains_title_and_all_categories(self):
        md = render_markdown()
        assert "人工智能安全治理框架 3.0" in md
        for category in CATEGORIES:
            assert category in md

    def test_render_marks_missing_status(self):
        md = render_markdown()
        assert "缺失" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
