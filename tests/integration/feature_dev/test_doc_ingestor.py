from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from maref.integration.feature_dev.doc_ingestor import (
    ComplianceRule,
    CostModel,
    DeployStage,
    DocumentSection,
    FeatureDocument,
    Hypothesis,
    MarkdownDocIngestor,
    TableRow,
    _assign_stages_recursively,
    _detect_stage,
    _extract_checklists,
    _extract_compliance_rules,
    _extract_cost_models,
    _extract_hypotheses,
    _extract_hypotheses_from_sections,
    _extract_hypotheses_from_text,
    _extract_milestones,
    _extract_requirements,
    _parse_markdown_sections,
    _parse_tables,
)


class TestDeployStage:
    def test_values(self) -> None:
        assert DeployStage.MVP.value == "mvp"
        assert DeployStage.MIXED.value == "mixed"
        assert DeployStage.INTERNALIZATION.value == "internalization"
        assert DeployStage.UNKNOWN.value == "unknown"

    def test_is_str_enum(self) -> None:
        assert isinstance(DeployStage.MVP, str)
        assert DeployStage.MVP == "mvp"


class TestDataClasses:
    def test_table_row(self) -> None:
        row = TableRow(cells=["a", "b"], section_heading="Test")
        d = row.to_dict()
        assert d["cells"] == ["a", "b"]
        assert d["section"] == "Test"

    def test_cost_model(self) -> None:
        cm = CostModel(stage="MVP", items={"dev": 100.0}, total=100.0)
        d = cm.to_dict()
        assert d["stage"] == "MVP"
        assert d["items"] == {"dev": 100.0}
        assert d["total"] == 100.0

    def test_cost_model_empty(self) -> None:
        cm = CostModel(stage="MVP")
        assert cm.items == {}
        assert cm.total == 0.0

    def test_compliance_rule(self) -> None:
        r = ComplianceRule(rule_id="r1", description="Test", category="daily", is_automated=True)
        d = r.to_dict()
        assert d["rule_id"] == "r1"
        assert d["is_automated"] is True
        assert d["category"] == "daily"

    def test_compliance_rule_defaults(self) -> None:
        r = ComplianceRule(rule_id="r2", description="Manual", category="discipline")
        assert r.is_automated is False

    def test_hypothesis(self) -> None:
        h = Hypothesis(name="H1", method="A/B test", pass_threshold=">80%", fail_criterion="<50%")
        d = h.to_dict()
        assert d["name"] == "H1"
        assert d["pass_threshold"] == ">80%"


class TestDocumentSection:
    def test_collect_all_reqs_dedup(self) -> None:
        sec = DocumentSection(
            heading="Test",
            level=1,
            content="",
            requirements=["req1", "req2", "req1"],
        )
        assert sec.collect_all_reqs() == ["req1", "req2"]

    def test_collect_all_reqs_recursive(self) -> None:
        sub = DocumentSection(heading="Sub", level=2, content="", requirements=["sub_req"])
        sec = DocumentSection(
            heading="Root", level=1, content="", requirements=["root_req"], subsections=[sub]
        )
        assert sec.collect_all_reqs() == ["root_req", "sub_req"]

    def test_collect_all_tables(self) -> None:
        sub = DocumentSection(
            heading="Sub",
            level=2,
            content="",
            table_rows=[TableRow(cells=["sub"], section_heading="Sub")],
        )
        sec = DocumentSection(
            heading="Root",
            level=1,
            content="",
            table_rows=[TableRow(cells=["root"], section_heading="Root")],
            subsections=[sub],
        )
        rows = sec.collect_all_tables()
        assert len(rows) == 2
        assert rows[0].cells == ["root"]
        assert rows[1].cells == ["sub"]

    def test_to_dict_truncates(self) -> None:
        sec = DocumentSection(heading="H", level=1, content="x" * 500, requirements=["r"] * 30)
        d = sec.to_dict()
        assert d["heading"] == "H"
        assert len(d["requirements"]) == 20
        assert d["content_preview"] == "x" * 200


class TestFeatureDocument:
    def test_total_requirements_dedup_across_stages(self) -> None:
        s1 = DocumentSection(heading="S1", level=1, content="", requirements=["r1", "r2"])
        s2 = DocumentSection(heading="S2", level=1, content="", requirements=["r2", "r3"])
        doc = FeatureDocument(title="Test", raw_path="test.md")
        doc.stages[DeployStage.MVP] = [s1]
        doc.stages[DeployStage.MIXED] = [s2]
        assert doc.total_requirements == 3

    def test_total_milestones_includes_subsections(self) -> None:
        sub = DocumentSection(heading="Sub", level=2, content="", milestones=["m2"])
        sec = DocumentSection(
            heading="Root", level=1, content="", milestones=["m1"], subsections=[sub]
        )
        doc = FeatureDocument(title="Test", raw_path="test.md")
        doc.stages[DeployStage.MVP] = [sec]
        assert doc.total_milestones == 2

    def test_to_dict_structure(self) -> None:
        doc = FeatureDocument(title="T", raw_path="p.md")
        d = doc.to_dict()
        assert d["title"] == "T"
        assert d["raw_path"] == "p.md"
        assert "stages" in d
        assert "total_requirements" in d

    def test_empty_document(self) -> None:
        doc = FeatureDocument(title="Empty", raw_path="empty.md")
        assert doc.total_requirements == 0
        assert doc.total_milestones == 0
        assert doc.to_dict()["total_requirements"] == 0


class TestDetectStage:
    def test_mvp_keywords(self) -> None:
        assert _detect_stage("MVP plan") == DeployStage.MVP
        assert _detect_stage("wool-mvp design") == DeployStage.MVP
        assert _detect_stage("阶段一部署") == DeployStage.MVP
        assert _detect_stage("Phase 1 delivery") == DeployStage.MVP
        assert _detect_stage("0-4周 快速迭代") == DeployStage.MVP

    def test_mixed_keywords(self) -> None:
        assert _detect_stage("混合期 strategy") == DeployStage.MIXED
        assert _detect_stage("阶段二 expansion") == DeployStage.MIXED
        assert _detect_stage("Phase 2 scale") == DeployStage.MIXED
        assert _detect_stage("1-3个月 增长") == DeployStage.MIXED

    def test_internalization_keywords(self) -> None:
        assert _detect_stage("内化期 build") == DeployStage.INTERNALIZATION
        assert _detect_stage("IP王国规划") == DeployStage.INTERNALIZATION
        assert _detect_stage("阶段三 maturity") == DeployStage.INTERNALIZATION
        assert _detect_stage("Phase 3 optimize") == DeployStage.INTERNALIZATION
        assert _detect_stage("3-12个月 深化") == DeployStage.INTERNALIZATION

    def test_unknown(self) -> None:
        assert _detect_stage("Introduction") == DeployStage.UNKNOWN
        assert _detect_stage("随便写写") == DeployStage.UNKNOWN
        assert _detect_stage("") == DeployStage.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert _detect_stage("Mvp") == DeployStage.MVP
        assert _detect_stage("mVP") == DeployStage.MVP


class TestExtractMilestones:
    def test_milestone_pattern(self) -> None:
        text = "里程碑：完成原型设计"
        assert _extract_milestones(text) == ["完成原型设计"]

    def test_milestone_english(self) -> None:
        text = "milestone: Launch v1.0"
        assert _extract_milestones(text) == ["Launch v1.0"]

    def test_heading_based(self) -> None:
        text = "## 阶段一: Foundation"
        assert "Foundation" in _extract_milestones(text)[0]

    def test_bullet_with_deliverable(self) -> None:
        text = "- 阶段目标：Q3 launch"
        ms = _extract_milestones(text)
        assert any("Q3 launch" in m for m in ms)

    def test_no_milestones(self) -> None:
        assert _extract_milestones("Just some text.") == []


class TestParseTables:
    def test_simple_table(self) -> None:
        md = textwrap.dedent("""
            | Header A | Header B |
            |----------|----------|
            | Cell 1   | Cell 2   |
        """).strip()
        rows = _parse_tables(md, "Test Section")
        assert len(rows) == 1
        assert "Header A=Cell 1" in rows[0].cells[0]
        assert "Header B=Cell 2" in rows[0].cells[0]

    def test_multiple_rows(self) -> None:
        md = textwrap.dedent("""
            | Col1 | Col2 |
            |------|------|
            | A    | B    |
            | C    | D    |
        """).strip()
        rows = _parse_tables(md, "Test")
        assert len(rows) == 2

    def test_no_table(self) -> None:
        assert _parse_tables("Plain text with no pipes", "Test") == []

    def test_malformed_table_missing_separator(self) -> None:
        md = textwrap.dedent("""
            | A | B |
            | C | D |
        """).strip()
        rows = _parse_tables(md, "Test")
        assert len(rows) == 0

    def test_table_in_context(self) -> None:
        md = "Some text\n\n| Key | Value |\n|-----|-------|\n| X   | 1     |\n\nMore text"
        rows = _parse_tables(md, "Section")
        assert len(rows) == 1


class TestExtractRequirements:
    def test_must_keyword(self) -> None:
        reqs = _extract_requirements("必须实现用户登录。")
        assert any("实现用户登录" in r for r in reqs)

    def test_checkmark(self) -> None:
        reqs = _extract_requirements("✅ 完成数据验证\n")
        assert any("完成数据验证" in r for r in reqs)

    def test_should_keyword(self) -> None:
        reqs = _extract_requirements("should handle errors gracefully\n")
        assert any("handle errors gracefully" in r for r in reqs)

    def test_table_as_requirement(self) -> None:
        md = "| 用途 | 内容生成 | 视频剪辑 |"
        reqs = _extract_requirements(md)
        assert any("用途" in r for r in reqs)

    def test_non_requirement_text(self) -> None:
        reqs = _extract_requirements("This is just a normal sentence without trigger words.")
        assert len(reqs) == 0

    def test_mixed_content(self) -> None:
        md = "必须加密。\n需实现缓存。\nSome normal text."
        reqs = _extract_requirements(md)
        assert len(reqs) >= 2


class TestExtractChecklists:
    def test_checked(self) -> None:
        items = _extract_checklists("- [x] Done task")
        assert items == ["Done task"]

    def test_unchecked(self) -> None:
        items = _extract_checklists("- [ ] Pending task")
        assert items == ["Pending task"]

    def test_no_checklist(self) -> None:
        assert _extract_checklists("Just text") == []

    def test_multiple(self) -> None:
        md = "- [x] Task 1\n- [ ] Task 2\n- [x] Task 3"
        items = _extract_checklists(md)
        assert items == ["Task 1", "Task 2", "Task 3"]


class TestExtractHypotheses:
    def test_format_with_double_asterisk(self) -> None:
        md = "| **H1** | A/B test | >80% | <50% | some |"
        hypos = _extract_hypotheses(md)
        assert len(hypos) == 1
        assert hypos[0].name == "H1"
        assert hypos[0].method == "A/B test"
        assert hypos[0].pass_threshold == ">80%"
        assert hypos[0].fail_criterion == "<50%"

    def test_format_with_name_after_colon(self) -> None:
        md = "| **H1: Engagement** | survey | >70% | <40% |"
        hypos = _extract_hypotheses_from_text(md)
        assert len(hypos) == 1
        assert hypos[0].name == "H1"

    def test_no_hypotheses(self) -> None:
        assert _extract_hypotheses("No table here") == []


class TestExtractComplianceRules:
    def test_numbered_bold_items(self) -> None:
        md = "1. **Daily Standup**"
        rules = _extract_compliance_rules(md)
        assert any("Daily Standup" in r.description for r in rules)
        assert any(r.category == "discipline" for r in rules)

    def test_checklist_rules(self) -> None:
        md = "- [ ] Code review"
        rules = _extract_compliance_rules(md)
        assert any("Code review" in r.description for r in rules)

    def test_category_tracking(self) -> None:
        md = "每日自检\n- [ ] Morning check"
        rules = _extract_compliance_rules(md)
        daily_rules = [r for r in rules if r.category == "daily"]
        assert len(daily_rules) >= 1

    def test_no_duplicates(self) -> None:
        md = "1. **Same Rule**\n1. **Same Rule**"
        rules = _extract_compliance_rules(md)
        assert len([r for r in rules if "Same Rule" in r.description]) == 1


class TestExtractCostModels:
    def test_basic_cost_model(self) -> None:
        md = textwrap.dedent("""
            | 成本项 | 人力 | 资源 |
            |-------|------|------|
            | MVP   | ¥100 | ¥200 |
        """).strip()
        models = _extract_cost_models(md)
        assert len(models) == 1
        assert models[0].stage == "MVP"
        assert models[0].items.get("人力") == 100.0
        assert models[0].total == 300.0

    def test_multiple_stages(self) -> None:
        md = textwrap.dedent("""
            | 成本项 | Dev |
            |-------|-----|
            | MVP   | 100 |
            | Mixed | 200 |
        """).strip()
        models = _extract_cost_models(md)
        assert len(models) == 2

    def test_no_cost_table(self) -> None:
        assert _extract_cost_models("No cost data") == []

    def test_skip_separator_row(self) -> None:
        md = textwrap.dedent("""
            | 成本项 | Cost |
            |-------|------|
            |---|---|
            | MVP   | 100  |
        """).strip()
        models = _extract_cost_models(md)
        assert len(models) == 1


class TestParseMarkdownSections:
    def test_simple_section(self) -> None:
        md = "# Title\nContent here"
        sections = _parse_markdown_sections(md)
        assert len(sections) == 1
        assert sections[0].heading == "Title"
        assert sections[0].level == 1

    def test_nested_sections(self) -> None:
        md = textwrap.dedent("""
            # H1
            ## H2
            ### H3
        """).strip()
        sections = _parse_markdown_sections(md)
        assert len(sections) == 1
        assert sections[0].heading == "H1"
        assert len(sections[0].subsections) == 1
        assert sections[0].subsections[0].heading == "H2"
        assert len(sections[0].subsections[0].subsections) == 1
        assert sections[0].subsections[0].subsections[0].heading == "H3"

    def test_multiple_top_level(self) -> None:
        md = "# First\n\n# Second"
        sections = _parse_markdown_sections(md)
        assert len(sections) == 2

    def test_heading_level_change(self) -> None:
        md = "# H1\n## H2\n# Another H1"
        sections = _parse_markdown_sections(md)
        assert len(sections) == 2
        assert sections[0].heading == "H1"
        assert sections[1].heading == "Another H1"

    def test_content_assigned_to_section(self) -> None:
        md = "# Section\nSome body text\nMore text"
        sections = _parse_markdown_sections(md)
        assert "Some body text" in sections[0].content
        assert "More text" in sections[0].content

    def test_empty_content(self) -> None:
        sections = _parse_markdown_sections("")
        assert sections == []


class TestAssignStagesRecursively:
    def test_assign_by_heading(self) -> None:
        sec = DocumentSection(heading="MVP Phase", level=1, content="Details")
        doc = FeatureDocument(title="T", raw_path="p.md")
        _assign_stages_recursively(doc, [sec])
        assert DeployStage.MVP in doc.stages
        assert doc.stages[DeployStage.MVP] == [sec]

    def test_assign_by_content_when_heading_unknown(self) -> None:
        sec = DocumentSection(heading="Generic", level=1, content="MVP requirements here")
        doc = FeatureDocument(title="T", raw_path="p.md")
        _assign_stages_recursively(doc, [sec])
        assert DeployStage.MVP in doc.stages

    def test_nested_stage_assignment(self) -> None:
        sub = DocumentSection(heading="混合期 details", level=2, content="")
        sec = DocumentSection(
            heading="Parent", level=1, content="", subsections=[sub]
        )
        doc = FeatureDocument(title="T", raw_path="p.md")
        _assign_stages_recursively(doc, [sec])
        assert DeployStage.MIXED in doc.stages

    def test_unknown_not_added(self) -> None:
        sec = DocumentSection(heading="Random", level=1, content="Plain text")
        doc = FeatureDocument(title="T", raw_path="p.md")
        _assign_stages_recursively(doc, [sec])
        assert len(doc.stages) == 0


class TestMarkdownDocIngestor:
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.resolve")
    def test_ingest_basic(
        self,
        mock_resolve: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        mock_resolve.return_value = Path("/resolved/test.md")
        mock_read.return_value = textwrap.dedent("""\
            # Test Feature

            ## MVP Phase

            must implement login。

            - [x] Auth done

            | Key | Value |
            |-----|-------|
            | CPU | 2     |
        """)

        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest("test.md")
        assert doc.title == "Test Feature"
        assert doc.total_requirements >= 1
        assert len(doc.all_sections) >= 1
        assert len(doc.all_sections[0].subsections) >= 1

    @patch("pathlib.Path.exists", return_value=False)
    def test_ingest_file_not_found(self, mock_exists: MagicMock) -> None:
        ingestor = MarkdownDocIngestor()
        with pytest.raises(FileNotFoundError):
            ingestor.ingest("nonexistent.md")

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.resolve")
    def test_ingest_title_from_first_line(
        self,
        mock_resolve: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        mock_resolve.return_value = Path("/resolved/untitled.md")
        mock_read.return_value = "# Custom Title\nContent"

        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest("untitled.md")
        assert doc.title == "Custom Title"

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.resolve")
    def test_ingest_with_stages_and_hypotheses(
        self,
        mock_resolve: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        mock_resolve.return_value = Path("/resolved/doc.md")
        mock_read.return_value = textwrap.dedent("""\
            # Feature

            ## MVP — 0-4周
            Content for mvp.

            ## 混合期 阶段二
            Content for mixed.

            ## 内化期 IP王国
            Content for internalization.

            ### Hypotheses
            | **H1: Engagement** | A/B test | >80% | <50% |
        """)

        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest("doc.md")
        assert DeployStage.MVP in doc.stages
        assert DeployStage.MIXED in doc.stages
        assert DeployStage.INTERNALIZATION in doc.stages
        assert len(doc.hypotheses) >= 1
        assert "mvp" in doc.metadata.get("detected_stages", [])
        assert doc.metadata.get("hypotheses_found", 0) >= 1

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.resolve")
    def test_ingest_metadata_fields(
        self,
        mock_resolve: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        mock_resolve.return_value = Path("/resolved/doc.md")
        mock_read.return_value = textwrap.dedent("""\
            # Feature
            ## MVP
            must implement login。
        """)

        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest("doc.md")
        assert doc.metadata["char_count"] > 0
        assert doc.metadata["section_count"] >= 1
        assert "mvp" in doc.metadata["detected_stages"]
        assert doc.metadata["extracted_requirements"] >= 1


class TestExtractHypothesesFromSections:
    def test_walks_nested_sections(self) -> None:
        sub = DocumentSection(
            heading="Test",
            level=2,
            content="| **H1: Alpha** | m1 | p1 | f1 |",
        )
        sec = DocumentSection(heading="Root", level=1, content="", subsections=[sub])
        hypos = _extract_hypotheses_from_sections([sec])
        assert len(hypos) == 1
        assert hypos[0].name == "H1"

    def test_deep_nested(self) -> None:
        s3 = DocumentSection(
            heading="L3", level=3,
            content="| **H1: A** | m | p | f |",
        )
        s2 = DocumentSection(heading="L2", level=2, content="", subsections=[s3])
        s1 = DocumentSection(heading="L1", level=1, content="", subsections=[s2])
        hypos = _extract_hypotheses_from_sections([s1])
        assert len(hypos) == 1

    def test_no_hypotheses(self) -> None:
        sec = DocumentSection(heading="Empty", level=1, content="No hypotheses")
        assert _extract_hypotheses_from_sections([sec]) == []
