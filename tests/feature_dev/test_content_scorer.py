from __future__ import annotations

from typing import Any
from unittest.mock import patch

from maref.integration.feature_dev.content_scorer import ContentScorer
from maref.integration.feature_dev.doc_ingestor import (
    FeatureDocument,
    Hypothesis,
)


def _doc(**overrides: Any) -> FeatureDocument:
    base = {
        "title": "Test",
        "raw_path": "/tmp/t.md",
        "metadata": {"extracted_requirements": 10, "detected_stages": ["mvp", "mixed"]},
    }
    base.update(overrides)
    return FeatureDocument(**base)


class TestContentScorer:
    def test_static_audit_scales_with_content(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        base: dict[str, Any] = {"characters": [], "scripts": [], "stages_covered": set(),
                                "requirements_covered": 0}
        assert scorer._score_static_audit(base) == 0.0

        filled = {"characters": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                  "scripts": [{"title": str(i)} for i in range(5)],
                  "stages_covered": {"mvp", "mixed", "internalization"},
                  "requirements_covered": 10}
        assert scorer._score_static_audit(filled) == 100.0

    def test_static_audit_capped(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        many = {"characters": [{"name": str(i)} for i in range(20)],
                "scripts": [{"title": str(i)} for i in range(50)],
                "stages_covered": {"mvp", "mixed", "internalization"},
                "requirements_covered": 999}
        assert scorer._score_static_audit(many) <= 100.0

    def test_reasoning_scores_backstory(self) -> None:
        doc = _doc(hypotheses=[Hypothesis(name="H1", method="M", pass_threshold="P", fail_criterion="F"),
                               Hypothesis(name="H2", method="M", pass_threshold="P", fail_criterion="F")])
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {"characters": [{"backstory": "x" * 50, "archetype": "T", "setting": "S"}],
                             "scripts": [{"title": "1"}, {"title": "2"}]}
        score = scorer._score_reasoning(a)
        assert score > 10.0

    def test_reasoning_minimum_base(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        assert scorer._score_reasoning({"characters": [], "scripts": []}) == 10.0

    def test_action_paths_and_duration(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [{"profile_path": "/tmp/p1.md"}, {"profile_path": "/tmp/p2.md"}],
            "scripts": [{"script_path": "/tmp/s1.md"}, {"script_path": "/tmp/s2.md"}],
            "stages_covered": {"mvp"},
        }
        # No duration or scene_count — all from paths and stage count
        score = scorer._score_action(a)
        assert 20.0 <= score <= 100.0

    def test_action_capped(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [{"profile_path": str(i)} for i in range(10)],
            "scripts": [{"script_path": str(i), "total_duration_s": 100, "scene_count": 10}
                        for i in range(10)],
            "stages_covered": {"mvp", "mixed", "internalization"},
        }
        assert scorer._score_action(a) <= 100.0

    @patch("maref.integration.feature_dev.content_scorer.Path.exists")
    def test_e2e_with_disk_present(self, mock_exists: Any) -> None:
        mock_exists.return_value = True
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [{"profile_path": "/tmp/p1.md"}],
            "scripts": [{"script_path": "/tmp/s1.md"}, {"script_path": "/tmp/s2.md"}],
            "stages_covered": {"mvp", "mixed"},
        }
        score = scorer._score_e2e(a)
        assert score >= 15.0

    @patch("maref.integration.feature_dev.content_scorer.Path.exists")
    def test_e2e_no_disk(self, mock_exists: Any) -> None:
        mock_exists.return_value = False
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [{"profile_path": "/nonexistent/p1.md"}],
            "scripts": [{"script_path": "/nonexistent/s1.md"}],
            "stages_covered": set(),
        }
        score = scorer._score_e2e(a)
        assert score == 0.0

    def test_mas_diversity(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [
                {"archetype": "A", "style_keywords": "cyberpunk"},
                {"archetype": "B", "style_keywords": "fantasy"},
                {"archetype": "C", "style_keywords": "noir"},
            ],
        }
        with_1 = scorer._score_mas(a)
        assert with_1 >= 35.0  # 3 chars = 20+15=35, 3 archetypes = 21, 3 styles = 15 (capped)

    def test_mas_crossover_bonus(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        a: dict[str, Any] = {
            "characters": [{"archetype": "A", "style_keywords": "s"}, {"archetype": "B", "style_keywords": "t"}],
            "scripts": [{"title": "Crossover: Worlds Collide"}, {"title": "Episode 2"}],
            "stages_covered": {"mvp", "mixed"},
        }
        score = scorer._score_mas(a)
        assert score > 30.0

    def test_overall_weighted(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        layers = {"Static Audit": 100.0, "Reasoning Metrics": 50.0,
                  "Action Metrics": 60.0, "E2E Metrics": 70.0, "MAS Dimensions": 80.0}
        score = scorer.overall(layers)
        expected = round(100 * 0.15 + 50 * 0.20 + 60 * 0.25 + 70 * 0.20 + 80 * 0.20, 1)
        assert score == expected

    def test_overall_empty_defaults(self) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        assert scorer.overall({}) == 0.0

    def test_score_returns_all_five(self, sample_artifacts: dict[str, Any]) -> None:
        doc = _doc()
        scorer = ContentScorer(doc)
        scores = scorer.score(sample_artifacts)
        assert set(scores.keys()) == {"Static Audit", "Reasoning Metrics", "Action Metrics",
                                       "E2E Metrics", "MAS Dimensions"}
