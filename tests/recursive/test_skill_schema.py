from __future__ import annotations

import pytest

from maref.recursive.skill_schema import (
    HexagramTrigger,
    MarefSkill,
    MarefSkillMeta,
    SkillSource,
    validate_skill_dict,
)


class TestMarefSkill:
    def test_name_and_version_properties(self) -> None:
        meta = MarefSkillMeta(name="test-skill", version="2.0.0", description="a test")
        skill = MarefSkill(maref_skill="1.0", meta=meta)
        assert skill.name == "test-skill"
        assert skill.version == "2.0.0"

    def test_matches_hexagram_require(self) -> None:
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="hex-skill", version="1.0", description=""),
            hexagram_trigger=HexagramTrigger(require=[10, 20], exclude=[]),
        )
        assert skill.matches_hexagram(10) is True
        assert skill.matches_hexagram(20) is True
        assert skill.matches_hexagram(30) is False

    def test_matches_hexagram_exclude_overrides_require(self) -> None:
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="hex-skill", version="1.0", description=""),
            hexagram_trigger=HexagramTrigger(require=[10], exclude=[10]),
        )
        assert skill.matches_hexagram(10) is False

    def test_matches_hexagram_transition_from(self) -> None:
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="hex-skill", version="1.0", description=""),
            hexagram_trigger=HexagramTrigger(require=[10], transition_from=[5]),
        )
        assert skill.matches_hexagram(10, previous=5) is True
        assert skill.matches_hexagram(10, previous=99) is False

    def test_matches_context_default(self) -> None:
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="ctx-skill", version="1.0", description=""),
        )
        assert skill.matches_context("any/file.py") is True

    def test_to_dict_structure(self) -> None:
        meta = MarefSkillMeta(
            name="dict-skill",
            version="1.0.0",
            description="test to_dict",
            author_did="did:test:author",
        )
        skill = MarefSkill(
            maref_skill="1.0",
            meta=meta,
            source=SkillSource.PROJECT,
        )
        d = skill.to_dict()
        assert d["maref_skill"] == "1.0"
        assert d["meta"]["name"] == "dict-skill"
        assert d["source"] == "project"

    def test_validate_skill_dict_valid(self) -> None:
        data = {
            "maref_skill": "1.0",
            "meta": {
                "name": "valid-skill",
                "version": "1.0.0",
                "description": "a valid skill",
            },
            "hexagram_trigger": {"require": [10], "exclude": []},
            "degradation_chain": {"primary": "default"},
            "behavior": {"entrypoint": "main"},
        }
        errors = validate_skill_dict(data)
        assert len(errors) == 0

    def test_validate_skill_dict_invalid(self) -> None:
        data = {
            "maref_skill": "0.5",
            "meta": {"name": "", "version": ""},
            "hexagram_trigger": {"require": [-1, 99], "exclude": []},
            "degradation_chain": {},
            "behavior": {},
        }
        errors = validate_skill_dict(data)
        assert len(errors) >= 5
