"""Declarative policy pack schema.

Policy packs are data, not code. They may tighten governance decisions but
must never weaken the core DENY floor.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from maref.governance.canonical_json import canonical_hash

_PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_RULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class PackDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"


class PolicyPackRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=_RULE_ID_RE.pattern)
    action: str = Field(min_length=1, max_length=200)
    decision: PackDecision
    priority: int = Field(default=0, ge=0, le=1000)
    description: str = Field(default="", max_length=500)
    regulation_ref: str = Field(default="", max_length=200)
    conditions: dict[str, Any] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)
    tenants: list[str] = Field(default_factory=list)
    min_trust: float | None = Field(default=None, ge=0, le=100)
    max_trust: float | None = Field(default=None, ge=0, le=100)
    hitl_tier: Literal["P0", "P1", "P2"] = "P1"
    enabled: bool = True

    @field_validator("conditions")
    @classmethod
    def _conditions_are_scalar_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = (str, int, float, bool, type(None))
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("condition keys must be strings")
            if isinstance(item, list):
                if not all(isinstance(entry, allowed) for entry in item):
                    raise ValueError(f"condition {key!r} list must contain scalars")
            elif not isinstance(item, allowed):
                raise ValueError(f"condition {key!r} must be a scalar or scalar list")
        return value

    @model_validator(mode="after")
    def _legal_traceability(self) -> PolicyPackRule:
        if self.decision in (PackDecision.DENY, PackDecision.DEFER):
            if not self.regulation_ref.strip():
                raise ValueError("deny/defer rules require regulation_ref")
        if self.min_trust is not None and self.max_trust is not None:
            if self.min_trust > self.max_trust:
                raise ValueError("min_trust must be <= max_trust")
        return self


class PolicyPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pack_format: Literal[1] = 1
    pack_id: str = Field(pattern=_PACK_ID_RE.pattern)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(pattern=_VERSION_RE.pattern)
    jurisdiction: str = Field(default="*", pattern=r"^(\*|[a-z][a-z0-9_]{1,30})$")
    description: str = Field(default="", max_length=1000)
    core_min: str = Field(default="0.54.0", pattern=_VERSION_RE.pattern)
    core_max: str = Field(default="0.56.0", pattern=_VERSION_RE.pattern)
    rules: list[PolicyPackRule] = Field(min_length=1)
    signature: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> PolicyPack:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.rule_id in seen:
                raise ValueError(f"duplicate rule_id: {rule.rule_id}")
            seen.add(rule.rule_id)
        if _version_tuple(self.core_min) > _version_tuple(self.core_max):
            raise ValueError("core_min must be <= core_max")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return canonical_hash(payload)

    def is_compatible(self, core_version: str) -> bool:
        current = _version_tuple(core_version)
        return _version_tuple(self.core_min) <= current < _version_tuple(self.core_max)


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid version: {value}")
    major, minor, patch = (int(part) for part in parts)
    return (major, minor, patch)
