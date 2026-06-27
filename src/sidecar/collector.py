from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import deque
from typing import Any

from sidecar.protocol import (
    AgentId,
    AgentState,
    EntropyReading,
    Observation,
    ObservationType,
    StateSnapshot,
)

logger = logging.getLogger(__name__)


class AgentAdapter(ABC):
    @abstractmethod
    async def list_agents(self) -> list[AgentId]:
        ...

    @abstractmethod
    async def get_state(self, name: AgentId) -> StateSnapshot | None:
        ...

    @abstractmethod
    async def get_entropy(self, name: AgentId) -> EntropyReading | None:
        ...


class MockAgentAdapter(AgentAdapter):
    def __init__(self, namespace: str = "test", num_agents: int = 3) -> None:
        self._agents: dict[AgentId, None] = {}
        self._states: dict[str, StateSnapshot] = {}
        self._entropies: dict[str, EntropyReading] = {}
        for i in range(num_agents):
            aid = AgentId(namespace=namespace, name=f"agent_{i}")
            self._agents[aid] = None
            self._states[str(aid)] = StateSnapshot(agent_id=aid, state=AgentState.IDLE)
            self._entropies[str(aid)] = EntropyReading(source=str(aid), value=0.0, level="normal")

    async def list_agents(self) -> list[AgentId]:
        return list(self._agents.keys())

    async def get_state(self, name: AgentId) -> StateSnapshot:
        return self._states[str(name)]

    async def get_entropy(self, name: AgentId) -> EntropyReading:
        return self._entropies[str(name)]

    def set_state(
        self,
        name: AgentId,
        state: AgentState,
        current_task: str | None = None,
        task_progress: float = 0.0,
        pending_messages: list[str] | None = None,
    ) -> None:
        key = str(name)
        self._states[key] = StateSnapshot(
            agent_id=name,
            state=state,
            current_task=current_task or "",
            task_progress=task_progress,
            pending_messages=len(pending_messages) if pending_messages else 0,
        )

    def set_task(
        self,
        name: AgentId,
        state: AgentState,
        pending_messages: list[str] | None = None,
    ) -> None:
        key = str(name)
        self._states[key] = StateSnapshot(
            agent_id=name,
            state=state,
            pending_messages=len(pending_messages) if pending_messages else 0,
        )

    def set_pending(
        self,
        name: AgentId,
        state: AgentState,
        current_task: str | None = None,
        task_progress: float = 0.0,
    ) -> None:
        key = str(name)
        self._states[key] = StateSnapshot(
            agent_id=name,
            state=state,
            current_task=current_task or "",
            task_progress=task_progress,
        )

    def set_entropy(self, name: AgentId, entropy: float) -> None:
        level = "normal"
        if entropy >= 3.0:
            level = "critical"
        elif entropy >= 1.5:
            level = "warning"
        self._entropies[str(name)] = EntropyReading(source=str(name), value=entropy, level=level)


class ObservationCollector:
    def __init__(self, adapter: AgentAdapter, buffer_size: int = 1000, poll_interval: float = 1.0) -> None:
        self._adapter = adapter
        self._buffer_size = buffer_size
        self._poll_interval = poll_interval
        self._buffer: deque[Observation] = deque(maxlen=buffer_size)
        self._callbacks: list[Any] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._anomaly_detected = False
        self._consecutive_clean = 0

    def add_callback(self, cb: Any) -> None:
        self._callbacks.append(cb)

    def remove_callback(self, cb: Any) -> None:
        self._callbacks.remove(cb)

    def notify_anomaly(self) -> None:
        self._anomaly_detected = True

    def get_recent(self, n: int | None = None) -> list[Observation]:
        if n is None:
            return list(self._buffer)
        return list(self._buffer)[-n:]

    def get_buffer_size(self) -> int:
        return len(self._buffer)

    async def collect_once(self) -> list[Observation]:
        observations: list[Observation] = []
        try:
            agents = await self._adapter.list_agents()
            for agent_id in agents:
                state = await self._adapter.get_state(agent_id)
                state_obs = Observation(
                    obs_type=ObservationType.STATE_SNAPSHOT,
                    payload=state,
                    source=str(agent_id),
                )
                self._push_observation(state_obs)
                observations.append(state_obs)

                entropy = await self._adapter.get_entropy(agent_id)
                entropy_obs = Observation(
                    obs_type=ObservationType.ENTROPY_METRIC,
                    payload=entropy,
                    source=str(agent_id),
                )
                self._push_observation(entropy_obs)
                observations.append(entropy_obs)
            self._consecutive_clean += 1
            if self._anomaly_detected:
                anomaly_obs = Observation(
                    obs_type=ObservationType.ANOMALY,
                    payload={"anomaly_detected": True},
                    source="collector",
                )
                self._push_observation(anomaly_obs)
                observations.append(anomaly_obs)
                self._anomaly_detected = False
        except Exception:
            logger.exception("Error during collect_once")
        return observations

    def _push_observation(self, obs: Observation) -> None:
        self._buffer.append(obs)
        for cb in self._callbacks:
            try:
                cb(obs)
            except Exception:
                logger.exception("Error in observation callback")

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self.collect_once()
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
