from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.integration.feature_dev.content_producer import (
    ASSET_BASE,
    ContentProducer,
    _THEME_SEED,
)
from maref.integration.feature_dev.doc_ingestor import FeatureDocument


@pytest.fixture
def doc() -> FeatureDocument:
    return FeatureDocument(title="TestFeature", raw_path="test.md", metadata={"extracted_requirements": 30})


@pytest.fixture
def producer(doc: FeatureDocument) -> ContentProducer:
    return ContentProducer(doc)


class TestBaselineProduce:
    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    @patch.object(ContentProducer, "_build_character")
    @patch.object(ContentProducer, "_build_script")
    def test_produce_baseline_first_cycle(
        self,
        mock_script: MagicMock,
        mock_char: MagicMock,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        mock_char.side_effect = [
            {"char_id": "cyberpunk-neko", "name": "Nyx", "profile_path": "/p1.md"},
            {"char_id": "fantasy-elf", "name": "Sylvara", "profile_path": "/p2.md"},
        ]
        mock_script.side_effect = [
            {"char_id": "cyberpunk-neko", "episode_number": 1, "title": "Ep1"},
            {"char_id": "fantasy-elf", "episode_number": 1, "title": "Ep2"},
        ]

        result = producer.produce(cycle=1, feedback={})
        assert result["cycle"] == 1
        assert len(result["characters"]) == 2
        assert len(result["scripts"]) == 2
        assert "mvp" in result["stages_covered"]
        assert "exports" in result

    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    @patch.object(ContentProducer, "_build_character")
    @patch.object(ContentProducer, "_build_script")
    def test_baseline_cycle_2_no_prev(
        self,
        mock_script: MagicMock,
        mock_char: MagicMock,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        mock_char.side_effect = [
            {"char_id": "cyberpunk-neko", "name": "Nyx", "profile_path": "/p.md"},
            {"char_id": "fantasy-elf", "name": "Sylvara", "profile_path": "/p2.md"},
        ]
        mock_script.side_effect = [
            {"char_id": "cyberpunk-neko", "episode_number": 1, "title": "Ep1"},
            {"char_id": "fantasy-elf", "episode_number": 1, "title": "Ep2"},
        ]

        result = producer.produce(cycle=2, feedback={})
        assert result["cycle"] == 2


class TestImprovedProduce:
    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    @patch.object(ContentProducer, "_build_script")
    @patch.object(ContentProducer, "_add_character")
    def test_adds_content_when_gap_large(
        self,
        mock_add_char: MagicMock,
        mock_script: MagicMock,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        mock_add_char.return_value = "new-char"
        mock_script.return_value = {
            "char_id": "new-char",
            "episode_number": 1,
            "title": "New Ep",
        }
        prev = {
            "characters": [{"char_id": "c1", "name": "Char1"}],
            "scripts": [{"char_id": "c1", "title": "Ep1"}],
            "stages_covered": {"mvp"},
        }
        feedback = {"Static Audit": 30.0, "Reasoning Metrics": 50.0, "Action Metrics": 70.0, "E2E Metrics": 60.0, "MAS Dimensions": 80.0}

        result = producer.produce(cycle=2, feedback=feedback, prev_artifacts=prev)
        assert result["cycle"] == 2
        assert len(result["characters"]) >= 1
        assert len(result["scripts"]) >= 1

    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    @patch.object(ContentProducer, "_build_script")
    @patch.object(ContentProducer, "_add_character")
    def test_crossover_when_mas_low(
        self,
        mock_add_char: MagicMock,
        mock_script: MagicMock,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        mock_add_char.return_value = "c2"
        # _produce_improved may call _build_script multiple times; provide enough side effects
        mock_script.return_value = {
            "char_id": "c1", "episode_number": 2, "title": "Ep2",
        }
        prev = {
            "characters": [
                {"char_id": "c1", "name": "A", "archetype": "The Trickster", "style_keywords": "cyberpunk"},
                {"char_id": "c2", "name": "B", "archetype": "The Guardian", "style_keywords": "fantasy"},
            ],
            "scripts": [{"char_id": "c1", "episode_number": 1, "title": "Ep1"}],
            "stages_covered": {"mvp"},
        }
        feedback = {"MAS Dimensions": 30.0, "Static Audit": 60.0, "Reasoning Metrics": 70.0, "Action Metrics": 70.0, "E2E Metrics": 70.0}

        producer._build_crossover_script = MagicMock(return_value={
            "char_id": "c1xc2",
            "episode_number": 0,
            "title": "Crossover: When Worlds Collide",
            "scene_count": 3,
            "total_duration_s": 37,
            "script_path": "/cross.md",
        })

        result = producer.produce(cycle=3, feedback=feedback, prev_artifacts=prev)
        assert result["cycle"] == 3

    def test_baseline_when_no_prev_or_cycle_1(self, producer: ContentProducer) -> None:
        with patch.multiple(
            "maref.integration.feature_dev.content_producer.Path",
            mkdir=MagicMock(),
            write_text=MagicMock(),
        ), patch.object(producer, "_build_character") as mock_char, patch.object(
            producer, "_build_script"
        ) as mock_script:
            mock_char.side_effect = [
                {"char_id": "c1", "name": "Nyx", "profile_path": "/p.md"},
                {"char_id": "c2", "name": "Sylvara", "profile_path": "/p2.md"},
            ]
            mock_script.side_effect = [
                {"char_id": "c1", "episode_number": 1, "title": "Ep1"},
                {"char_id": "c2", "episode_number": 1, "title": "Ep2"},
            ]
            result = producer.produce(cycle=1, feedback={})
            assert result["cycle"] == 1

    def test_stages_covered_escalates(self, producer: ContentProducer) -> None:
        prev = {
            "characters": [{"char_id": "c1"}, {"char_id": "c2"}, {"char_id": "c3"}],
            "scripts": [{"char_id": c, "episode_number": i, "title": f"Ep{i}"} for i, c in enumerate(["c1", "c1", "c1", "c1", "c1", "c1", "c1", "c1"])],
            "stages_covered": {"mvp"},
        }
        with patch.object(producer, "_write_artifacts"), patch.object(
            producer, "_build_script"
        ), patch.object(producer, "_add_character") as mock_add:
            mock_add.return_value = "c4"
            result = producer.produce(cycle=5, feedback={"Static Audit": 50.0, "Reasoning Metrics": 50.0, "Action Metrics": 50.0, "E2E Metrics": 50.0, "MAS Dimensions": 50.0}, prev_artifacts=prev)
            assert "mixed" in result["stages_covered"] or "internalization" in result["stages_covered"]


class TestAddCharacter:
    def test_adds_new_theme(self, producer: ContentProducer) -> None:
        chars: list = []
        with patch.object(producer, "_build_character") as mock_build:
            mock_build.return_value = {"char_id": "cyberpunk-neko", "name": "Nyx"}
            cid = producer._add_character(chars)
            assert cid == "cyberpunk-neko"
            assert len(chars) == 1

    def test_skips_existing(self, producer: ContentProducer) -> None:
        chars = [{"name": "Neon-chan"}]
        with patch.object(producer, "_build_character") as mock_build:
            mock_build.return_value = {"char_id": "fantasy-elf", "name": "Sylvara"}
            cid = producer._add_character(chars)
            assert cid == "fantasy-elf"

    def test_fallback_when_all_used(self, producer: ContentProducer) -> None:
        chars = [
            {"name": "Neon-chan"},
            {"name": "Sylvara"},
            {"name": "Sam Spade-3PO"},
        ]
        cid = producer._add_character(chars)
        assert cid.startswith("generated-")
        assert len(chars) == 4


class TestBuildCharacter:
    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "write_text")
    def test_build_character_structure(
        self,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        _mock_write2: MagicMock,
        _mock_mkdir2: MagicMock,
        producer: ContentProducer,
    ) -> None:
        profile = producer._build_character("test-char", "cyberpunk-neko")
        assert profile["char_id"] == "test-char"
        assert profile["name"] == "Neon-chan"
        assert profile["archetype"] == "The Trickster"
        assert "profile_path" in profile
        assert "created_date" in profile

    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    def test_build_character_fallback_theme(
        self,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        profile = producer._build_character("unknown", "nonexistent-theme")
        assert profile["name"] == "Neon-chan"  # falls back to cyberpunk-neko


class TestBuildScript:
    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    def test_build_script_structure(
        self,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        script = producer._build_script("test-char", "cyberpunk-neko", 1)
        assert script["char_id"] == "test-char"
        assert script["episode_number"] == 1
        assert script["scene_count"] == 3
        assert script["total_duration_s"] == 37
        assert "script_path" in script

    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    def test_build_script_uses_theme(
        self,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        script = producer._build_script("elf-char", "fantasy-elf", 2)
        assert "Journey" in script["title"]
        assert script["scene_count"] == 3


class TestBuildCrossoverScript:
    @patch("maref.integration.feature_dev.content_producer.Path.mkdir")
    @patch("maref.integration.feature_dev.content_producer.Path.write_text")
    def test_crossover_structure(
        self,
        mock_write: MagicMock,
        mock_mkdir: MagicMock,
        producer: ContentProducer,
    ) -> None:
        script = producer._build_crossover_script("char-a", "char-b")
        assert script["char_id"] == "char-axchar-b"
        assert script["episode_number"] == 0
        assert "Crossover" in script["title"]
        assert script["scene_count"] == 3


class TestCountReqsCovered:
    def test_basic_count(self, producer: ContentProducer) -> None:
        count = producer._count_reqs_covered(
            chars=[{"char_id": "c1"}, {"char_id": "c2"}],
            scripts=[{"char_id": "c1"}, {"char_id": "c1"}, {"char_id": "c2"}],
        )
        assert count > 0

    def test_empty(self, producer: ContentProducer) -> None:
        assert producer._count_reqs_covered(chars=[], scripts=[]) == 0

    def test_capped_by_doc_reqs(self, producer: ContentProducer) -> None:
        producer.doc.metadata["extracted_requirements"] = 10
        count = producer._count_reqs_covered(
            chars=[{"char_id": "c1"}] * 5,
            scripts=[{"char_id": "c1"}] * 5,
        )
        assert count <= 10

    def test_bonus_for_multiple_chars_and_scripts(self, producer: ContentProducer) -> None:
        count = producer._count_reqs_covered(
            chars=[{"char_id": "c1"}, {"char_id": "c2"}],
            scripts=[{"char_id": "c1"}, {"char_id": "c1"}, {"char_id": "c2"}],
        )
        assert count > 5
