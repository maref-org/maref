from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from maref.governance.types import GovernanceState
from maref.identity.did_registry import AgentDID


class JointState(str, Enum):
    IDLE = "idle"
    COORDINATING = "coordinating"
    SYNCING = "syncing"
    STABILIZING = "stabilizing"
    COMPLETED = "completed"
    HALTED = "halted"


@dataclass
class AgentSlot:
    agent_did: AgentDID
    maref_state: GovernanceState
    last_sync: float
    barrier_version: int


class JointStateMachine:
    def __init__(self, max_sync_deviation_ms: float = 10.0) -> None:
        self._state = JointState.IDLE
        self._slots: dict[AgentDID, AgentSlot] = {}
        self._barrier_version = 0
        self._max_deviation = max_sync_deviation_ms

    def register_agent(self, did: AgentDID, initial_state: GovernanceState = GovernanceState.INIT) -> None:
        self._slots[did] = AgentSlot(
            agent_did=did,
            maref_state=initial_state,
            last_sync=time.time(),
            barrier_version=self._barrier_version,
        )
        self._state = JointState.COORDINATING

    def sync_agent(self, did: AgentDID, new_state: GovernanceState) -> float:
        if did not in self._slots:
            raise ValueError(f"Unknown agent: {did.did_string}")
        before = time.perf_counter()
        self._slots[did].maref_state = new_state
        self._slots[did].last_sync = time.time()
        self._slots[did].barrier_version = self._barrier_version
        delta_ms = (time.perf_counter() - before) * 1000
        self._check_sync_deviation()
        return delta_ms

    def _check_sync_deviation(self) -> None:
        sync_times = [slot.last_sync for slot in self._slots.values()]
        if len(sync_times) <= 1:
            return
        max_time = max(sync_times)
        min_time = min(sync_times)
        deviation = (max_time - min_time) * 1000
        if deviation > self._max_deviation:
            self._state = JointState.STABILIZING
            self._barrier_version += 1
            for slot in self._slots.values():
                slot.barrier_version = self._barrier_version

    def advance_barrier(self) -> int:
        self._barrier_version += 1
        for slot in self._slots.values():
            slot.barrier_version = self._barrier_version
            slot.last_sync = time.time()
        self._state = JointState.SYNCING
        return self._barrier_version

    def force_halt(self, reason: str = "") -> None:
        self._state = JointState.HALTED
        for slot in self._slots.values():
            slot.maref_state = GovernanceState.HALT

    def force_stabilize(self, reason: str = "") -> None:
        self._state = JointState.STABILIZING
        self._barrier_version += 1
        for slot in self._slots.values():
            slot.maref_state = GovernanceState.STABILIZE
            slot.barrier_version = self._barrier_version

    @property
    def current_state(self) -> JointState:
        return self._state

    @property
    def barrier_version(self) -> int:
        return self._barrier_version

    @property
    def agent_count(self) -> int:
        return len(self._slots)

    def get_slot(self, did: AgentDID) -> AgentSlot | None:
        return self._slots.get(did)
