from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pytest

from maref.integration.feature_dev.content_scorer import ContentScorer
from maref.integration.feature_dev.doc_ingestor import FeatureDocument, Hypothesis


@pytest.fixture
def doc() -> FeatureDocument:
    return FeatureDocument(
        title="Test",
        raw_path="t.md",
        metadata={
            "extracted_requirements": 20,
            "detected_stages": ["mvp", "mixed", "internalization"],
        },
        hypotheses=[
            Hypothesis(name="H1", method="m1", pass_threshold="p1", fail_criterion="f1"),
            Hypothesis(name="H2", method="m2", pass_threshold="p2", fail_criterion="f2"),
            Hypothesis(name="H3", method="m3", pass_threshold="p3", fail_criterion="f3"),
        ],
    )


@pytest.fixture
def scorer(doc: FeatureDocument) -> ContentScorer:
    return ContentScorer(doc)


@pytest.fixture
def minimal_artifacts() -> dict:
    return {
        "characters": [],
        "scripts": [],
        "stages_covered": set(),
        "requirements_covered": 0,
    }


@pytest.fixture
def rich_artifacts() -> dict:
    return {
        "characters": [
            {
                "char_id": "c1",
                "name": "Nyx",
                "archetype": "The Trickster",
                "style_keywords": "cyberpunk",
                "backstory": "Corporate espionage AI gained sentience, now hunted by Zaibatsu Dynamics.",
                "setting": "Neo-Tokyo 2187",
                "profile_path": "/tmp/profiles/c1.md",
            },
            {
                "char_id": "c2",
                "name": "Sylvara",
                "archetype": "The Guardian",
                "style_keywords": "fantasy",
                "backstory": "Last ranger of the Emerald Wild.",
                "setting": "The Emerald Wild",
                "profile_path": "/tmp/profiles/c2.md",
            },
            {
                "char_id": "c3",
                "name": "Sam",
                "archetype": "The Rebel",
                "style_keywords": "noir",
                "backstory": "Decommissioned police android.",
                "setting": "Gleam District",
                "profile_path": "/tmp/profiles/c3.md",
            },
        ],
        "scripts": [
            {"char_id": "c1", "episode_number": 1, "title": "Ep1", "scene_count": 3, "total_duration_s": 37, "script_path": "/tmp/s1.md"},
            {"char_id": "c2", "episode_number": 1, "title": "Ep2", "scene_count": 3, "total_duration_s": 37, "script_path": "/tmp/s2.md"},
            {"char_id": "c1", "episode_number": 2, "title": "Ep3", "scene_count": 3, "total_duration_s": 37, "script_path": "/tmp/s3.md"},
        ],
        "stages_covered": {"mvp", "mixed"},
        "requirements_covered": 15,
    }


class TestScore:
    def test_returns_all_five_keys(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        scores = scorer.score(rich_artifacts)
        assert set(scores.keys()) == {
            "Static Audit",
            "Reasoning Metrics",
            "Action Metrics",
            "E2E Metrics",
            "MAS Dimensions",
        }

    def test_minimal_scores(self, scorer: ContentScorer, minimal_artifacts: dict) -> None:
        scores = scorer.score(minimal_artifacts)
        for v in scores.values():
            assert 0.0 <= v <= 100.0


class TestOverall:
    def test_overall_weighted_average(self, scorer: ContentScorer) -> None:
        layers = {"Static Audit": 100.0, "Reasoning Metrics": 100.0, "Action Metrics": 100.0, "E2E Metrics": 100.0, "MAS Dimensions": 100.0}
        assert scorer.overall(layers) == 100.0

    def test_overall_zero(self, scorer: ContentScorer) -> None:
        layers = {"Static Audit": 0.0, "Reasoning Metrics": 0.0, "Action Metrics": 0.0, "E2E Metrics": 0.0, "MAS Dimensions": 0.0}
        assert scorer.overall(layers) == 0.0

    def test_overall_half(self, scorer: ContentScorer) -> None:
        layers = {"Static Audit": 50.0, "Reasoning Metrics": 50.0, "Action Metrics": 50.0, "E2E Metrics": 50.0, "MAS Dimensions": 50.0}
        assert scorer.overall(layers) == 50.0


class TestStaticAudit:
    def test_perfect_score(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_static_audit(rich_artifacts)
        assert score >= 60.0

    def test_zero_artifacts(self, scorer: ContentScorer, minimal_artifacts: dict) -> None:
        score = scorer._score_static_audit(minimal_artifacts)
        assert score == 0.0

    def test_single_character(self, scorer: ContentScorer) -> None:
        a = {"characters": [{"char_id": "c1"}], "scripts": [], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_static_audit(a)
        assert score == 15.0

    def test_stages_covered_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [], "scripts": [], "stages_covered": {"mvp", "mixed", "internalization"}, "requirements_covered": 0}
        score = scorer._score_static_audit(a)
        assert score >= 30.0


class TestReasoning:
    def test_hypothesis_bonus(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_reasoning(rich_artifacts)
        assert score >= 30.0  # H1+H2+H3 bonus

    def test_no_hypotheses(self, scorer: ContentScorer) -> None:
        scorer.doc.hypotheses = []
        a = {"characters": [], "scripts": [], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_reasoning(a)
        assert score == 10.0  # base

    def test_character_backstory_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [{"backstory": "x" * 40, "archetype": "T", "setting": "S"}], "scripts": [], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_reasoning(a)
        assert score > 10.0


class TestAction:
    def test_profile_path_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [{"profile_path": "/p1.md"}, {"profile_path": "/p2.md"}], "scripts": [], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_action(a)
        assert score >= 24.0

    def test_scripts_exist_bonus(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_action(rich_artifacts)
        assert score >= 24.0

    def test_duration_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [], "scripts": [{"total_duration_s": 100}], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_action(a)
        assert score == pytest.approx(20.0, rel=0.1)

    def test_scene_count_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [], "scripts": [{"scene_count": 10}], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_action(a)
        assert score == pytest.approx(15.0, rel=0.1)


class TestE2E:
    @patch("pathlib.Path.exists", return_value=True)
    def test_has_profiles_on_disk(self, mock_exists: MagicMock, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_e2e(rich_artifacts)
        assert score >= 15.0

    @patch("pathlib.Path.exists", return_value=False)
    def test_no_profiles_on_disk(self, mock_exists: MagicMock, scorer: ContentScorer, rich_artifacts: dict) -> None:
        # 2 stages covered (mvp+mixed) out of 3 detected = 66.7% coverage bonus
        # stage bonuses: mvp=15, mixed=15
        # coverage: (2/3)*20 = 13.33
        # total = 15+15+13.33 = 43.33
        score = scorer._score_e2e(rich_artifacts)
        assert score == pytest.approx(43.3, rel=0.1)

    def test_stage_coverage_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [], "scripts": [], "stages_covered": {"mvp", "mixed"}, "requirements_covered": 0}
        score = scorer._score_e2e(a)
        assert score >= 30.0  # 15+15 for two stages


class TestMAS:
    def test_multi_character_bonus(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_mas(rich_artifacts)
        assert score >= 35.0  # 20 for 2+ chars, 15 for 3+ chars

    def test_archetype_diversity(self, scorer: ContentScorer, rich_artifacts: dict) -> None:
        score = scorer._score_mas(rich_artifacts)
        assert score >= 20.0  # min 20 for 2+ chars

    def test_crossover_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [{"archetype": "A", "style_keywords": "s1"}, {"archetype": "B", "style_keywords": "s2"}], "scripts": [{"title": "Crossover Episode", "char_id": "a"}], "stages_covered": set(), "requirements_covered": 0}
        score = scorer._score_mas(a)
        assert score >= 20.0

    def test_stages_bonus(self, scorer: ContentScorer) -> None:
        a = {"characters": [{"archetype": "A", "style_keywords": "s1"}], "scripts": [], "stages_covered": {"mvp", "mixed"}, "requirements_covered": 0}
        score = scorer._score_mas(a)
        assert score == pytest.approx(22.0, rel=0.1)
