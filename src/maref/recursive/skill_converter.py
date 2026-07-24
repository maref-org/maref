from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from maref.recursive.skill_scorer import QualityScore, _strip_frontmatter

# ── SKILL.md → MarefSkill dict ─────────────────────────────


class SkillConverter:
    """Convert a scanned SKILL.md + QualityScore into a MarefSkill-compatible dict.

    The core mapping:

        SKILL.md frontmatter    → meta.name, meta.description
        repo_url + content_hash → meta.author_did
        full body               → behavior.prompt
        constant                → behavior.entrypoint = "llm_guided"
        empty defaults          → hexagram_trigger, degradation_chain, context_activation
    """

    def convert(
        self,
        content: str,
        content_hash: str,
        repo_url: str,
        repo_path: str,
        frontmatter: dict[str, Any] | None = None,
        quality: QualityScore | None = None,
    ) -> dict[str, Any]:
        if frontmatter is None:
            import yaml

            from maref.recursive.skill_scorer import _split_frontmatter

            _, raw_fm = _split_frontmatter(content)
            frontmatter = yaml.safe_load(raw_fm) if raw_fm else {}

        name = str(frontmatter.get("name", "unknown_skill")).strip().replace(" ", "_")
        description = str(frontmatter.get("description", "")).strip()
        body = _strip_frontmatter(content)

        prompt = self._build_prompt(name, description, body)

        skill_id = self._generate_skill_id(content_hash)

        author_did = f"did:github:{repo_url.replace('https://', '')}/hash:{content_hash[:12]}"

        est_steps = len([l for l in body.split("\n") if l.strip().startswith("## Step") or l.strip().startswith("##Step")])
        timeout_ms = min(120000, max(30000, est_steps * 15000))

        return {
            "maref_skill": "1.0",
            "meta": {
                "name": name,
                "version": "1.0.0",
                "description": description or f"Distilled from {repo_url}",
                "author_did": author_did,
            },
            "hexagram_trigger": {
                "require": [],
                "exclude": [],
                "transition_from": None,
            },
            "parameter_injection": {
                "model_override": None,
                "effort": None,
                "timeout_ms": timeout_ms,
            },
            "hooks": [],
            "context_activation": None,
            "degradation_chain": {
                "primary": "llm_guided",
                "degraded": [],
            },
            "behavior": {
                "entrypoint": "llm_guided",
                "prompt": prompt,
                "handler_type": "llm",
                "content_hash": content_hash[:12],
                "source_repo": repo_url,
                "source_path": repo_path,
            },
            "quality_score": round(quality.overall, 4) if quality else 0.0,
        }

    @staticmethod
    def _build_prompt(name: str, description: str, body: str) -> str:
        lines = [
            f"You are executing the \"{name}\" skill.",
            f"Description: {description}" if description else "",
            "",
            "Instructions:",
            body.strip(),
        ]
        return "\n".join(lines)

    @staticmethod
    def _generate_skill_id(content_hash: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"maref::skill::{content_hash}"))


def convert_skill_to_dict(
    content: str,
    content_hash: str,
    repo_url: str,
    repo_path: str,
    frontmatter: dict[str, Any] | None = None,
    quality: QualityScore | None = None,
) -> dict[str, Any]:
    """Convenience wrapper."""
    return SkillConverter().convert(content, content_hash, repo_url, repo_path, frontmatter, quality)
