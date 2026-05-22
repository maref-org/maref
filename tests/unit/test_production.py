"""Tests for the MAREF Production module (v0.28.0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from maref.production.asset_scaffolder import AssetScaffolder
from maref.production.character_factory import CharacterFactory
from maref.production.content_assembler import ContentAssembler
from maref.production.content_engine import ContentEngine, ProductionResult
from maref.production.hypothesis_validator import HypothesisValidator, ValidationResult
from maref.production.script_writer import ScriptWriter


class TestAssetScaffolder:
    def test_init_default_base(self) -> None:
        s = AssetScaffolder()
        assert s.base.name == "ai-native-ip"

    def test_scaffold_creates_directories(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path))
        result = s.scaffold()
        assert result["directories_created"] >= 14
        assert (tmp_path / "characters").exists()
        assert (tmp_path / "storylines").exists()
        assert (tmp_path / "README.md").exists()

    def test_scaffold_idempotent(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path))
        s.scaffold()
        s.scaffold()  # should not raise
        assert (tmp_path / "characters").exists()

    def test_create_character(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path))
        path = s.create_character("test-char")
        assert path.name == "test-char"
        assert (path / "profile").exists()
        assert (path / "lora-weights").exists()
        assert (path / "reference-images").exists()
        assert (path / "voice-samples").exists()

    def test_create_storyline(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path))
        path = s.create_storyline("test-story")
        assert path.name == "test-story"
        assert (path / "arc").exists()
        assert (path / "episodes").exists()
        assert (path / "fan-feedback").exists()

    def test_get_status_not_exists(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path / "nonexistent"))
        status = s.get_status()
        assert not status["exists"]

    def test_get_status_with_data(self, tmp_path: Path) -> None:
        s = AssetScaffolder(base_path=str(tmp_path))
        s.scaffold()
        s.create_character("hero1")
        status = s.get_status()
        assert status["exists"]
        assert "hero1" in status["characters"]
        assert status["export_count"] == 0


class TestCharacterFactory:
    def test_list_themes(self) -> None:
        cf = CharacterFactory()
        themes = cf.list_themes()
        assert len(themes) == 3
        ids = [t["id"] for t in themes]
        assert "cyberpunk-neko" in ids
        assert "fantasy-elf" in ids
        assert "retro-detective-noir" in ids

    def test_generate_creates_profile(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        result = cf.generate("cyberpunk-neko")
        assert result["char_id"] == "cyberpunk-neko"
        assert result["name"] == "Neon-chan"
        assert result["archetype"] == "The Trickster"
        profile_path = Path(result["profile_path"])
        assert profile_path.exists()
        meta_path = tmp_path / "characters" / "cyberpunk-neko" / "profile" / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["name"] == "Neon-chan"

    def test_generate_with_custom_char_id(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        result = cf.generate("fantasy-elf", char_id="my-elf")
        assert result["char_id"] == "my-elf"
        assert (tmp_path / "characters" / "my-elf").exists()

    def test_generate_unknown_theme(self) -> None:
        cf = CharacterFactory()
        with pytest.raises(ValueError, match="Unknown theme 'invalid-theme'"):
            cf.generate("invalid-theme")

    def test_get_profile_nonexistent(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        assert cf.get_profile("nobody") is None

    def test_get_profile_exists(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        profile = cf.get_profile("cyberpunk-neko")
        assert profile is not None
        assert profile["name"] == "Neon-chan"
        assert profile["archetype"] == "The Trickster"

    def test_render_template_all_fields(self) -> None:
        cf = CharacterFactory()
        data: dict[str, str] = {k: f"val_{k}" for k in [
            "name", "alias", "archetype", "role", "appearance",
            "features", "palette", "style_keywords", "personality_type",
            "strengths", "flaws", "quirks", "speech_pattern",
            "backstory", "voice_tone", "voice_cadence", "catchphrases",
            "setting", "relationships", "motivation",
        ]}
        md = cf._render_template(data)
        for val in data.values():
            assert val in md


class TestScriptWriter:
    def test_list_available_matches_theme(self) -> None:
        sw = ScriptWriter()
        eps = sw.list_available("cyberpunk-neko")
        assert len(eps) == 2
        assert eps[0]["title"] == "The Awakening"

    def test_list_available_no_match(self) -> None:
        sw = ScriptWriter()
        assert sw.list_available("unknown-char") == []

    def test_generate_raises_if_no_character(self, tmp_path: Path) -> None:
        sw = ScriptWriter(base_path=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            sw.generate("nonexistent")

    def test_generate_creates_script(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        sw = ScriptWriter(base_path=str(tmp_path))
        result = sw.generate("cyberpunk-neko", episode_number=1)
        assert result["title"] == "The Awakening"
        assert result["episode_number"] == 1
        assert result["scene_count"] == 3
        script_path = Path(result["script_path"])
        assert script_path.exists()
        content = script_path.read_text(encoding="utf-8")
        assert "Episode 1: The Awakening" in content
        assert "Neon-chan" in content

    def test_generate_episode_2(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        sw = ScriptWriter(base_path=str(tmp_path))
        result = sw.generate("cyberpunk-neko", episode_number=2)
        assert result["title"] == "The Ghost in the Machine"

    def test_generate_clamps_invalid_episode(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        sw = ScriptWriter(base_path=str(tmp_path))
        result = sw.generate("cyberpunk-neko", episode_number=99)
        assert result["episode_number"] == 1

    def test_generate_fallback_theme(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko", char_id="weird-char")
        sw = ScriptWriter(base_path=str(tmp_path))
        result = sw.generate("weird-char")
        assert result["title"] == "The Awakening"


class TestContentAssembler:
    def test_assemble_raises_if_no_character(self, tmp_path: Path) -> None:
        ca = ContentAssembler(base_path=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            ca.assemble("nonexistent")

    def test_assemble_creates_export(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        ca = ContentAssembler(base_path=str(tmp_path))
        result = ca.assemble("cyberpunk-neko")
        assert result["char_id"] == "cyberpunk-neko"
        assert result["has_profile"]
        export_dir = Path(result["export_dir"])
        assert (export_dir / "manifest.json").exists()
        assert (export_dir / "profile.md").exists()
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["char_id"] == "cyberpunk-neko"

    def test_assemble_with_specific_episode(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        sw = ScriptWriter(base_path=str(tmp_path))
        sw.generate("cyberpunk-neko", episode_number=1)
        sw.generate("cyberpunk-neko", episode_number=2)
        ca = ContentAssembler(base_path=str(tmp_path))
        result = ca.assemble("cyberpunk-neko", episode=1)
        assert "-ep01" in result["export_dir"]

    def test_list_dir_nonexistent(self, tmp_path: Path) -> None:
        ca = ContentAssembler()
        assert ca._list_dir(tmp_path / "noexist") == []


class TestHypothesisValidator:
    def test_validate_character_not_found(self, tmp_path: Path) -> None:
        hv = HypothesisValidator(base_path=str(tmp_path))
        result = hv.validate("nonexistent")
        assert not result.overall_pass
        assert not result.h1_pass
        assert "not found" in result.h1_detail.lower()

    def test_validate_h1_h2_h3_all_pass(self, tmp_path: Path) -> None:
        base = tmp_path
        char_dir = base / "characters" / "test-char"
        meta = {"name": "Test Hero", "archetype": "The Hero", "style_keywords": "neon", "palette": "cyan"}
        meta_dir = char_dir / "profile"
        meta_dir.mkdir(parents=True)
        (meta_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        ep_dir = base / "storylines" / "test-char-s01" / "episodes"
        ep_dir.mkdir(parents=True)
        (ep_dir / "episode-01.md").write_text("# ep1")
        (ep_dir / "episode-02.md").write_text("# ep2")
        export_dir = base / "exports" / "test-char"
        export_dir.mkdir(parents=True)
        (export_dir / "manifest.json").write_text("{}")
        hv = HypothesisValidator(base_path=str(base))
        result = hv.validate("test-char")
        assert result.overall_pass
        assert result.h1_pass
        assert result.h2_pass
        assert result.h3_pass

    def test_validate_h1_no_profile(self) -> None:
        hv = HypothesisValidator()
        passed, detail = hv._check_h1(False, {})
        assert not passed
        assert "no profile" in detail.lower()

    def test_validate_h1_with_profile(self) -> None:
        hv = HypothesisValidator()
        passed, detail = hv._check_h1(True, {"name": "X", "archetype": "Hero"})
        assert passed
        assert "complete profile" in detail

    def test_validate_h1_incomplete_profile(self) -> None:
        hv = HypothesisValidator()
        passed, detail = hv._check_h1(True, {"name": "X"})
        assert passed
        assert "mvp viable" in detail.lower()

    def test_validate_h2_no_profile(self) -> None:
        hv = HypothesisValidator()
        passed, _ = hv._check_h2(False, {}, 0)
        assert not passed

    def test_validate_h2_styled_and_scripted(self) -> None:
        hv = HypothesisValidator()
        passed, detail = hv._check_h2(True, {"style_keywords": "neon", "palette": "cyan"}, 2)
        assert passed
        assert "differentiated" in detail

    def test_validate_h2_mvp_viable(self) -> None:
        hv = HypothesisValidator()
        passed, _ = hv._check_h2(True, {}, 0)
        assert passed

    def test_validate_h3_no_content(self) -> None:
        hv = HypothesisValidator()
        passed, _ = hv._check_h3(False, 0)
        assert not passed

    def test_validate_h3_mvp_viable(self) -> None:
        hv = HypothesisValidator()
        passed, _ = hv._check_h3(False, 1)
        assert passed

    def test_validate_h3_export_ready(self) -> None:
        hv = HypothesisValidator()
        passed, detail = hv._check_h3(True, 2)
        assert passed
        assert "monetization path" in detail

    def test_validation_result_to_dict(self) -> None:
        vr = ValidationResult(
            char_id="x", h1_pass=True, h1_detail="h1", h2_pass=False, h2_detail="h2",
            h3_pass=True, h3_detail="h3", overall_pass=True,
        )
        d = vr.to_dict()
        assert d["char_id"] == "x"
        assert d["h1"]["pass"]
        assert not d["h2"]["pass"]


class TestContentEngine:
    def test_engine_initialization(self) -> None:
        engine = ContentEngine()
        assert engine.scaffolder is not None
        assert engine.char_factory is not None
        assert engine.script_writer is not None
        assert engine.assembler is not None
        assert engine.validator is not None

    def test_run_character_only(self, tmp_path: Path) -> None:
        engine = ContentEngine()
        engine.scaffolder = AssetScaffolder(base_path=str(tmp_path))
        engine.char_factory = CharacterFactory(base_path=str(tmp_path))
        result = engine.run_character_only("cyberpunk-neko")
        assert result["name"] == "Neon-chan"

    def test_run_script_only(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        engine = ContentEngine()
        engine.script_writer = ScriptWriter(base_path=str(tmp_path))
        result = engine.run_script_only("cyberpunk-neko", episode=1)
        assert result["title"] == "The Awakening"

    def test_run_assemble_only(self, tmp_path: Path) -> None:
        cf = CharacterFactory(base_path=str(tmp_path))
        cf.generate("cyberpunk-neko")
        engine = ContentEngine()
        engine.assembler = ContentAssembler(base_path=str(tmp_path))
        result = engine.run_assemble_only("cyberpunk-neko")
        assert result["has_profile"]

    def test_run_validate_only_not_found(self, tmp_path: Path) -> None:
        engine = ContentEngine()
        engine.validator = HypothesisValidator(base_path=str(tmp_path))
        result = engine.run_validate_only("nonexistent")
        assert not result.overall_pass

    def test_production_result_to_dict(self) -> None:
        pr = ProductionResult(
            char_id="test", theme_id="cyberpunk-neko",
            profile={"name": "X"}, scripts=[],
            assembled=None, validation=None,
            total_duration_s=1.234, steps=["step1"],
        )
        d = pr.to_dict()
        assert d["char_id"] == "test"
        assert d["total_duration_s"] == 1.23
        assert d["validation"] is None

    def test_production_result_to_dict_with_validation(self) -> None:
        vr = ValidationResult(
            char_id="x", h1_pass=True, h1_detail="h1", h2_pass=False, h2_detail="h2",
            h3_pass=True, h3_detail="h3", overall_pass=True,
        )
        pr = ProductionResult(
            char_id="x", theme_id="t", profile={}, scripts=[],
            assembled=None, validation=vr,
            total_duration_s=0.5, steps=[],
        )
        d = pr.to_dict()
        assert d["validation"]["overall_pass"]

    def test_full_pipeline_scaffold_and_generate_only(self, tmp_path: Path) -> None:
        """Run a full pipeline cycle and verify the result structure."""
        engine = ContentEngine()
        engine.scaffolder = AssetScaffolder(base_path=str(tmp_path))
        engine.char_factory = CharacterFactory(base_path=str(tmp_path))
        engine.script_writer = ScriptWriter(base_path=str(tmp_path))
        engine.assembler = ContentAssembler(base_path=str(tmp_path))
        engine.validator = HypothesisValidator(base_path=str(tmp_path))
        result = engine.run_full_pipeline("cyberpunk-neko", episode_count=1)
        assert result.char_id == "cyberpunk-neko"
        assert result.profile["name"] == "Neon-chan"
        assert len(result.scripts) == 1
        assert result.assembled is not None
        assert result.validation is not None
        assert result.total_duration_s > 0
        assert len(result.steps) >= 4
