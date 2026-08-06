from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.integration.feature_dev.doc_ingestor import (
    DeployStage,
    FeatureDocument,
)
from maref.integration.feature_dev.task_generator import (
    FeatureTask,
    LayerCriterion,
    TaskGenerator,
)


class TestLayerCriterion:
    def test_defaults(self) -> None:
        c = LayerCriterion(layer_number=1, layer_name="Static Audit")
        assert c.target_score == 80.0
        assert c.weight == 1.0
        assert c.eval_prompt == ""

    def test_custom(self) -> None:
        c = LayerCriterion(
            layer_number=2,
            layer_name="Reasoning",
            target_score=90.0,
            weight=2.0,
            eval_prompt="Evaluate reasoning",
        )
        assert c.target_score == 90.0
        assert c.weight == 2.0
        assert c.eval_prompt == "Evaluate reasoning"


class TestFeatureTask:
    def test_defaults(self) -> None:
        task = FeatureTask(
            task_id="t1",
            title="Test",
            description="Desc",
            deploy_stage=DeployStage.MVP,
            source_section="Sec",
        )
        assert task.criteria == []
        assert task.subtasks == []
        assert task.dependencies == []

    def test_full_construction(self) -> None:
        crit = LayerCriterion(layer_number=1, layer_name="SA")
        task = FeatureTask(
            task_id="t2",
            title="Full",
            description="Full desc",
            deploy_stage=DeployStage.MIXED,
            source_section="Sec",
            criteria=[crit],
            subtasks=["sub1"],
            dependencies=["dep1"],
        )
        assert task.task_id == "t2"
        assert task.deploy_stage == DeployStage.MIXED
        assert len(task.criteria) == 1
        assert task.subtasks == ["sub1"]
        assert task.dependencies == ["dep1"]


def _make_doc_with_stages(
    stages: dict[DeployStage, list],
    title: str = "TestFeature",
) -> FeatureDocument:
    doc = FeatureDocument(title=title, raw_path=f"{title}.md")
    for stage, sections in stages.items():
        doc.stages[stage] = sections
    doc.all_sections = []
    for sec_list in stages.values():
        doc.all_sections.extend(sec_list)
    return doc


class TestTaskGeneratorGenerate:
    def test_generates_tasks_for_all_stages(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        mvp_sec = MagicMock(spec=DocumentSection)
        mvp_sec.heading = "MVP"
        mvp_sec.requirements = ["req1"]
        mvp_sec.milestones = ["m1"]

        mixed_sec = MagicMock(spec=DocumentSection)
        mixed_sec.heading = "Mixed"
        mixed_sec.requirements = ["req2"]
        mixed_sec.milestones = ["m2"]

        doc = _make_doc_with_stages({
            DeployStage.MVP: [mvp_sec],
            DeployStage.MIXED: [mixed_sec],
        })

        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks) == 2
        stage_values = {t.deploy_stage for t in tasks}
        assert DeployStage.MVP in stage_values
        assert DeployStage.MIXED in stage_values

    def test_fallback_when_no_stages(self) -> None:
        doc = _make_doc_with_stages({})
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks) == 1
        assert tasks[0].deploy_stage == DeployStage.UNKNOWN
        assert "fallback" in tasks[0].task_id

    def test_build_criteria_mvp(self) -> None:
        doc = _make_doc_with_stages({})
        tg = TaskGenerator(doc)
        criteria = tg._build_criteria(DeployStage.MVP)
        assert len(criteria) == 5
        assert all(c.target_score == 60.0 for c in criteria)
        names = [c.layer_name for c in criteria]
        assert "Static Audit" in names
        assert "MAS Dimensions" in names

    def test_build_criteria_mixed(self) -> None:
        doc = _make_doc_with_stages({})
        tg = TaskGenerator(doc)
        criteria = tg._build_criteria(DeployStage.MIXED)
        assert all(c.target_score == 80.0 for c in criteria)

    def test_build_criteria_internalization(self) -> None:
        doc = _make_doc_with_stages({})
        tg = TaskGenerator(doc)
        criteria = tg._build_criteria(DeployStage.INTERNALIZATION)
        assert all(c.target_score == 90.0 for c in criteria)

    def test_to_research_topics(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        sec = MagicMock(spec=DocumentSection)
        sec.heading = "MVP"
        sec.requirements = ["req"]
        sec.milestones = ["m"]

        doc = _make_doc_with_stages({DeployStage.MVP: [sec]})
        tg = TaskGenerator(doc)
        tg.generate()
        topics = tg.to_research_topics()
        assert len(topics) >= 1

    def test_get_initial_research_topic(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        sec = MagicMock(spec=DocumentSection)
        sec.heading = "MVP"
        sec.requirements = ["req"]
        sec.milestones = ["m1", "m2", "m3"]

        doc = _make_doc_with_stages({DeployStage.MVP: [sec]}, title="MyFeature")
        tg = TaskGenerator(doc)
        tg.generate()
        topic = tg.get_initial_research_topic()
        assert "MyFeature" in topic

    def test_get_initial_research_topic_no_tasks(self) -> None:
        doc = _make_doc_with_stages({}, title="EmptyFeature")
        tg = TaskGenerator(doc)
        topic = tg.get_initial_research_topic()
        assert topic == "EmptyFeature"

    def test_build_stage_task_title_format(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        sec = MagicMock(spec=DocumentSection)
        sec.heading = "MVP Section"
        sec.requirements = ["a", "b"]
        sec.milestones = ["m1"]

        doc = _make_doc_with_stages({DeployStage.MVP: [sec]}, title="Alpha")
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks) == 1
        assert "Alpha" in tasks[0].title
        assert "MVP" in tasks[0].title

    def test_subtasks_from_milestones(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        sec = MagicMock(spec=DocumentSection)
        sec.heading = "MVP"
        sec.requirements = []
        sec.milestones = ["m1", "m2", "m3", "m4"]

        doc = _make_doc_with_stages({DeployStage.MVP: [sec]})
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks[0].subtasks) == 4

    def test_description_includes_counts(self) -> None:
        from maref.integration.feature_dev.doc_ingestor import DocumentSection

        sec = MagicMock(spec=DocumentSection)
        sec.heading = "MVP"
        sec.requirements = ["r1", "r2"]
        sec.milestones = ["m1"]

        doc = _make_doc_with_stages({DeployStage.MVP: [sec]})
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert "Milestones: 1" in tasks[0].description
