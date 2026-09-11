from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id

if TYPE_CHECKING:
    from maref.crypto.ed25519_keys import Ed25519KeyPair


class PheromoneType(str, Enum):
    TASK_READY = "task_ready"
    RESOURCE_FOUND = "resource_found"
    DANGER_SIGNAL = "danger_signal"
    COMPLETION_MARKER = "completion_marker"
    RECRUITMENT = "recruitment"


@dataclass
class Pheromone:
    stig_id: str
    pheromone_type: PheromoneType
    source_agent: str
    location: str
    intensity: float = 1.0
    decay_rate: float = 0.1
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    signer_fingerprint: str = ""

    @property
    def current_intensity(self) -> float:
        elapsed = (time.time() - self.created_at) / 3600.0
        return max(0.0, self.intensity * (1.0 - elapsed * self.decay_rate))

    def _payload_for_signing(self) -> str:
        return json.dumps(
            {
                "stig_id": self.stig_id,
                "pheromone_type": self.pheromone_type.value,
                "source_agent": self.source_agent,
                "location": self.location,
                "intensity": self.intensity,
                "decay_rate": self.decay_rate,
                "created_at": self.created_at,
                "metadata": self.metadata,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def sign(self, signer: Ed25519KeyPair) -> None:
        sig_bytes = signer.sign(self._payload_for_signing().encode("utf-8"))
        self.signature = sig_bytes.hex()
        self.signer_fingerprint = signer.fingerprint

    def verify_signature(self, public_key_pem: str) -> bool:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        if not self.signature:
            return False
        sig_bytes = bytes.fromhex(self.signature)
        return Ed25519KeyPair.verify(
            public_key_pem, sig_bytes, self._payload_for_signing().encode("utf-8")
        )


@dataclass
class StigmergyEnvironment:
    env_id: str
    capacity: int = 20
    pheromones: dict[str, Pheromone] = field(default_factory=dict)
    task_queue: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)


@dataclass
class SwarmMember:
    agent_id: str
    role: str = "worker"
    task_preference: list[str] = field(default_factory=list)
    active: bool = True
    completed_count: int = 0


@dataclass
class EmergenceResult:
    detected: bool
    pattern_type: str = ""
    participants: list[str] = field(default_factory=list)
    coordination_success: bool = False
    phase_transition_count: int = 0


class StigmergySwarm:
    MIN_EMERGENCE_AGENTS = 2
    MAX_EMERGENCE_AGENTS = 30
    INTENSITY_THRESHOLD = 0.3

    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._environments: dict[str, StigmergyEnvironment] = {}
        self._members: dict[str, SwarmMember] = {}
        self._pheromone_ids: dict[str, str] = {}
        self._emergence_events: list[EmergenceResult] = []
        self._audit_store = audit_store or UnifiedAuditStore()

    def create_environment(self, env_id: str, capacity: int = 20) -> StigmergyEnvironment:
        env = StigmergyEnvironment(env_id=env_id, capacity=capacity)
        self._environments[env_id] = env
        return env

    def register_member(
        self, agent_id: str, role: str = "worker", preferences: list[str] | None = None
    ) -> SwarmMember:
        member = SwarmMember(
            agent_id=agent_id,
            role=role,
            task_preference=preferences or [],
        )
        self._members[agent_id] = member
        return member

    def deposit_pheromone(
        self,
        env_id: str,
        agent_id: str,
        p_type: PheromoneType,
        location: str,
        intensity: float = 1.0,
        metadata: dict[str, Any] | None = None,
        signer: Any | None = None,
    ) -> Pheromone | None:
        env = self._environments.get(env_id)
        if env is None:
            return None
        if agent_id not in self._members:
            return None

        stig_id = f"stig_{env_id}_{agent_id}_{int(time.time() * 1000)}"
        p = Pheromone(
            stig_id=stig_id,
            pheromone_type=p_type,
            source_agent=agent_id,
            location=location,
            intensity=intensity,
            metadata=metadata or {},
        )
        if signer is not None:
            p.sign(signer)
        env.pheromones[p.stig_id] = p
        self._pheromone_ids[stig_id] = env_id
        return p

    def sense_pheromones(self, env_id: str, agent_id: str) -> list[Pheromone]:
        env = self._environments.get(env_id)
        if env is None or agent_id not in self._members:
            return []

        active: list[Pheromone] = []
        for p in env.pheromones.values():
            if p.current_intensity > self.INTENSITY_THRESHOLD:
                if p.source_agent != agent_id:
                    active.append(p)
        return sorted(active, key=lambda p: -p.current_intensity)

    def add_task(self, env_id: str, task_id: str) -> bool:
        env = self._environments.get(env_id)
        if env is None:
            return False
        if len(env.task_queue) >= env.capacity:
            return False
        env.task_queue.append(task_id)
        return True

    def assign_task(self, env_id: str, task_id: str, agent_id: str) -> bool:
        env = self._environments.get(env_id)
        if env is None:
            return False
        member = self._members.get(agent_id)
        if member is None:
            return False

        if task_id not in env.task_queue:
            return False

        env.task_queue.remove(task_id)
        env.completed_tasks.append(task_id)
        member.completed_count += 1
        return True

    def detect_emergence(self, env_id: str) -> EmergenceResult:
        env = self._environments.get(env_id)
        if env is None:
            return EmergenceResult(detected=False)

        active_agents = sum(1 for m in self._members.values() if m.active)
        pheromone_count = len(
            [p for p in env.pheromones.values() if p.current_intensity > self.INTENSITY_THRESHOLD]
        )

        coordinated = (
            active_agents >= self.MIN_EMERGENCE_AGENTS
            and len(env.completed_tasks) > 0
            and pheromone_count >= active_agents
        )

        phase_transitions = len(self._emergence_events)

        result = EmergenceResult(
            detected=coordinated,
            pattern_type="swarm_coordination" if coordinated else "none",
            participants=list(self._members.keys()),
            coordination_success=coordinated,
            phase_transition_count=phase_transitions,
        )

        if coordinated:
            self._emergence_events.append(result)
            self._audit_store.append(
                UnifiedAuditRecord(
                    record_id=make_record_id("swarm", hash(env_id) % 100000),
                    timestamp=time.time(),
                    layer="evolution",
                    round=47,
                    event_type="emergence_detected",
                    source_module="StigmergySwarm",
                    target_module=env_id,
                    decision="emergence_coordinated",
                    justification=f"Agents={active_agents}, pheromones={pheromone_count}",
                    outcome="success",
                    context_refs=[env_id],
                )
            )

        return result

    def run_swarm_cycle(self, env_id: str, tasks: list[str], agents: list[str]) -> EmergenceResult:
        env = self._environments.get(env_id)
        if env is None:
            self.create_environment(env_id)

        for agent_id in agents:
            if agent_id not in self._members:
                self.register_member(agent_id)

        for task_id in tasks:
            self.add_task(env_id, task_id)

        for agent_id in agents:
            self.deposit_pheromone(
                env_id,
                agent_id,
                PheromoneType.RECRUITMENT,
                location="task_board",
                intensity=0.8,
            )

        assigned = tasks[: len(agents)]
        for i, task_id in enumerate(assigned):
            if i < len(agents):
                self.assign_task(env_id, task_id, agents[i])

        for agent_id in agents:
            self.deposit_pheromone(
                env_id,
                agent_id,
                PheromoneType.COMPLETION_MARKER,
                location="completed",
                intensity=0.9,
            )

        return self.detect_emergence(env_id)

    def register_multiple(self, count: int, prefix: str = "swarm_agent") -> list[SwarmMember]:
        members: list[SwarmMember] = []
        for i in range(count):
            agent_id = f"{prefix}_{i}"
            member = self.register_member(agent_id)
            members.append(member)
        return members

    def get_statistics(self) -> dict[str, Any]:
        return {
            "total_members": len(self._members),
            "active_members": sum(1 for m in self._members.values() if m.active),
            "environments": len(self._environments),
            "emergence_events": len(self._emergence_events),
            "total_completed": sum(len(e.completed_tasks) for e in self._environments.values()),
        }

    @property
    def member_count(self) -> int:
        return len(self._members)

    def clear(self) -> None:
        self._environments.clear()
        self._members.clear()
        self._pheromone_ids.clear()
        self._emergence_events.clear()
