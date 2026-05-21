from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillSource(str, Enum):
    BUILTIN = "builtin"
    PROJECT = "project"
    USER = "user"
    MCP_REMOTE = "mcp_remote"


SOURCE_PRIORITY = {
    SkillSource.BUILTIN: 0,
    SkillSource.PROJECT: 1,
    SkillSource.USER: 2,
    SkillSource.MCP_REMOTE: 3,
}


@dataclass
class MarefSkillMeta:
    name: str
    version: str
    description: str
    author_did: str | None = None


@dataclass
class HexagramTrigger:
    require: list[int] = field(default_factory=list)
    exclude: list[int] = field(default_factory=list)
    transition_from: list[int] | None = None


@dataclass
class ParameterInjection:
    model_override: str | None = None
    effort: str | None = None
    timeout_ms: int | None = None


@dataclass
class DegradationStep:
    condition: str
    fallback: str


@dataclass
class DegradationChain:
    primary: str
    degraded: list[DegradationStep] = field(default_factory=list)


@dataclass
class ContextActivation:
    file_patterns: list[str] = field(default_factory=list)
    entropy_range: tuple[float, float] | None = None


@dataclass
class SkillHookRef:
    event: str
    handler: str


@dataclass
class MarefSkill:
    maref_skill: str
    meta: MarefSkillMeta
    role_affinity: dict[str, Any] = field(default_factory=dict)
    hexagram_trigger: HexagramTrigger = field(default_factory=HexagramTrigger)
    parameter_injection: ParameterInjection | None = None
    hooks: list[SkillHookRef] = field(default_factory=list)
    context_activation: ContextActivation | None = None
    degradation_chain: DegradationChain = field(default_factory=DegradationChain)
    behavior: dict[str, Any] = field(default_factory=dict)
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: SkillSource = SkillSource.BUILTIN
    loaded_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def version(self) -> str:
        return self.meta.version

    def matches_hexagram(self, current: int, previous: int | None = None) -> bool:
        trigger = self.hexagram_trigger
        if trigger.require and current not in trigger.require:
            return False
        if trigger.exclude and current in trigger.exclude:
            return False
        return not (trigger.transition_from is not None and previous is not None and previous not in trigger.transition_from)

    def matches_context(self, file_path: str, entropy: float | None = None) -> bool:
        if self.context_activation is None:
            return True
        ca = self.context_activation
        import fnmatch

        for pattern in ca.file_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                break
        else:
            if ca.file_patterns:
                return False
        if ca.entropy_range is not None and entropy is not None:
            lo, hi = ca.entropy_range
            if not (lo <= entropy <= hi):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "maref_skill": self.maref_skill,
            "meta": {
                "name": self.meta.name,
                "version": self.meta.version,
                "description": self.meta.description,
                "author_did": self.meta.author_did,
            },
            "role_affinity": self.role_affinity,
            "hexagram_trigger": {
                "require": self.hexagram_trigger.require,
                "exclude": self.hexagram_trigger.exclude,
                "transition_from": self.hexagram_trigger.transition_from,
            },
            "parameter_injection": (
                {
                    "model_override": self.parameter_injection.model_override,
                    "effort": self.parameter_injection.effort,
                    "timeout_ms": self.parameter_injection.timeout_ms,
                }
                if self.parameter_injection
                else None
            ),
            "hooks": [{"event": h.event, "handler": h.handler} for h in self.hooks],
            "context_activation": (
                {
                    "file_patterns": self.context_activation.file_patterns,
                    "entropy_range": list(self.context_activation.entropy_range)
                    if self.context_activation.entropy_range
                    else None,
                }
                if self.context_activation
                else None
            ),
            "degradation_chain": {
                "primary": self.degradation_chain.primary,
                "degraded": [
                    {"condition": d.condition, "fallback": d.fallback}
                    for d in self.degradation_chain.degraded
                ],
            },
            "behavior": self.behavior,
            "skill_id": self.skill_id,
            "source": self.source.value,
        }


@dataclass
class SkillValidationError:
    field: str
    message: str


def validate_skill_dict(data: dict[str, Any]) -> list[SkillValidationError]:
    errors: list[SkillValidationError] = []

    if data.get("maref_skill") != "1.0":
        errors.append(SkillValidationError(
            field="maref_skill",
            message="maref_skill must be '1.0'",
        ))

    meta = data.get("meta", {})
    if not meta.get("name"):
        errors.append(SkillValidationError(field="meta.name", message="name is required"))
    if not meta.get("version"):
        errors.append(SkillValidationError(field="meta.version", message="version is required"))
    if not meta.get("description"):
        errors.append(SkillValidationError(field="meta.description", message="description is required"))

    trigger = data.get("hexagram_trigger", {})
    require = trigger.get("require", [])
    for val in require:
        if not (0 <= val <= 63):
            errors.append(SkillValidationError(
                field="hexagram_trigger.require",
                message=f"hexagram value {val} out of range 0-63",
            ))
    exclude = trigger.get("exclude", [])
    for val in exclude:
        if not (0 <= val <= 63):
            errors.append(SkillValidationError(
                field="hexagram_trigger.exclude",
                message=f"hexagram value {val} out of range 0-63",
            ))
    tf = trigger.get("transition_from")
    if tf is not None:
        for val in tf:
            if not (0 <= val <= 63):
                errors.append(SkillValidationError(
                    field="hexagram_trigger.transition_from",
                    message=f"hexagram value {val} out of range 0-63",
                ))

    dc = data.get("degradation_chain")
    if dc and not dc.get("primary"):
        errors.append(SkillValidationError(
            field="degradation_chain.primary",
            message="primary is required in degradation_chain",
        ))

    behavior = data.get("behavior", {})
    if not behavior.get("entrypoint"):
        errors.append(SkillValidationError(
            field="behavior.entrypoint",
            message="behavior.entrypoint is required",
        ))

    return errors


def parse_skill_from_dict(data: dict[str, Any], source: SkillSource = SkillSource.BUILTIN) -> MarefSkill:
    errors = validate_skill_dict(data)
    if errors:
        msg = "; ".join(f"{e.field}: {e.message}" for e in errors)
        raise ValueError(f"Skill validation failed: {msg}")

    meta_raw = data["meta"]
    meta = MarefSkillMeta(
        name=meta_raw["name"],
        version=meta_raw["version"],
        description=meta_raw.get("description", ""),
        author_did=meta_raw.get("author_did"),
    )

    trigger_raw = data.get("hexagram_trigger", {})
    hex_trigger = HexagramTrigger(
        require=trigger_raw.get("require", []),
        exclude=trigger_raw.get("exclude", []),
        transition_from=trigger_raw.get("transition_from"),
    )

    pi_raw = data.get("parameter_injection")
    param_injection = None
    if pi_raw:
        param_injection = ParameterInjection(
            model_override=pi_raw.get("model_override"),
            effort=pi_raw.get("effort"),
            timeout_ms=pi_raw.get("timeout_ms"),
        )

    hooks = [
        SkillHookRef(event=h["event"], handler=h["handler"])
        for h in data.get("hooks", [])
    ]

    ca_raw = data.get("context_activation")
    context_activation = None
    if ca_raw:
        entropy = None
        if ca_raw.get("entropy_range"):
            entropy = tuple(ca_raw["entropy_range"])
        context_activation = ContextActivation(
            file_patterns=ca_raw.get("file_patterns", []),
            entropy_range=entropy,
        )

    dc_raw = data.get("degradation_chain", {})
    degraded = [
        DegradationStep(condition=d["condition"], fallback=d["fallback"])
        for d in dc_raw.get("degraded", [])
    ]
    deg_chain = DegradationChain(
        primary=dc_raw.get("primary", "default"),
        degraded=degraded,
    )

    return MarefSkill(
        maref_skill=data["maref_skill"],
        meta=meta,
        role_affinity=data.get("role_affinity", {}),
        hexagram_trigger=hex_trigger,
        parameter_injection=param_injection,
        hooks=hooks,
        context_activation=context_activation,
        degradation_chain=deg_chain,
        behavior=data.get("behavior", {}),
        source=source,
    )
