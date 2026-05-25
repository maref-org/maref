from __future__ import annotations

from typing import Any

from maref.integration.feature_dev.content_producer import ContentProducer
from maref.integration.feature_dev.doc_ingestor import FeatureDocument


def _doc(**overrides: Any) -> FeatureDocument:
    base = {
        "title": "Test",
        "raw_path": "/tmp/t.md",
        "metadata": {"extracted_requirements": 20},
    }
    base.update(overrides)
    return FeatureDocument(**base)


class TestContentProducer:
    def test_produce_baseline(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        result = prod._produce_baseline(1)
        assert result["cycle"] == 1
        assert len(result["characters"]) == 2
        assert len(result["scripts"]) == 2
        assert "mvp" in result["stages_covered"]

    def test_produce_improved_adds_content(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        prev = {
            "characters": [{"name": "Neon-chan", "char_id": "cyberpunk-neko"}],
            "scripts": [
                {"char_id": "cyberpunk-neko", "episode_number": 1, "title": "Ep1",
                 "scene_count": 3, "total_duration_s": 37, "script_path": str(tmp_path / "s1.md")},
            ],
            "stages_covered": {"mvp"},
            "requirements_covered": 7,
        }
        result = prod._produce_improved(2, {"Static Audit": 50.0}, prev, llm_plan=None)
        assert result["cycle"] == 2
        assert len(result["characters"]) >= 1
        assert len(result["scripts"]) >= 1
        assert len(result["stages_covered"]) >= 1

    def test_produce_delegates_baseline(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        result = prod.produce(1, {"A": 0.0})
        assert len(result["characters"]) == 2

    def test_produce_delegates_improved(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        prev = {
            "characters": [{"name": "Neon-chan", "char_id": "c1"}],
            "scripts": [{"char_id": "c1", "episode_number": 1, "title": "E1",
                         "scene_count": 3, "total_duration_s": 10, "script_path": str(tmp_path / "e1.md")}],
            "stages_covered": {"mvp"},
            "requirements_covered": 7,
        }
        result = prod.produce(2, {"A": 40.0}, prev_artifacts=prev)
        assert result["cycle"] == 2

    def test_add_character_new(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        chars: list[dict[str, Any]] = []
        cid = prod._add_character(chars)
        assert cid == "cyberpunk-neko"
        assert len(chars) == 1

    def test_add_character_all_used_fallback(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        chars = [
            {"name": "Neon-chan"},
            {"name": "Sylvara"},
            {"name": "Sam Spade-3PO"},
        ]
        cid = prod._add_character(chars)
        assert cid.startswith("generated-")
        assert len(chars) == 4
        assert chars[-1]["archetype"] == "The Explorer"

    def test_count_reqs_covered(self) -> None:
        doc = _doc(metadata={"extracted_requirements": 30})
        prod = ContentProducer(doc)
        chars = [{"name": "A"}, {"name": "B"}]
        scripts = [{"title": "1"}, {"title": "2"}, {"title": "3"}]
        count = prod._count_reqs_covered(chars, scripts)
        assert count > 0
        assert count <= 30

    def test_count_reqs_covered_no_doc(self) -> None:
        doc = _doc(metadata={"extracted_requirements": 0})
        prod = ContentProducer(doc)
        count = prod._count_reqs_covered([{"name": "A"}], [{"title": "1"}])
        assert count > 0

    def test_produce_improved_adds_stages(self, tmp_path: Any) -> None:
        doc = _doc()
        prod = ContentProducer(doc)
        prod._base = tmp_path
        prev = {
            "characters": [
                {"name": "A", "char_id": "cyberpunk-neko"},
                {"name": "B", "char_id": "fantasy-elf"},
                {"name": "C", "char_id": "retro-detective-noir"},
            ],
            "scripts": [
                {"char_id": "cyberpunk-neko", "episode_number": i, "title": f"E{i}",
                 "scene_count": 3, "total_duration_s": 10, "script_path": str(tmp_path / f"s{i}.md")}
                for i in range(1, 9)
            ],
            "stages_covered": {"mvp"},
            "requirements_covered": 15,
        }
        result = prod._produce_improved(5, {"MAS Dimensions": 40.0}, prev, llm_plan=None)
        stages = result["stages_covered"]
        assert "mixed" in stages
        assert "internalization" in stages
