from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.recursive.skill_loader import SkillLoader
from maref.recursive.skill_schema import (
    SkillSource,
    parse_skill_from_dict,
    validate_skill_dict,
)

VALID_SKILL_DICT = {
    "maref_skill": "1.0",
    "meta": {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "author_did": "did:maref:test/test-skill/v1",
    },
    "role_affinity": {
        "primary": "Executor",
        "secondary": ["Critic"],
    },
    "hexagram_trigger": {
        "require": [10, 20],
        "exclude": [0, 63],
        "transition_from": [5],
    },
    "parameter_injection": {
        "model_override": "sonnet",
        "effort": "high",
        "timeout_ms": 30000,
    },
    "hooks": [
        {"event": "maref.session.start", "handler": "check_integrity"},
    ],
    "context_activation": {
        "file_patterns": ["**/*.py"],
        "entropy_range": [1.0, 5.0],
    },
    "degradation_chain": {
        "primary": "full_audit",
        "degraded": [
            {"condition": "timeout", "fallback": "basic_check"},
        ],
    },
    "behavior": {
        "entrypoint": "skills/test.py",
        "sandbox": "isolated",
    },
}


class TestSkillValidation:
    def test_valid_skill_passes_validation(self) -> None:
        errors = validate_skill_dict(VALID_SKILL_DICT)
        assert len(errors) == 0

    def test_missing_maref_skill_version(self) -> None:
        data = {**VALID_SKILL_DICT, "maref_skill": "0.9"}
        errors = validate_skill_dict(data)
        assert any(e.field == "maref_skill" for e in errors)

    def test_missing_meta_name(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["meta"] = {**data["meta"], "name": ""}
        errors = validate_skill_dict(data)
        assert any(e.field == "meta.name" for e in errors)

    def test_missing_meta_version(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["meta"] = {**data["meta"], "version": ""}
        errors = validate_skill_dict(data)
        assert any(e.field == "meta.version" for e in errors)

    def test_missing_meta_description(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["meta"] = {**data["meta"], "description": ""}
        errors = validate_skill_dict(data)
        assert any(e.field == "meta.description" for e in errors)

    def test_hexagram_out_of_range_require(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["hexagram_trigger"] = {"require": [64], "exclude": [], "transition_from": None}
        errors = validate_skill_dict(data)
        assert any(e.field == "hexagram_trigger.require" for e in errors)

    def test_hexagram_out_of_range_exclude(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["hexagram_trigger"] = {"require": [], "exclude": [-1], "transition_from": None}
        errors = validate_skill_dict(data)
        assert any(e.field == "hexagram_trigger.exclude" for e in errors)

    def test_hexagram_out_of_range_transition_from(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["hexagram_trigger"] = {"require": [], "exclude": [], "transition_from": [100]}
        errors = validate_skill_dict(data)
        assert any(e.field == "hexagram_trigger.transition_from" for e in errors)

    def test_missing_degradation_primary(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["degradation_chain"] = {"primary": "", "degraded": []}
        errors = validate_skill_dict(data)
        assert any(e.field == "degradation_chain.primary" for e in errors)

    def test_missing_behavior_entrypoint(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["behavior"] = {"sandbox": "isolated"}
        errors = validate_skill_dict(data)
        assert any(e.field == "behavior.entrypoint" for e in errors)

    def test_empty_require_and_exclude_is_valid(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["hexagram_trigger"] = {"require": [], "exclude": [], "transition_from": None}
        errors = validate_skill_dict(data)
        assert len(errors) == 0


class TestSkillParsing:
    def test_parse_valid_skill(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.maref_skill == "1.0"
        assert skill.name == "test-skill"
        assert skill.version == "1.0.0"
        assert skill.meta.author_did == "did:maref:test/test-skill/v1"

    def test_parse_with_hexagram_trigger(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.hexagram_trigger.require == [10, 20]
        assert skill.hexagram_trigger.exclude == [0, 63]
        assert skill.hexagram_trigger.transition_from == [5]

    def test_parse_with_parameter_injection(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.parameter_injection is not None
        assert skill.parameter_injection.model_override == "sonnet"
        assert skill.parameter_injection.effort == "high"
        assert skill.parameter_injection.timeout_ms == 30000

    def test_parse_with_hooks(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert len(skill.hooks) == 1
        assert skill.hooks[0].event == "maref.session.start"

    def test_parse_with_context_activation(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.context_activation is not None
        assert skill.context_activation.entropy_range == (1.0, 5.0)

    def test_parse_with_degradation_chain(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.degradation_chain.primary == "full_audit"
        assert len(skill.degradation_chain.degraded) == 1
        assert skill.degradation_chain.degraded[0].condition == "timeout"

    def test_parse_skill_assigns_uuid(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert len(skill.skill_id) > 0

    def test_parse_skill_source_default(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.source == SkillSource.BUILTIN

    def test_parse_skill_source_explicit(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT, source=SkillSource.PROJECT)
        assert skill.source == SkillSource.PROJECT

    def test_parse_invalid_raises(self) -> None:
        data = {**VALID_SKILL_DICT, "maref_skill": "0.9"}
        with pytest.raises(ValueError, match="Skill validation failed"):
            parse_skill_from_dict(data)

    def test_parse_minimal_skill(self) -> None:
        data = {
            "maref_skill": "1.0",
            "meta": {"name": "minimal", "version": "1.0", "description": "desc"},
            "role_affinity": {},
            "hexagram_trigger": {"require": [], "exclude": [], "transition_from": None},
            "hooks": [],
            "degradation_chain": {"primary": "default", "degraded": []},
            "behavior": {"entrypoint": "minimal.py", "sandbox": "none"},
        }
        skill = parse_skill_from_dict(data)
        assert skill.name == "minimal"


class TestMarefSkillModel:
    def test_name_property(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.name == "test-skill"

    def test_version_property(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.version == "1.0.0"

    def test_matches_hexagram_require_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.matches_hexagram(10)

    def test_matches_hexagram_require_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_hexagram(999)

    def test_matches_hexagram_excluded(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_hexagram(0)

    def test_matches_hexagram_transition_from_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.matches_hexagram(10, previous=5)

    def test_matches_hexagram_transition_from_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_hexagram(10, previous=99)

    def test_matches_context_pattern_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.matches_context("src/main.py", entropy=2.0)

    def test_matches_context_pattern_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_context("README.md")

    def test_matches_context_entropy_in_range(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill.matches_context("src/main.py", entropy=3.0)

    def test_matches_context_entropy_below_range(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_context("src/main.py", entropy=0.5)

    def test_matches_context_entropy_above_range(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill.matches_context("src/main.py", entropy=10.0)

    def test_matches_context_none_activation(self) -> None:
        data = {**VALID_SKILL_DICT}
        data["context_activation"] = None
        skill = parse_skill_from_dict(data)
        assert skill.matches_context("any_file.txt")

    def test_to_dict_roundtrip(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        d = skill.to_dict()
        assert d["maref_skill"] == "1.0"
        assert d["meta"]["name"] == "test-skill"


class TestSkillLoader:
    def test_load_from_dict_adds_skill(self) -> None:
        loader = SkillLoader()
        skill = loader.load_from_dict(VALID_SKILL_DICT)
        found = loader.get(skill.name)
        assert found is not None
        assert found.name == "test-skill"

    def test_list_available_returns_metadata(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT)
        available = loader.list_available()
        assert len(available) == 1
        assert available[0]["name"] == "test-skill"

    def test_get_nonexistent_returns_none(self) -> None:
        loader = SkillLoader()
        assert loader.get("nonexistent") is None

    def test_multi_source_priority(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT, source=SkillSource.BUILTIN)
        project_skill = {
            **VALID_SKILL_DICT,
            "meta": {**VALID_SKILL_DICT["meta"], "version": "2.0.0"},
            "behavior": {"entrypoint": "project_test.py", "sandbox": "isolated"},
        }
        loader.load_from_dict(project_skill, source=SkillSource.PROJECT)
        found = loader.get("test-skill")
        assert found is not None
        assert found.version == "2.0.0"
        assert found.source == SkillSource.PROJECT

    def test_load_from_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / ".maref/skills"
            skills_dir.mkdir(parents=True)
            skill_yaml_path = skills_dir / "test.yaml"
            import yaml

            skill_yaml_path.write_text(yaml.dump(VALID_SKILL_DICT), encoding="utf-8")

            loader = SkillLoader()
            loader.load_all(project_root=tmpdir)
            found = loader.get("test-skill")
            assert found is not None
            assert found.source == SkillSource.PROJECT

    def test_get_active_skills_hexagram_match(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT)
        active = loader.get_active_skills(hexagram=10)
        assert len(active) == 1
        assert active[0].name == "test-skill"

    def test_get_active_skills_hexagram_excluded(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT)
        active = loader.get_active_skills(hexagram=0)
        assert len(active) == 0

    def test_import_mcp_skill(self) -> None:
        loader = SkillLoader()
        skill = loader.import_mcp_skill(VALID_SKILL_DICT)
        assert skill.source == SkillSource.MCP_REMOTE

    def test_load_yaml_with_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / ".maref/skills"
            skills_dir.mkdir(parents=True)
            (skills_dir / "invalid.yaml").write_text(": invalid yaml: :", encoding="utf-8")

            loader = SkillLoader()
            loader.load_all(project_root=tmpdir)
            assert loader.get("test-skill") is None

    def test_load_invalid_skill_dict_in_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / ".maref/skills"
            skills_dir.mkdir(parents=True)
            (skills_dir / "bad.yaml").write_text("just_a_string: not_a_dict", encoding="utf-8")

            loader = SkillLoader()
            loader.load_all(project_root=tmpdir)
            assert loader.get("test-skill") is None

    def test_get_active_skills_with_context(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT)
        active = loader.get_active_skills(hexagram=10, file_path="src/main.py", entropy=2.0)
        assert len(active) == 1

    def test_get_active_skills_context_no_match(self) -> None:
        loader = SkillLoader()
        loader.load_from_dict(VALID_SKILL_DICT)
        active = loader.get_active_skills(hexagram=10, file_path="other.txt", entropy=0.1)
        assert len(active) == 0

    def test_load_all_without_args(self) -> None:
        loader = SkillLoader()
        skills = loader.load_all()
        assert isinstance(skills, list)
