from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.protocol import AgentId, AgentState


class TestMockAgentAdapterEdgeCases:
    @pytest.mark.asyncio
    async def test_set_task(self) -> None:
        adapter = MockAgentAdapter()
        agent = AgentId(name="a0")
        adapter.set_task(agent, AgentState.RUNNING, pending_messages=["m1"])
        state = await adapter.get_state(agent)
        assert state.state == AgentState.RUNNING
        assert state.pending_messages == 1

    @pytest.mark.asyncio
    async def test_set_pending(self) -> None:
        adapter = MockAgentAdapter()
        agent = AgentId(name="a0")
        adapter.set_pending(agent, AgentState.WAITING, current_task="t1", task_progress=0.5)
        state = await adapter.get_state(agent)
        assert state.task_progress == 0.5

    @pytest.mark.asyncio
    async def test_set_entropy_warning_level(self) -> None:
        adapter = MockAgentAdapter()
        agent = AgentId(name="a0")
        adapter.set_entropy(agent, 2.0)
        reading = await adapter.get_entropy(agent)
        assert reading.level == "warning"

    @pytest.mark.asyncio
    async def test_set_entropy_normal_level(self) -> None:
        adapter = MockAgentAdapter()
        agent = AgentId(name="a0")
        adapter.set_entropy(agent, 0.5)
        reading = await adapter.get_entropy(agent)
        assert reading.level == "normal"

    @pytest.mark.asyncio
    async def test_set_entropy_critical_level(self) -> None:
        adapter = MockAgentAdapter()
        agent = AgentId(name="a0")
        adapter.set_entropy(agent, 3.5)
        reading = await adapter.get_entropy(agent)
        assert reading.level == "critical"


class TestObservationCollectorEdgeCases:
    def test_remove_callback(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        cb = lambda o: None
        collector.add_callback(cb)
        collector.remove_callback(cb)
        assert len(collector._callbacks) == 0

    @pytest.mark.asyncio
    async def test_collect_once_anomaly(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        collector.notify_anomaly()
        obs = await collector.collect_once()
        anomaly_obs = [o for o in obs if o.source == "collector"]
        assert len(anomaly_obs) == 1
        assert anomaly_obs[0].payload["anomaly_detected"] is True
        assert not collector._anomaly_detected

    @pytest.mark.asyncio
    async def test_collect_once_no_anomaly(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        obs = await collector.collect_once()
        anomaly_obs = [o for o in obs if o.source == "collector"]
        assert len(anomaly_obs) == 0

    @pytest.mark.asyncio
    async def test_push_observation_invokes_callback(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        received: list = []
        collector.add_callback(lambda o: received.append(o))
        await collector.collect_once()
        assert len(received) > 0

    @pytest.mark.asyncio
    async def test_run_stop(self) -> None:
        import asyncio
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter, poll_interval=0.01)
        task = asyncio.create_task(collector.run())
        await asyncio.sleep(0.05)
        collector.stop()
        await task
        assert collector.get_buffer_size() > 0

    @pytest.mark.asyncio
    async def test_collect_once_adapter_exception(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        adapter.list_agents = MagicMock(side_effect=Exception("adapter failure"))
        obs = await collector.collect_once()
        assert obs == []

    def test_notify_anomaly_marks_flag(self) -> None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        assert not collector._anomaly_detected
        collector.notify_anomaly()
        assert collector._anomaly_detected
