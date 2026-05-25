from __future__ import annotations

from maref.integration.feature_dev.doc_ingestor import (
    DeployStage,
    FeatureDocument,
)
from maref.integration.feature_dev.task_generator import TaskGenerator


class TestTaskGenerator:
    def test_generate_with_stages(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tasks = tg.generate()
        assert len(tasks) >= 2
        assert all(t.deploy_stage != DeployStage.UNKNOWN for t in tasks)

    def test_generate_fallback_empty_stages(self) -> None:
        doc = FeatureDocument(title="Empty", raw_path="/tmp/e.md")
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks) == 1
        assert tasks[0].deploy_stage == DeployStage.UNKNOWN

    def test_generate_fallback_no_sections(self) -> None:
        doc = FeatureDocument(title="NoSections", raw_path="/tmp/n.md",
                              stages={DeployStage.MVP: []})
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        assert len(tasks) == 1

    def test_build_criteria_mvp(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tasks = tg.generate()
        mvp_tasks = [t for t in tasks if t.deploy_stage == DeployStage.MVP]
        if mvp_tasks:
            for c in mvp_tasks[0].criteria:
                assert c.target_score == 60.0

    def test_build_criteria_mixed(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tasks = tg.generate()
        mixed_tasks = [t for t in tasks if t.deploy_stage == DeployStage.MIXED]
        if mixed_tasks:
            for c in mixed_tasks[0].criteria:
                assert c.target_score == 80.0

    def test_build_criteria_unknown_stage(self) -> None:
        doc = FeatureDocument(title="X", raw_path="/tmp/x.md")
        tg = TaskGenerator(doc)
        tasks = tg.generate()
        if tasks:
            for c in tasks[0].criteria:
                assert c.target_score == 60.0

    def test_to_research_topics(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tg.generate()
        topics = tg.to_research_topics()
        assert len(topics) > 0
        assert any("Test Feature" in t for t in topics)

    def test_get_initial_research_topic_with_tasks(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tg.generate()
        topic = tg.get_initial_research_topic()
        assert "Test Feature" in topic

    def test_get_initial_research_topic_no_tasks(self) -> None:
        doc = FeatureDocument(title="Lonely", raw_path="/tmp/l.md")
        tg = TaskGenerator(doc)
        topic = tg.get_initial_research_topic()
        assert topic == "Lonely"

    def test_task_id_format(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tasks = tg.generate()
        for t in tasks:
            assert t.task_id.startswith("feature-")

    def test_layer_criterion_five_layers(self, valid_feature_doc: FeatureDocument) -> None:
        tg = TaskGenerator(valid_feature_doc)
        tasks = tg.generate()
        for t in tasks:
            assert len(t.criteria) == 5
