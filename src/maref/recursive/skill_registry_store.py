from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.recursive.agent_marketplace import (
    AgentMarketplace,
    CapabilityListing,
    TrustLevel,
)
from maref.recursive.skill_loader import SkillLoader
from maref.recursive.skill_schema import SkillSource, parse_skill_from_dict


@dataclass
class SkillRegistrationResult:
    skill_name: str
    skill_id: str
    listing_id: str | None = None
    success: bool = False
    error: str | None = None


class SkillRegistryStore:
    """Persistent dedup store for processed skill hashes."""

    def __init__(self, store_path: str | Path = ".maref/skill_distillery/registry.json") -> None:
        self._store_path = Path(store_path)
        self._processed: dict[str, float] = {}  # hash → timestamp
        self._load()

    def is_already_processed(self, content_hash: str) -> bool:
        return content_hash in self._processed

    def mark_processed(self, content_hash: str) -> None:
        self._processed[content_hash] = __import__("time").time()
        self._save()

    def list_processed(self) -> list[tuple[str, float]]:
        return [(h, ts) for h, ts in self._processed.items()]

    @property
    def count(self) -> int:
        return len(self._processed)

    def _load(self) -> None:
        if self._store_path.exists():
            try:
                data = json.loads(self._store_path.read_text())
                self._processed = {k: v for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                self._processed = {}

    def _save(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store_path.write_text(json.dumps(self._processed, indent=2))


# ── Registration helpers ───────────────────────────────────


def register_distilled_skill(
    skill_dict: dict[str, Any],
    loader: SkillLoader | None = None,
    marketplace: AgentMarketplace | None = None,
    agent_id: str = "maref_skill_distiller",
) -> SkillRegistrationResult:
    """Load skill dict into SkillLoader and publish as CapabilityListing."""
    name = skill_dict.get("meta", {}).get("name", "unknown")
    skill_id = skill_dict.get("behavior", {}).get("content_hash", "???")

    if loader is None:
        loader = SkillLoader()

    # 1. Parse and load via MCP_REMOTE source
    try:
        skill = parse_skill_from_dict(skill_dict, source=SkillSource.MCP_REMOTE)
        loader._skills.setdefault(skill.name, []).append(skill)
        loader._all_skills = sorted(
            loader._merge_by_priority() if hasattr(loader, "_merge_by_priority") else [skill],
            key=lambda s: s.meta.name,
        )
    except Exception as exc:
        return SkillRegistrationResult(
            skill_name=name,
            skill_id=skill_id,
            success=False,
            error=f"parse_skill_from_dict failed: {exc}",
        )

    # 2. Publish to marketplace as free listing
    listing_id = None
    if marketplace is not None:
        try:
            from datetime import datetime

            listing = CapabilityListing(
                agent_id=agent_id,
                capability=name,
                price=0.0,
                trust_requirement=TrustLevel.LOW,
                sla={},
                metadata={
                    "skill_id": skill_id,
                    "source": "github_distilled",
                    "distilled_at": datetime.utcnow().isoformat(),
                },
            )
            listing_id = marketplace.publish(listing)
        except Exception as exc:
            return SkillRegistrationResult(
                skill_name=name,
                skill_id=skill_id,
                success=False,
                error=f"marketplace publish failed: {exc}",
            )

    return SkillRegistrationResult(
        skill_name=name,
        skill_id=skill_id,
        listing_id=listing_id,
        success=True,
    )
