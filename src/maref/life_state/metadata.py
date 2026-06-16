"""Life State Metadata — core definitions for living state entities.

C31: Defines what a "life state" is and establishes a unified metadata model.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LifeStateType(str, Enum):
    """The five canonical life state types."""

    AGENT = "agent"
    SERVICE = "service"
    PIPELINE = "pipeline"
    KNOWLEDGE = "knowledge"
    GOVERNANCE = "governance"


class LifeStateCapability(str, Enum):
    """Capabilities a life state entity may possess."""

    COMPUTE = "compute"
    REASON = "reason"
    LEARN = "learn"
    COMMUNICATE = "communicate"
    HEAL = "heal"
    REPRODUCE = "reproduce"
    OBSERVE = "observe"
    GOVERN = "govern"
    EVOLVE = "evolve"


@dataclass
class LifeStateMetadata:
    """Metadata describing a living state entity.

    Attributes:
        state_id: Unique identifier (UUIDv7-style hex).
        state_type: One of the five canonical types.
        version: Semantic version string.
        capabilities: Set of capabilities this entity possesses.
        health_score: Dynamic health score (0-100).
        birth_time: Unix timestamp when the entity was created.
        lineage: Parent state_id, if any.
        labels: Arbitrary key-value labels for discovery.
        metadata_version: Schema version of this metadata object.
    """

    state_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    state_type: LifeStateType = LifeStateType.AGENT
    version: str = "0.1.0"
    capabilities: set[LifeStateCapability] = field(default_factory=set)
    health_score: float = 100.0
    birth_time: float = field(default_factory=time.time)
    lineage: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    metadata_version: str = "1.0"

    def __post_init__(self) -> None:
        if not isinstance(self.capabilities, set):
            self.capabilities = set(self.capabilities)
        if not isinstance(self.labels, dict):
            self.labels = dict(self.labels)
        self._clamp_health()

    def _clamp_health(self) -> None:
        self.health_score = max(0.0, min(100.0, float(self.health_score)))

    def add_capability(self, capability: LifeStateCapability) -> None:
        self.capabilities.add(capability)

    def remove_capability(self, capability: LifeStateCapability) -> None:
        self.capabilities.discard(capability)

    def has_capability(self, capability: LifeStateCapability) -> bool:
        return capability in self.capabilities

    def update_health(self, score: float) -> None:
        self.health_score = score
        self._clamp_health()

    def set_label(self, key: str, value: str) -> None:
        self.labels[key] = value

    def get_label(self, key: str, default: str = "") -> str:
        return self.labels.get(key, default)

    def age_seconds(self) -> float:
        return time.time() - self.birth_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "state_type": self.state_type.value,
            "version": self.version,
            "capabilities": sorted([c.value for c in self.capabilities]),
            "health_score": round(self.health_score, 2),
            "birth_time": self.birth_time,
            "lineage": self.lineage,
            "labels": dict(self.labels),
            "metadata_version": self.metadata_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LifeStateMetadata:
        return cls(
            state_id=data.get("state_id", uuid.uuid4().hex[:16]),
            state_type=LifeStateType(data.get("state_type", "agent")),
            version=data.get("version", "0.1.0"),
            capabilities={LifeStateCapability(c) for c in data.get("capabilities", [])},
            health_score=data.get("health_score", 100.0),
            birth_time=data.get("birth_time", time.time()),
            lineage=data.get("lineage"),
            labels=dict(data.get("labels", {})),
            metadata_version=data.get("metadata_version", "1.0"),
        )
