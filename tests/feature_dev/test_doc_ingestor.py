from __future__ import annotations

from pathlib import Path

import pytest

from maref.integration.feature_dev.doc_ingestor import (
    CostModel,
    DeployStage,
    DocumentSection,
    FeatureDocument,
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


class TestDetectStage:
    def test_mvp_keywords(self) -> None:
        assert _detect_stage("MVP phase 1") == DeployStage.MVP
        assert _detect_stage("wool-mvp design") == DeployStage.MVP
        assert _detect_stage("阶段一 implementation") == DeployStage.MVP

    def test_mixed_keywords(self) -> None:
        assert _detect_stage("混合期 deployment") == DeployStage.MIXED
        assert _detect_stage("阶段二 planning") == DeployStage.MIXED

    def test_internalization_keywords(self) -> None:
        assert _detect_stage("内化期 strategy") == DeployStage.INTERNALIZATION
        assert _detect_stage("IP王国 maturity") == DeployStage.INTERNALIZATION
        assert _detect_stage("阶段三 rollout") == DeployStage.INTERNALIZATION

    def test_unknown(self) -> None:
        assert _detect_stage("random text") == DeployStage.UNKNOWN
        assert _detect_stage("") == DeployStage.UNKNOWN


class TestExtractMilestones:
    def test_milestone_patterns(self) -> None:
        text = "里程碑: Auth module complete\n**里程碑1**: Rate limiting implemented\n- 产出物: Validation pass"
        ms = _extract_milestones(text)
        assert len(ms) >= 2

    def test_empty(self) -> None:
        assert _extract_milestones("no milestones here") == []


class TestExtractRequirements:
    def test_chinese_patterns(self) -> None:
        text = "✅ Must implement JWT verification\n必须完成测试\n需实现审计日志"
        reqs = _extract_requirements(text)
        assert len(reqs) >= 2

    def test_english_patterns(self) -> None:
        text = "must have audit logging\nshall support tenant isolation\nshould handle errors"
        reqs = _extract_requirements(text)
        assert len(reqs) >= 2

    def test_table_rows(self) -> None:
        text = "| 工具 | Cost | Notes |\n|---|---|---|\n| OpenTelemetry | ¥100 | observability |"
        reqs = _extract_requirements(text)
        assert any("工具" in r for r in reqs)

    def test_empty(self) -> None:
        assert _extract_requirements("nothing relevant") == []


class TestExtractChecklists:
    def test_checkbox_patterns(self) -> None:
        text = "- [x] Done task\n- [ ] Pending task\n- [ ] Also todo"
        items = _extract_checklists(text)
        assert len(items) == 3

    def test_empty(self) -> None:
        assert _extract_checklists("no checkboxes") == []


class TestExtractHypotheses:
    def test_table_pattern(self) -> None:
        text = (
            "| **H1** | A/B test | >80% | <50% | Extra |\n"
            "| **H2** | Study | >70% | <40% | Extra |"
        )
        hypos = _extract_hypotheses(text)
        assert len(hypos) >= 1
        assert hypos[0].name == "H1"

    def test_empty(self) -> None:
        assert _extract_hypotheses("no table") == []


class TestExtractHypothesesFromText:
    def test_hypothesis_with_colon(self) -> None:
        text = "| **H1: Core Concept** | A/B | >80% | <50% | Good |"
        hypos = _extract_hypotheses_from_text(text)
        assert len(hypos) == 1
        assert hypos[0].name == "H1"

    def test_empty(self) -> None:
        assert _extract_hypotheses_from_text("no match") == []


class TestExtractHypothesesFromSections:
    def test_recursive(self) -> None:
        sec = DocumentSection(
            heading="Test",
            level=1,
            content="| **H1: Title** | Method | >80% | <50% | Notes |",
        )
        hypos = _extract_hypotheses_from_sections([sec])
        assert len(hypos) == 1
        assert hypos[0].name == "H1"

    def test_nested_sections(self) -> None:
        inner = DocumentSection(heading="Inner", level=3, content="")
        mid = DocumentSection(
            heading="Mid",
            level=2,
            content="| **H2: Sub** | Study | >70% | <40% | Notes |",
            subsections=[inner],
        )
        sec = DocumentSection(heading="Root", level=1, content="", subsections=[mid])
        hypos = _extract_hypotheses_from_sections([sec])
        assert len(hypos) == 1
        assert hypos[0].name == "H2"


class TestExtractComplianceRules:
    def test_numbered_disciplines(self) -> None:
        text = "1. **Security Check**\n2. **Data Privacy**\n- [x] Daily audit"
        rules = _extract_compliance_rules(text)
        assert any(r.description == "Security Check" for r in rules)
        assert any(r.category == "discipline" for r in rules)

    def test_checklist_categories(self) -> None:
        text = "每日自检\n- [x] Morning check\n每周\n- [ ] Weekly sync"
        rules = _extract_compliance_rules(text)
        cats = {r.category for r in rules}
        assert len(cats) >= 1  # at least one category found
        assert any(c in ("daily", "weekly") for c in cats)

    def test_empty(self) -> None:
        assert _extract_compliance_rules("") == []


class TestExtractCostModels:
    def test_cost_table(self) -> None:
        text = "| 成本项 | Tool A | Tool B |\n|---|---|---|\n| **Scene Gen** | ¥500 | ¥300 |\n| **Audio** | ¥200 | ¥150 |"
        models = _extract_cost_models(text)
        assert len(models) >= 2
        assert models[0].stage == "Scene Gen"
        assert models[0].items.get("Tool A", 0) == 500.0

    def test_with_formatted_values(self) -> None:
        text = "| 成本项 | Cost |\n|---|---|\n| **Render** | ¥1,000 |"
        models = _extract_cost_models(text)
        assert len(models) >= 1

    def test_empty(self) -> None:
        assert _extract_cost_models("no cost data") == []


class TestParseTables:
    def test_basic_table(self) -> None:
        text = "| H1 | H2 |\n|---|---|\n| A | B |\n| C | D |"
        rows = _parse_tables(text, "Test")
        assert len(rows) == 2

    def test_no_separator(self) -> None:
        text = "| H1 | H2 |\n| A | B |"
        rows = _parse_tables(text, "Test")
        assert len(rows) == 0

    def test_no_table(self) -> None:
        assert _parse_tables("plain text", "Test") == []


class TestParseMarkdownSections:
    def test_basic_hierarchy(self) -> None:
        text = "# H1\ncontent1\n## H2\ncontent2\n### H3\ncontent3"
        sections = _parse_markdown_sections(text)
        assert len(sections) == 1
        assert sections[0].heading == "H1"
        assert len(sections[0].subsections) == 1
        assert sections[0].subsections[0].heading == "H2"
        assert len(sections[0].subsections[0].subsections) == 1

    def test_multiple_h1(self) -> None:
        text = "# First\n# Second\n## Sub\n"
        sections = _parse_markdown_sections(text)
        assert len(sections) == 2

    def test_empty(self) -> None:
        assert _parse_markdown_sections("") == []
        assert _parse_markdown_sections("\n\n") == []


class TestAssignStagesRecursively:
    def test_assigns_by_heading(self) -> None:
        doc = FeatureDocument(title="Test", raw_path="/tmp/t.md")
        sec = DocumentSection(heading="MVP Phase", level=2, content="content")
        _assign_stages_recursively(doc, [sec])
        assert DeployStage.MVP in doc.stages

    def test_assigns_by_content(self) -> None:
        doc = FeatureDocument(title="Test", raw_path="/tmp/t.md")
        sec = DocumentSection(heading="Generic", level=2, content="This is the 混合期 details")
        _assign_stages_recursively(doc, [sec])
        assert DeployStage.MIXED in doc.stages

    def test_skips_unknown(self) -> None:
        doc = FeatureDocument(title="Test", raw_path="/tmp/t.md")
        sec = DocumentSection(heading="Intro", level=1, content="Welcome")
        _assign_stages_recursively(doc, [sec])
        assert len(doc.stages) == 0


class TestDocumentSection:
    def test_collect_all_reqs_dedup(self) -> None:
        sub = DocumentSection(heading="Sub", level=2, content="", requirements=["req1", "req2"])
        sec = DocumentSection(
            heading="Root", level=1, content="", requirements=["req1", "req3"], subsections=[sub]
        )
        all_reqs = sec.collect_all_reqs()
        assert sorted(all_reqs) == ["req1", "req2", "req3"]

    def test_collect_all_tables(self) -> None:
        sub = DocumentSection(
            heading="Sub",
            level=2,
            content="",
            table_rows=[TableRow(cells=["data"], section_heading="Sub")],
        )
        sec = DocumentSection(heading="Root", level=1, content="", subsections=[sub])
        assert len(sec.collect_all_tables()) == 1

    def test_to_dict_truncation(self) -> None:
        sec = DocumentSection(heading="H", level=1, content="x" * 500)
        d = sec.to_dict()
        assert len(d["content_preview"]) <= 200


class TestFeatureDocument:
    def test_total_requirements_dedup(self) -> None:
        sec1 = DocumentSection(heading="S1", level=2, content="", requirements=["a", "b"])
        sec2 = DocumentSection(heading="S2", level=2, content="", requirements=["b", "c"])
        doc = FeatureDocument(
            title="T",
            raw_path="/tmp/t.md",
            stages={DeployStage.MVP: [sec1], DeployStage.MIXED: [sec2]},
        )
        assert doc.total_requirements == 3

    def test_total_milestones(self) -> None:
        sec = DocumentSection(heading="S", level=2, content="", milestones=["m1", "m2"])
        doc = FeatureDocument(
            title="T",
            raw_path="/tmp/t.md",
            stages={DeployStage.MVP: [sec]},
        )
        assert doc.total_milestones == 2

    def test_to_dict_structure(self) -> None:
        doc = FeatureDocument(title="Test", raw_path="/tmp/t.md")
        d = doc.to_dict()
        assert d["title"] == "Test"
        assert "stages" in d


class TestMarkdownDocIngestor:
    def test_file_not_found(self) -> None:
        ingestor = MarkdownDocIngestor()
        with pytest.raises(FileNotFoundError):
            ingestor.ingest("/nonexistent/path.md")

    def test_ingest_success(self, tmp_path: Path, sample_markdown: str) -> None:
        f = tmp_path / "test.md"
        f.write_text(sample_markdown, encoding="utf-8")
        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest(str(f))
        assert doc.title == "Secure API Gateway"
        assert doc.metadata["section_count"] > 0

    def test_ingest_with_h1_title(self, tmp_path: Path, sample_markdown: str) -> None:
        f = tmp_path / "feature.md"
        f.write_text(sample_markdown, encoding="utf-8")
        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest(str(f))
        assert len(doc.all_sections) > 0

    def test_ingest_empty_doc(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest(str(f))
        assert doc.title == "empty"
        assert doc.metadata["section_count"] == 0


class TestCostModel:
    def test_to_dict(self) -> None:
        cm = CostModel(stage="Test", items={"A": 10.0}, total=10.0)
        d = cm.to_dict()
        assert d["stage"] == "Test"
        assert d["total"] == 10.0


class TestTableRow:
    def test_to_dict(self) -> None:
        tr = TableRow(cells=["a", "b"], section_heading="H")
        d = tr.to_dict()
        assert d["cells"] == ["a", "b"]
        assert d["section"] == "H"
