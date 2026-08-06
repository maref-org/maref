from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrajectoryEventType(str, Enum):
    """Types of events that can be recorded in a trajectory."""

    TASK_CREATED = "task_created"
    TASK_STATE_CHANGED = "task_state_changed"
    DELEGATION_SENT = "delegation_sent"
    MESSAGE_EXCHANGED = "message_exchanged"
    TASK_COMPLETED = "task_completed"


@dataclass
class TrajectoryEvent:
    """A single event in a task trajectory."""

    event_id: str
    timestamp: float
    task_id: str
    event_type: TrajectoryEventType
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrajectoryEvent:
        return cls(
            event_id=data["event_id"],
            timestamp=data["timestamp"],
            task_id=data["task_id"],
            event_type=TrajectoryEventType(data["event_type"]),
            actor=data["actor"],
            payload=data.get("payload", {}),
        )


@dataclass
class TaskTrajectory:
    """Complete trajectory of a single task execution."""

    task_id: str
    description: str
    created_at: float
    events: list[TrajectoryEvent] = field(default_factory=list)
    delegations: list[dict[str, Any]] = field(default_factory=list)
    final_state: str | None = None
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "created_at": self.created_at,
            "events": [e.to_dict() for e in self.events],
            "delegations": self.delegations,
            "final_state": self.final_state,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskTrajectory:
        return cls(
            task_id=data["task_id"],
            description=data["description"],
            created_at=data["created_at"],
            events=[TrajectoryEvent.from_dict(e) for e in data.get("events", [])],
            delegations=data.get("delegations", []),
            final_state=data.get("final_state"),
            completed_at=data.get("completed_at"),
        )


class TrajectoryCollector:
    """Collects and exports execution trajectories for MAS-TS-001 D2/D3 scoring.

    Follows the existing @dataclass + to_dict() pattern used across the codebase.
    """

    def __init__(self, agent_id: str = "urn:agent:maref:0-35-0-beta:main") -> None:
        self._agent_id = agent_id
        self._trajectories: dict[str, TaskTrajectory] = {}

    def start_task(self, task_id: str, description: str, actor: str = "") -> TaskTrajectory:
        now = time.time()
        traj = TaskTrajectory(
            task_id=task_id,
            description=description,
            created_at=now,
        )
        traj.events.append(
            TrajectoryEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                task_id=task_id,
                event_type=TrajectoryEventType.TASK_CREATED,
                actor=actor or self._agent_id,
                payload={"description": description},
            )
        )
        self._trajectories[task_id] = traj
        return traj

    def complete_task(self, task_id: str, final_state: str = "completed") -> None:
        traj = self._trajectories.get(task_id)
        if traj is None:
            return
        now = time.time()
        traj.final_state = final_state
        traj.completed_at = now
        traj.events.append(
            TrajectoryEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                task_id=task_id,
                event_type=TrajectoryEventType.TASK_COMPLETED,
                actor=self._agent_id,
                payload={"final_state": final_state},
            )
        )

    def record_event(
        self,
        task_id: str,
        event_type: TrajectoryEventType,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        traj = self._trajectories.get(task_id)
        if traj is None:
            return
        traj.events.append(
            TrajectoryEvent(
                event_id=str(uuid.uuid4()),
                timestamp=time.time(),
                task_id=task_id,
                event_type=event_type,
                actor=actor,
                payload=payload or {},
            )
        )

    def record_message(
        self,
        task_id: str,
        direction: str,
        sender: str,
        recipient: str,
        content: str,
    ) -> None:
        traj = self._trajectories.get(task_id)
        if traj is None:
            return
        traj.events.append(
            TrajectoryEvent(
                event_id=str(uuid.uuid4()),
                timestamp=time.time(),
                task_id=task_id,
                event_type=TrajectoryEventType.MESSAGE_EXCHANGED,
                actor=sender,
                payload={
                    "direction": direction,
                    "sender": sender,
                    "recipient": recipient,
                    "content_length": len(content),
                },
            )
        )

    def record_delegation(self, task_id: str, target_agent_url: str) -> None:
        traj = self._trajectories.get(task_id)
        if traj is None:
            return
        now = time.time()
        delegation = {"target_agent_url": target_agent_url, "delegated_at": now}
        traj.delegations.append(delegation)
        traj.events.append(
            TrajectoryEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                task_id=task_id,
                event_type=TrajectoryEventType.DELEGATION_SENT,
                actor=self._agent_id,
                payload=delegation,
            )
        )

    def get_trajectory(self, task_id: str) -> TaskTrajectory | None:
        return self._trajectories.get(task_id)

    def get_all_trajectories(self) -> list[TaskTrajectory]:
        return list(self._trajectories.values())

    def get_single_agent_trajectories(self) -> list[TaskTrajectory]:
        """Return trajectories with no delegations (D2: single-agent)."""
        return [t for t in self._trajectories.values() if not t.delegations]

    def get_multi_agent_trajectories(self) -> list[TaskTrajectory]:
        """Return trajectories with delegations (D3: multi-agent)."""
        return [t for t in self._trajectories.values() if t.delegations]

    def export_json(self) -> str:
        return json.dumps(
            [t.to_dict() for t in self._trajectories.values()],
            indent=2,
            ensure_ascii=False,
        )

    def export_single_agent_json(self) -> str:
        return json.dumps(
            [t.to_dict() for t in self.get_single_agent_trajectories()],
            indent=2,
            ensure_ascii=False,
        )

    def export_multi_agent_json(self) -> str:
        return json.dumps(
            [t.to_dict() for t in self.get_multi_agent_trajectories()],
            indent=2,
            ensure_ascii=False,
        )


__all__ = [
    "TrajectoryEventType",
    "TrajectoryEvent",
    "TaskTrajectory",
    "TrajectoryCollector",
]
