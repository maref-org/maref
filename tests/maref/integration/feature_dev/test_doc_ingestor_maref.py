from __future__ import annotations

from pathlib import Path

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
    _detect_stage,
    _extract_milestones,
    _parse_tables,
)


class TestDeployStage:
    def test_values(self) -> None:
        assert DeployStage.MVP.value == "mvp"
        assert DeployStage.MIXED.value == "mixed"
        assert DeployStage.INTERNALIZATION.value == "internalization"
        assert DeployStage.UNKNOWN.value == "unknown"


class TestTableRow:
    def test_fields(self) -> None:
        row = TableRow(cells=["a", "b"], section_heading="Section 1")
        assert row.cells == ["a", "b"]
        assert row.section_heading == "Section 1"

    def test_to_dict(self) -> None:
        row = TableRow(cells=["x"], section_heading="Test")
        d = row.to_dict()
        assert d["cells"] == ["x"]
        assert d["section"] == "Test"


class TestCostModel:
    def test_defaults(self) -> None:
        cm = CostModel(stage="mvp")
        assert cm.stage == "mvp"
        assert cm.items == {}
        assert cm.total == 0.0

    def test_with_items(self) -> None:
        cm = CostModel(stage="mixed", items={"compute": 100.0}, total=100.0)
        assert cm.items["compute"] == 100.0
        assert cm.total == 100.0

    def test_to_dict(self) -> None:
        cm = CostModel(stage="mvp", items={"storage": 50.0}, total=50.0)
        d = cm.to_dict()
        assert d["stage"] == "mvp"
        assert d["total"] == 50.0


class TestComplianceRule:
    def test_defaults(self) -> None:
        rule = ComplianceRule(
            rule_id="R1", description="test rule", category="daily"
        )
        assert rule.rule_id == "R1"
        assert rule.is_automated is False

    def test_with_automation(self) -> None:
        rule = ComplianceRule(
            rule_id="R2",
            description="auto rule",
            category="weekly",
            is_automated=True,
        )
        assert rule.is_automated is True

    def test_to_dict(self) -> None:
        rule = ComplianceRule(
            rule_id="R1", description="desc", category="daily"
        )
        d = rule.to_dict()
        assert d["rule_id"] == "R1"
        assert d["is_automated"] is False


class TestHypothesis:
    def test_fields(self) -> None:
        h = Hypothesis(
            name="H1",
            method="A/B test",
            pass_threshold="p<0.05",
            fail_criterion="p>=0.05",
        )
        assert h.name == "H1"
        assert h.method == "A/B test"

    def test_to_dict(self) -> None:
        h = Hypothesis(name="H1", method="test", pass_threshold="0.05", fail_criterion="0.05")
        d = h.to_dict()
        assert d["name"] == "H1"


class TestDocumentSection:
    def test_defaults(self) -> None:
        sec = DocumentSection(heading="Intro", level=1, content="Hello")
        assert sec.heading == "Intro"
        assert sec.level == 1
        assert sec.content == "Hello"
        assert sec.subsections == []
        assert sec.milestones == []

    def test_collect_all_reqs(self) -> None:
        child = DocumentSection(
            heading="Child", level=2, content="", requirements=["req1"]
        )
        parent = DocumentSection(
            heading="Parent",
            level=1,
            content="",
            requirements=["req1", "req2"],
            subsections=[child],
        )
        reqs = parent.collect_all_reqs()
        assert len(reqs) == 2
        assert "req1" in reqs
        assert "req2" in reqs

    def test_collect_all_tables(self) -> None:
        child_row = TableRow(cells=["c1"], section_heading="Child")
        child = DocumentSection(
            heading="Child", level=2, content="", table_rows=[child_row]
        )
        parent_row = TableRow(cells=["p1"], section_heading="Parent")
        parent = DocumentSection(
            heading="Parent",
            level=1,
            content="",
            table_rows=[parent_row],
            subsections=[child],
        )
        rows = parent.collect_all_tables()
        assert len(rows) == 2

    def test_to_dict(self) -> None:
        sec = DocumentSection(heading="Test", level=1, content="hello")
        d = sec.to_dict()
        assert d["heading"] == "Test"
        assert d["level"] == 1
        assert d["content_preview"] == "hello"


class TestFeatureDocument:
    def test_defaults(self) -> None:
        doc = FeatureDocument(title="Feature X", raw_path="/path/to/doc.md")
        assert doc.title == "Feature X"
        assert doc.total_requirements == 0
        assert doc.total_milestones == 0

    def test_total_requirements(self) -> None:
        section = DocumentSection(
            heading="S1",
            level=1,
            content="",
            requirements=["r1", "r2"],
        )
        doc = FeatureDocument(
            title="F1",
            raw_path="/p",
            stages={DeployStage.MVP: [section]},
        )
        assert doc.total_requirements == 2

    def test_total_milestones(self) -> None:
        section = DocumentSection(
            heading="S1", level=1, content="", milestones=["m1"]
        )
        doc = FeatureDocument(
            title="F1",
            raw_path="/p",
            stages={DeployStage.MVP: [section]},
        )
        assert doc.total_milestones == 1

    def test_to_dict(self) -> None:
        doc = FeatureDocument(title="F1", raw_path="/p")
        d = doc.to_dict()
        assert d["title"] == "F1"
        assert d["total_requirements"] == 0


class TestFreeFunctions:
    def test_detect_stage_mvp(self) -> None:
        assert _detect_stage("This is mvp phase") == DeployStage.MVP

    def test_detect_stage_internalization(self) -> None:
        assert _detect_stage("进入内化期阶段三") == DeployStage.INTERNALIZATION

    def test_detect_stage_unknown(self) -> None:
        assert _detect_stage("random text without keywords") == DeployStage.UNKNOWN

    def test_extract_milestones_empty(self) -> None:
        assert _extract_milestones("no milestones here") == []

    def test_extract_milestones_with_marker(self) -> None:
        result = _extract_milestones("里程碑：完成第一阶段")
        assert len(result) >= 1
        assert "完成第一阶段" in result[0]

    def test_parse_tables_simple(self) -> None:
        text = "| h1 | h2 |\n|----|----|\n| a  | b  |"
        rows = _parse_tables(text, "Test Section")
        assert len(rows) == 1
        # _parse_tables produces a single cell with k=v pairs
        assert len(rows[0].cells) == 1
        assert "h1=a" in rows[0].cells[0]
        assert "h2=b" in rows[0].cells[0]

    def test_parse_tables_no_table(self) -> None:
        assert _parse_tables("plain text", "Section") == []


class TestMarkdownDocIngestor:
    def test_init(self) -> None:
        ingestor = MarkdownDocIngestor()
        assert ingestor is not None

    def test_raises_on_missing_file(self) -> None:
        ingestor = MarkdownDocIngestor()
        with pytest.raises(FileNotFoundError):
            ingestor.ingest("/tmp/nonexistent_file_12345.md")

    def test_ingest_simple_markdown(self, tmp_path: Path) -> None:
        p = tmp_path / "test-doc.md"
        p.write_text("# Test Doc\n\nHello world")
        ingestor = MarkdownDocIngestor()
        doc = ingestor.ingest(str(p))
        assert doc.title == "Test Doc"
