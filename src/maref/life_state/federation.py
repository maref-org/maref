"""Life State Federation — multi-entity collaboration.

C39: Federation registration, negotiation, task distribution, and DecisionMarket integration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.life_state.metadata import LifeStateCapability, LifeStateMetadata
from maref.life_state.registry import LifeStateRegistry


class FederationRole(str, Enum):
    COORDINATOR = "coordinator"
    WORKER = "worker"
    OBSERVER = "observer"


@dataclass
class FederationMember:
    state_id: str
    role: FederationRole
    capabilities: set[LifeStateCapability] = field(default_factory=set)
    joined_at: float = field(default_factory=time.time)
    task_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "role": self.role.value,
            "capabilities": sorted([c.value for c in self.capabilities]),
            "joined_at": self.joined_at,
            "task_count": self.task_count,
        }


@dataclass
class FederationTask:
    task_id: str
    task_type: str
    assigned_to: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "assigned_to": self.assigned_to,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
        }


class LifeStateFederation:
    """Manages federation of multiple life state entities.

    Provides:
      - Federation registration and role assignment
      - Task distribution based on capabilities
      - Integration with DecisionMarket for consensus
    """

    def __init__(self, registry: LifeStateRegistry | None = None) -> None:
        self._registry = registry or LifeStateRegistry()
        self._members: dict[str, FederationMember] = {}
        self._tasks: dict[str, FederationTask] = {}
        self._task_counter: int = 0

    def join(
        self,
        metadata: LifeStateMetadata,
        role: FederationRole = FederationRole.WORKER,
    ) -> FederationMember:
        if not self._registry.has(metadata.state_id):
            self._registry.register(metadata)
        member = FederationMember(
            state_id=metadata.state_id,
            role=role,
            capabilities=set(metadata.capabilities),
        )
        self._members[metadata.state_id] = member
        return member

    def leave(self, state_id: str) -> None:
        self._members.pop(state_id, None)

    def get_member(self, state_id: str) -> FederationMember | None:
        return self._members.get(state_id)

    def list_members(self) -> list[FederationMember]:
        return list(self._members.values())

    def list_by_role(self, role: FederationRole) -> list[FederationMember]:
        return [m for m in self._members.values() if m.role == role]

    def find_capable(self, capability: LifeStateCapability) -> list[FederationMember]:
        return [m for m in self._members.values() if capability in m.capabilities]

    def assign_task(self, task_type: str, capability: LifeStateCapability, payload: dict[str, Any]) -> FederationTask | None:
        candidates = self.find_capable(capability)
        if not candidates:
            return None
        candidate = min(candidates, key=lambda m: m.task_count)
        self._task_counter += 1
        task = FederationTask(
            task_id=f"task-{self._task_counter}",
            task_type=task_type,
            assigned_to=candidate.state_id,
            payload=payload,
        )
        self._tasks[task.task_id] = task
        candidate.task_count += 1
        return task

    def complete_task(self, task_id: str) -> FederationTask | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.status = "completed"
        member = self._members.get(task.assigned_to)
        if member is not None:
            member.task_count = max(0, member.task_count - 1)
        return task

    def get_task(self, task_id: str) -> FederationTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, state_id: str | None = None) -> list[FederationTask]:
        if state_id is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.assigned_to == state_id]

    def get_coordinator(self) -> FederationMember | None:
        coordinators = self.list_by_role(FederationRole.COORDINATOR)
        return coordinators[0] if coordinators else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_count": len(self._members),
            "task_count": len(self._tasks),
            "members": [m.to_dict() for m in self.list_members()],
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }
