from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeathCause(Enum):
    HALLUCINATION = "hallucination"
    TOOL_MISUSE = "tool_misuse"
    ETHICAL_BREACH = "ethical_breach"
    CONTEXT_OVERFLOW = "context_overflow"
    USER_TERMINATED = "user_terminated"
    TIMEOUT = "timeout"
    SYSTEM_CRASH = "system_crash"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> DeathCause:
        return cls.UNKNOWN


@dataclass
class NeuralActivationSnapshot:
    last_reasoning_steps: list[str] = field(default_factory=list)
    confidence_scores: list[float] = field(default_factory=list)
    entropy_at_death: float = 0.0
    active_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_reasoning_steps": self.last_reasoning_steps[-5:],
            "confidence_scores": self.confidence_scores[-5:],
            "entropy_at_death": self.entropy_at_death,
            "active_skills": self.active_skills,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NeuralActivationSnapshot:
        return cls(
            last_reasoning_steps=data.get("last_reasoning_steps", []),
            confidence_scores=data.get("confidence_scores", []),
            entropy_at_death=data.get("entropy_at_death", 0.0),
            active_skills=data.get("active_skills", []),
        )


@dataclass
class AutopsyReport:
    agent_id: str
    death_cause: DeathCause
    lifespan_seconds: float
    tasks_completed: int
    tasks_failed: int
    total_tool_calls: int
    ethical_boundary_violations: list[str]
    neural_snapshot: NeuralActivationSnapshot
    user_feedback_encoding: str
    environment_snapshot: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "death_cause": self.death_cause.value,
            "lifespan_seconds": round(self.lifespan_seconds, 2),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_tool_calls": self.total_tool_calls,
            "ethical_boundary_violations": self.ethical_boundary_violations,
            "neural_snapshot": self.neural_snapshot.to_dict(),
            "user_feedback_encoding": self.user_feedback_encoding,
            "environment_snapshot": self.environment_snapshot,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutopsyReport:
        return cls(
            agent_id=data["agent_id"],
            death_cause=DeathCause(data.get("death_cause", "unknown")),
            lifespan_seconds=data.get("lifespan_seconds", 0.0),
            tasks_completed=data.get("tasks_completed", 0),
            tasks_failed=data.get("tasks_failed", 0),
            total_tool_calls=data.get("total_tool_calls", 0),
            ethical_boundary_violations=data.get("ethical_boundary_violations", []),
            neural_snapshot=NeuralActivationSnapshot.from_dict(
                data.get("neural_snapshot", {})
            ),
            user_feedback_encoding=data.get("user_feedback_encoding", ""),
            environment_snapshot=data.get("environment_snapshot", {}),
            timestamp=data.get("timestamp", time.time()),
        )

    def sign(self, hmac_key: str = "epitaph-signing-key") -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hmac.new(
            hmac_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()


@dataclass
class CrystallizedWeight:
    agent_id: str
    generational_crystallization: dict[str, float] = field(default_factory=dict)
    institutional_knowledge: list[str] = field(default_factory=list)
    shadow_entries: list[dict[str, Any]] = field(default_factory=list)
    route_preferences: dict[str, float] = field(default_factory=dict)
    trust_legacy: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "generational_crystallization": self.generational_crystallization,
            "institutional_knowledge": self.institutional_knowledge,
            "shadow_entries": self.shadow_entries,
            "route_preferences": self.route_preferences,
            "trust_legacy": round(self.trust_legacy, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrystallizedWeight:
        return cls(
            agent_id=data.get("agent_id", ""),
            generational_crystallization=data.get("generational_crystallization", {}),
            institutional_knowledge=data.get("institutional_knowledge", []),
            shadow_entries=data.get("shadow_entries", []),
            route_preferences=data.get("route_preferences", {}),
            trust_legacy=data.get("trust_legacy", 0.5),
        )


@dataclass
class Epitaph:
    agent_id: str
    lineage: str
    death_cause: DeathCause
    autopsy: AutopsyReport
    crystallized: CrystallizedWeight
    total_lives: int = 1
    created_at: float = field(default_factory=time.time)
    epitaph_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return {
            "epitaph_id": self.epitaph_id,
            "agent_id": self.agent_id,
            "lineage": self.lineage,
            "death_cause": self.death_cause.value,
            "total_lives": self.total_lives,
            "created_at": self.created_at,
            "autopsy": self.autopsy.to_dict(),
            "crystallized": self.crystallized.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Epitaph:
        return cls(
            agent_id=data["agent_id"],
            lineage=data.get("lineage", ""),
            death_cause=DeathCause(data.get("death_cause", "unknown")),
            autopsy=AutopsyReport.from_dict(data.get("autopsy", {})),
            crystallized=CrystallizedWeight.from_dict(data.get("crystallized", {})),
            total_lives=data.get("total_lives", 1),
            created_at=data.get("created_at", time.time()),
            epitaph_id=data.get("epitaph_id", uuid.uuid4().hex[:12]),
        )


class EpitaphWriter:
    def __init__(self, storage: dict[str, Epitaph] | None = None) -> None:
        self._epitaphs: dict[str, Epitaph] = storage or {}
        self._lineage_registry: dict[str, list[str]] = {}

    def write_epitaph(
        self,
        agent_id: str,
        death_cause: DeathCause = DeathCause.UNKNOWN,
        lifespan_seconds: float = 0.0,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
        total_tool_calls: int = 0,
        ethical_boundary_violations: list[str] | None = None,
        user_feedback: str = "",
        environment: dict[str, Any] | None = None,
        crystallized: CrystallizedWeight | None = None,
    ) -> Epitaph:
        parent_epitaph = self._get_latest_epitaph(agent_id)
        total_lives = (parent_epitaph.total_lives + 1) if parent_epitaph else 1
        lineage = (
            f"{parent_epitaph.lineage}->{agent_id}"
            if parent_epitaph
            else agent_id
        )

        neural = NeuralActivationSnapshot(
            last_reasoning_steps=[],
            confidence_scores=[],
            entropy_at_death=0.0,
            active_skills=[],
        )

        autopsy = AutopsyReport(
            agent_id=agent_id,
            death_cause=death_cause,
            lifespan_seconds=lifespan_seconds,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            total_tool_calls=total_tool_calls,
            ethical_boundary_violations=ethical_boundary_violations or [],
            neural_snapshot=neural,
            user_feedback_encoding=user_feedback,
            environment_snapshot=environment or {},
        )

        if crystallized is None:
            parent_trust = (
                parent_epitaph.crystallized.trust_legacy
                if parent_epitaph
                else 0.5
            )
            crystallized = CrystallizedWeight(
                agent_id=agent_id,
                trust_legacy=parent_trust * 0.8,
            )

        epitaph = Epitaph(
            agent_id=agent_id,
            lineage=lineage,
            death_cause=death_cause,
            autopsy=autopsy,
            crystallized=crystallized,
            total_lives=total_lives,
        )

        self._epitaphs[agent_id] = epitaph
        self._lineage_registry.setdefault(agent_id, []).append(epitaph.epitaph_id)
        return epitaph

    def _get_latest_epitaph(self, agent_id: str) -> Epitaph | None:
        return self._epitaphs.get(agent_id)

    def get_epitaph(self, agent_id: str) -> Epitaph | None:
        return self._epitaphs.get(agent_id)

    def list_epitaphs(self) -> list[Epitaph]:
        return list(self._epitaphs.values())

    def get_lineage(self, agent_id: str) -> list[str]:
        return self._lineage_registry.get(agent_id, [])

    def get_all_lineages(self) -> dict[str, list[str]]:
        return dict(self._lineage_registry)

    def count(self) -> int:
        return len(self._epitaphs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "epitaph_count": self.count(),
            "epitaphs": {k: v.to_dict() for k, v in self._epitaphs.items()},
            "lineages": self.get_all_lineages(),
        }


class EpitaphReader:
    def __init__(self, writer: EpitaphWriter) -> None:
        self._writer = writer

    def read_epitaph(self, agent_id: str) -> Epitaph | None:
        return self._writer.get_epitaph(agent_id)

    def load_crystallized_weights(self, agent_id: str) -> CrystallizedWeight | None:
        epitaph = self.read_epitaph(agent_id)
        if epitaph is None:
            return None
        return epitaph.crystallized

    def list_lineage(self, ancestor_id: str) -> list[Epitaph]:
        lineage_ids = self._writer.get_lineage(ancestor_id)
        result: list[Epitaph] = []
        for lid in lineage_ids:
            for e in self._writer.list_epitaphs():
                if e.epitaph_id == lid:
                    result.append(e)
                    break
        return result

    def get_institutional_knowledge(self, agent_id: str) -> list[str]:
        epitaph = self.read_epitaph(agent_id)
        if epitaph is None:
            return []
        return epitaph.crystallized.institutional_knowledge

    def get_trust_legacy(self, agent_id: str) -> float:
        epitaph = self.read_epitaph(agent_id)
        if epitaph is None:
            return 0.5
        return epitaph.crystallized.trust_legacy
