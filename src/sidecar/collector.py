from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable

from sidecar.protocol import (
    AgentId,
    AgentState,
    EntropyReading,
    Observation,
    ObservationType,
    StateSnapshot,
)


class AgentAdapter(ABC):
    @abstractmethod
    async def list_agents(self) -> list[AgentId]:
        ...

    @abstractmethod
    async def get_state(self, agent_id: AgentId) -> StateSnapshot | None:
        ...

    @abstractmethod
    async def get_entropy(self, agent_id: AgentId) -> EntropyReading | None:
        ...


class MockAgentAdapter(AgentAdapter):
    def __init__(self, num_agents: int = 2) -> None:
        self._agents: dict[str, AgentId] = {}
        self._states: dict[str, StateSnapshot] = {}
        self._entropies: dict[str, float] = {}
        self._namespace = "mock"
        for i in range(num_agents):
            agent_id = AgentId(name=f"agent-{i}", namespace=self._namespace)
            self._agents[agent_id.name] = agent_id
            self._states[agent_id.name] = StateSnapshot(
                agent_id=agent_id,
                state=AgentState.IDLE,
            )
            self._entropies[agent_id.name] = 0.0

    async def list_agents(self) -> list[AgentId]:
        return list(self._agents.values())

    async def get_state(self, agent_id: AgentId) -> StateSnapshot | None:
        key = agent_id.name
        if key not in self._agents:
            return None
        state = self._states.get(key)
        if state is None:
            return None
        return StateSnapshot(
            agent_id=state.agent_id,
            state=state.state,
            current_task=state.current_task,
            task_progress=state.task_progress,
            pending_messages=state.pending_messages,
        )

    async def get_entropy(self, agent_id: AgentId) -> EntropyReading | None:
        key = agent_id.name
        if key not in self._agents:
            return None
        value = self._entropies.get(key, 0.0)
        if value >= 3.0:
            level = "critical"
        elif value >= 1.5:
            level = "warning"
        else:
            level = "normal"
        return EntropyReading(
            agent_id=agent_id,
            value=value,
            level=level,
        )

    def set_state(self, agent_id: AgentId, state: AgentState) -> None:
        key = agent_id.name
        if key in self._states:
            old = self._states[key]
            self._states[key] = StateSnapshot(
                agent_id=old.agent_id,
                state=state,
                current_task=old.current_task,
                task_progress=old.task_progress,
                pending_messages=old.pending_messages,
            )

    def set_task(self, agent_id: AgentId, task: str, progress: float = 0.0) -> None:
        key = agent_id.name
        if key in self._states:
            old = self._states[key]
            self._states[key] = StateSnapshot(
                agent_id=old.agent_id,
                state=old.state,
                current_task=task,
                task_progress=progress,
                pending_messages=old.pending_messages,
            )

    def set_pending(self, agent_id: AgentId, count: int) -> None:
        key = agent_id.name
        if key in self._states:
            old = self._states[key]
            self._states[key] = StateSnapshot(
                agent_id=old.agent_id,
                state=old.state,
                current_task=old.current_task,
                task_progress=old.task_progress,
                pending_messages=count,
            )

    def set_entropy(self, agent_id: AgentId, value: float) -> None:
        key = agent_id.name
        if key in self._entropies:
            self._entropies[key] = value


class ObservationCollector:
    def __init__(
        self,
        adapter: AgentAdapter,
        buffer_size: int = 1000,
        poll_interval: float = 1.0,
    ) -> None:
        self._adapter = adapter
        self._buffer_size = buffer_size
        self._base_interval = poll_interval
        self._current_interval = poll_interval
        self._buffer: list[Observation] = []
        self._callbacks: list[Callable[[Observation], None]] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._anomaly_detected = False
        self._consecutive_clean = 0

    def add_callback(self, callback: Callable[[Observation], None]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Observation], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def notify_anomaly(self) -> None:
        self._anomaly_detected = True
        self._consecutive_clean = 0
        self._current_interval = self._base_interval

    def get_recent(self, count: int) -> list[Observation]:
        return list(self._buffer[-count:])

    def get_buffer_size(self) -> int:
        return len(self._buffer)

    async def collect_once(self) -> list[Observation]:
        observations: list[Observation] = []
        agents = await self._adapter.list_agents()
        for agent in agents:
            state = await self._adapter.get_state(agent)
            if state:
                observations.append(Observation(
                    agent_id=agent,
                    type=ObservationType.STATE,
                    data={
                        "state": state.state.value,
                        "current_task": state.current_task,
                        "task_progress": state.task_progress,
                        "pending_messages": state.pending_messages,
                    },
                ))
                self._push_observation(observations[-1])
            entropy = await self._adapter.get_entropy(agent)
            if entropy:
                observations.append(Observation(
                    agent_id=agent,
                    type=ObservationType.ENTROPY,
                    data={"value": entropy.value, "level": entropy.level},
                ))
                self._push_observation(observations[-1])
        if self._anomaly_detected and observations:
            obs = Observation(
                agent_id=None,
                type=ObservationType.ANOMALY,
                data={"message": "anomaly detected"},
            )
            observations.append(obs)
            self._push_observation(obs)
        if not self._anomaly_detected:
            self._consecutive_clean += 1
        self._anomaly_detected = False
        return observations

    def _push_observation(self, obs: Observation) -> None:
        self._buffer.append(obs)
        if len(self._buffer) > self._buffer_size:
            self._buffer.pop(0)
        for cb in self._callbacks:
            try:
                cb(obs)
            except Exception:
                pass

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self.collect_once()
            await asyncio.sleep(self._current_interval)

    def stop(self) -> None:
        self._running = False
