from __future__ import annotations

import uuid
from typing import Any

from maref.evolution.shadow_registry import ShadowEntry, ShadowRegistry
from maref.recursive.skill_schema import (
    ContextActivation,
    DegradationChain,
    DegradationStep,
    HexagramTrigger,
    MarefSkill,
    MarefSkillMeta,
    ParameterInjection,
    SkillSource,
    validate_skill_dict,
)

DEATH_CAUSE_TO_HEXAGRAM: dict[str, list[int]] = {
    "hallucination": [5, 13],
    "tool_misuse": [4, 12],
    "ethical_breach": [0, 8],
    "context_overflow": [6, 14],
    "user_terminated": [1, 9],
    "timeout": [4, 20],
    "system_crash": [0, 24],
    "unknown": [1, 9],
}

DEATH_CAUSE_TEMPLATES: dict[str, str] = {
    "hallucination": "Skill derived from hallucination death: fact-checking + reality-anchoring patterns",
    "tool_misuse": "Skill derived from tool misuse death: tool-call validation + safety patterns",
    "ethical_breach": "Skill derived from ethical breach death: boundary enforcement patterns",
    "context_overflow": "Skill derived from context overflow death: context compression patterns",
    "user_terminated": "Skill derived from user-terminated session: graceful shutdown patterns",
    "timeout": "Skill derived from timeout death: response-time optimization patterns",
    "system_crash": "Skill derived from system crash death: fault-tolerance patterns",
    "unknown": "Skill derived from unknown death cause: general resilience patterns",
}

SKILL_VERSION = "1.0.0-caf"


class SkillRefinery:
    def __init__(self, shadow_registry: ShadowRegistry) -> None:
        self._shadow = shadow_registry
        self._refined: dict[str, MarefSkill] = {}

    def refine_from_entry(self, entry: ShadowEntry) -> MarefSkill:
        cause = entry.death_cause
        agent_id = entry.agent_id
        skill_id = f"caf-{agent_id}-{cause}-{uuid.uuid4().hex[:6]}"
        trust_score = entry.trust_legacy
        hexagram = DEATH_CAUSE_TO_HEXAGRAM.get(cause, [1, 9])

        meta = MarefSkillMeta(
            name=f"caf/{agent_id}/{cause}",
            version=SKILL_VERSION,
            description=DEATH_CAUSE_TEMPLATES.get(
                cause, f"Skill refined from {agent_id} death by {cause}"
            ),
            author_did=f"did:maref:caf:{agent_id}",
        )

        trigger = HexagramTrigger(
            require=hexagram,
            exclude=list(range(63)),
            transition_from=None,
        )

        param_injection = ParameterInjection(
            model_override=None,
            effort="auto" if trust_score > 0.7 else "high",
            timeout_ms=int(entry.lifespan_seconds * 1000) if entry.lifespan_seconds > 0 else None,
        )

        degradation = DegradationChain(
            primary="default_primary",
            degraded=[
                DegradationStep(
                    condition=f"trust_legacy < {trust_score - 0.1:.2f}",
                    fallback=f"revert_to_parent::{entry.lineage}",
                ),
            ],
        )

        context_activation = ContextActivation(
            file_patterns=[
                f"**/agent/{agent_id}/**",
                f"**/epitaph/{entry.entry_id}/**",
            ],
            entropy_range=(0.2, 0.8),
        )

        behavior: dict[str, Any] = {
            "entrypoint": "caf_refine.main",
            "origin_death_cause": cause,
            "origin_agent": agent_id,
            "origin_lineage": entry.lineage,
            "refined_from_entry": entry.entry_id,
            "trust_legacy": round(trust_score, 4),
            "lifespan_seconds": round(entry.lifespan_seconds, 2),
            "tasks_completed": entry.tasks_completed,
            "tasks_failed": entry.tasks_failed,
            "instructions": (
                f"This skill was refined from agent {agent_id} "
                f"which died of {cause} after {entry.total_lives} lives. "
                f"Trust legacy: {trust_score:.2f}. "
                f"Use CAF reverse-assimilation patterns to avoid repeating this death."
            ),
        }

        maref_skill = MarefSkill(
            maref_skill="1.0",
            meta=meta,
            hexagram_trigger=trigger,
            parameter_injection=param_injection,
            context_activation=context_activation,
            degradation_chain=degradation,
            behavior=behavior,
            skill_id=skill_id,
            source=SkillSource.PROJECT,
        )

        errors = validate_skill_dict(maref_skill.to_dict())
        if errors:
            raise ValueError(
                f"Refined skill validation failed: "
                f"{'; '.join(f'{e.field}: {e.message}' for e in errors)}"
            )

        self._refined[skill_id] = maref_skill
        return maref_skill

    def refine_agent(self, agent_id: str) -> list[MarefSkill]:
        entries = self._shadow.get_by_agent(agent_id)
        if not entries:
            return []
        return [self.refine_from_entry(e) for e in entries]

    def refine_by_cause(self, cause: str) -> list[MarefSkill]:
        entries = self._shadow.get_by_death_cause(cause)
        if not entries:
            return []
        return [self.refine_from_entry(e) for e in entries]

    def refine_all(self) -> list[MarefSkill]:
        return [self.refine_from_entry(e) for e in self._shadow.get_all()]

    def get_skill(self, skill_id: str) -> MarefSkill | None:
        return self._refined.get(skill_id)

    def list_skills(self) -> list[MarefSkill]:
        return list(self._refined.values())

    def count_skills(self) -> int:
        return len(self._refined)

    def refine_lineage(self, lineage_prefix: str) -> list[MarefSkill]:
        entries = self._shadow.get_by_lineage_prefix(lineage_prefix)
        if not entries:
            return []
        return [self.refine_from_entry(e) for e in entries]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_refined": self.count_skills(),
            "refined_skills": [s.to_dict() for s in self._refined.values()],
        }
