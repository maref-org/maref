"""Skill Loader — parse Markdown skill files with YAML frontmatter.

Format:
---
name: skill_name
role_affinity: reviewer|builder|planner|observer
hexagram_trigger: 离|坤|乾|...
---

# Skill Title

## Steps
1. ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MarefSkill:
    """Parsed skill definition from a Markdown file."""

    name: str
    role_affinity: str = ""
    hexagram_trigger: str = ""
    title: str = ""
    body: str = ""
    source_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_mcp_prompt(self) -> dict[str, Any]:
        """Convert to MCP prompt format."""
        return {
            "name": self.name,
            "description": self.title or self.body[:120],
            "arguments": [],
            "prompt": self.body,
        }


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_skill_file(path: str | Path) -> MarefSkill | None:
    """Parse a single Markdown skill file with YAML frontmatter."""
    content = Path(path).read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    try:
        fm = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        fm = {}

    name = fm.get("name", Path(path).stem)
    title = ""
    for line in body.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return MarefSkill(
        name=name,
        role_affinity=fm.get("role_affinity", ""),
        hexagram_trigger=fm.get("hexagram_trigger", ""),
        title=title,
        body=body,
        source_path=str(path),
        metadata={
            k: v for k, v in fm.items() if k not in ("name", "role_affinity", "hexagram_trigger")
        },
    )


def load_skills_from_dir(directory: str | Path) -> list[MarefSkill]:
    """Load all Markdown skill files from a directory."""
    skills: list[MarefSkill] = []
    base = Path(directory)
    if not base.is_dir():
        return skills
    for f in sorted(base.glob("*.md")):
        skill = parse_skill_file(f)
        if skill is not None:
            skills.append(skill)
    return skills
