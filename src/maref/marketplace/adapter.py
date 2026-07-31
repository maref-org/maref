from __future__ import annotations

import time
from typing import Any

from maref.marketplace.registry import SkillManifest
from maref.recursive.skill_schema import (
    DegradationChain,
    HexagramTrigger,
    MarefSkill,
    MarefSkillMeta,
    SkillSource,
)


class ManifestAdapter:
    SKILL_FIELD = "1.0"

    @staticmethod
    def to_maref(
        manifest: SkillManifest,
        source: SkillSource = SkillSource.PROJECT,
    ) -> MarefSkill:
        entrypoint = manifest.entrypoint or "default"
        behavior: dict[str, Any] = {"entrypoint": entrypoint}
        if manifest.input_schema:
            behavior["input_schema"] = manifest.input_schema
        if manifest.output_schema:
            behavior["output_schema"] = manifest.output_schema
        behavior["sandbox"] = manifest.sandbox_config.get("mode", "isolated")

        return MarefSkill(
            maref_skill=ManifestAdapter.SKILL_FIELD,
            meta=MarefSkillMeta(
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                author_did=manifest.author or None,
            ),
            role_affinity={},
            hexagram_trigger=HexagramTrigger(),
            parameter_injection=None,
            hooks=[],
            context_activation=None,
            degradation_chain=DegradationChain(primary=entrypoint),
            behavior=behavior,
            skill_id=manifest.skill_id,
            source=source,
            loaded_at=time.time(),
        )

    @staticmethod
    def to_manifest(skill: MarefSkill) -> SkillManifest:
        entrypoint = skill.behavior.get("entrypoint", "") if skill.behavior else ""
        input_schema = skill.behavior.get("input_schema", {}) if skill.behavior else {}
        output_schema = skill.behavior.get("output_schema", {}) if skill.behavior else {}

        return SkillManifest(
            name=skill.meta.name,
            version=skill.meta.version,
            description=skill.meta.description,
            input_schema=input_schema,
            output_schema=output_schema,
            dependencies=[],
            author=skill.meta.author_did or "",
            license="Apache-2.0",
            entrypoint=entrypoint,
            sandbox_config={"mode": skill.behavior.get("sandbox", "isolated")} if skill.behavior else {},
            test_cases=[],
            skill_id=skill.skill_id[:8],
        )
