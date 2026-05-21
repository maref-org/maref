from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from maref.recursive.skill_schema import (
    SOURCE_PRIORITY,
    MarefSkill,
    SkillSource,
    parse_skill_from_dict,
)

BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin_skills"
DEFAULT_PROJECT_SKILLS_DIR_NAME = ".maref/skills"
DEFAULT_USER_SKILLS_DIR_NAME = ".maref/skills"


class SkillLoader:
    def __init__(self) -> None:
        self._skills: dict[str, list[MarefSkill]] = {}
        self._all_skills: list[MarefSkill] = []

    @property
    def skills(self) -> list[MarefSkill]:
        return list(self._all_skills)

    def load_all(
        self,
        project_root: str | None = None,
        user_home: str | None = None,
    ) -> list[MarefSkill]:
        self._all_skills = []

        builtin_dir = BUILTIN_SKILLS_DIR
        if builtin_dir.exists():
            self._load_from_dir(builtin_dir, SkillSource.BUILTIN)

        if project_root:
            project_skills_dir = Path(project_root) / DEFAULT_PROJECT_SKILLS_DIR_NAME
            if project_skills_dir.exists():
                self._load_from_dir(project_skills_dir, SkillSource.PROJECT)

        if user_home:
            user_skills_dir = Path(user_home) / DEFAULT_USER_SKILLS_DIR_NAME
            if user_skills_dir.exists():
                self._load_from_dir(user_skills_dir, SkillSource.USER)

        merged = self._merge_by_priority()
        self._all_skills = sorted(merged, key=lambda s: s.meta.name)
        return self._all_skills

    def _load_from_dir(self, directory: Path, source: SkillSource) -> None:
        yaml_files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
        for yaml_file in yaml_files:
            try:
                raw = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
                if not isinstance(data, dict):
                    continue
                skill = parse_skill_from_dict(data, source=source)
                self._skills.setdefault(skill.name, []).append(skill)
            except (yaml.YAMLError, ValueError) as e:
                import logging
                logging.getLogger("maref.skill_loader").warning(
                    "Failed to load skill %s: %s", yaml_file, e
                )

    def _merge_by_priority(self) -> list[MarefSkill]:
        result: dict[str, MarefSkill] = {}
        for name, candidates in self._skills.items():
            best = max(candidates, key=lambda s: SOURCE_PRIORITY.get(s.source, 0))
            result[name] = best
        return list(result.values())

    def load_from_dict(self, data: dict[str, Any], source: SkillSource = SkillSource.BUILTIN) -> MarefSkill:
        skill = parse_skill_from_dict(data, source=source)
        self._skills.setdefault(skill.name, []).append(skill)
        merged = self._merge_by_priority()
        self._all_skills = sorted(merged, key=lambda s: s.meta.name)
        return skill

    def get(self, name: str) -> MarefSkill | None:
        for skill in self._all_skills:
            if skill.name == name:
                return skill
        return None

    def list_available(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.meta.name,
                "version": s.meta.version,
                "description": s.meta.description,
                "source": s.source.value,
                "skill_id": s.skill_id,
            }
            for s in self._all_skills
        ]

    def get_active_skills(
        self,
        hexagram: int,
        prev_hexagram: int | None = None,
        file_path: str | None = None,
        entropy: float | None = None,
    ) -> list[MarefSkill]:
        active: list[MarefSkill] = []
        for skill in self._all_skills:
            if skill.matches_hexagram(hexagram, prev_hexagram):
                if file_path is not None or entropy is not None:
                    if skill.matches_context(file_path or "", entropy):
                        active.append(skill)
                else:
                    active.append(skill)
        return active

    def import_mcp_skill(self, data: dict[str, Any]) -> MarefSkill:
        return self.load_from_dict(data, source=SkillSource.MCP_REMOTE)
