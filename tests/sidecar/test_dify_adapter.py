from __future__ import annotations

import pytest

from sidecar.adapters.dify import CozeAdapter, DifyAdapter
from sidecar.collector import ObservationCollector
from sidecar.protocol import AgentState, EntropyReading


class TestDifyAdapter:
    @pytest.fixture
    def adapter(self) -> DifyAdapter:
        return DifyAdapter()

    async def test_list_agents_empty_initially(self, adapter: DifyAdapter) -> None:
        agents = await adapter.list_agents()
        assert agents == []

    async def test_register_agent_returns_agent_id(self, adapter: DifyAdapter) -> None:
        agent_id = adapter.register_agent("test-agent")
        assert agent_id.name == "test-agent"
        assert agent_id.namespace == "dify"

    async def test_list_agents_after_register(self, adapter: DifyAdapter) -> None:
        agent_id = adapter.register_agent("dify-bot")
        agents = await adapter.list_agents()
        assert len(agents) == 1
        assert agents[0].name == agent_id.name

    async def test_get_state_registered_agent(self, adapter: DifyAdapter) -> None:
        agent_id = adapter.register_agent("dify-bot")
        state = await adapter.get_state(agent_id)
        assert state is not None
        assert state.state == AgentState.IDLE
        assert state.metadata["source"] == "dify"
        assert state.metadata["name"] == "dify-bot"

    async def test_get_state_unregistered_agent(self, adapter: DifyAdapter) -> None:
        from sidecar.protocol import AgentId
        state = await adapter.get_state(AgentId(name="unknown"))
        assert state is None

    async def test_get_entropy_registered_agent(self, adapter: DifyAdapter) -> None:
        agent_id = adapter.register_agent("dify-bot")
        entropy = await adapter.get_entropy(agent_id)
        assert entropy is not None
        assert entropy.value == 0.0
        assert entropy.source == "dify"
        assert entropy.threshold == 5.0

    async def test_get_entropy_unregistered_agent(self, adapter: DifyAdapter) -> None:
        from sidecar.protocol import AgentId
        entropy = await adapter.get_entropy(AgentId(name="unknown"))
        assert entropy is None

    async def test_observe_stream_yields_snapshots(self, adapter: DifyAdapter) -> None:
        adapter.register_agent("dify-bot")
        snapshots = []
        async for snapshot in adapter.observe_stream("analyze data"):
            snapshots.append(snapshot)
        assert len(snapshots) == 1
        assert snapshots[0].current_task == "analyze data"
        assert snapshots[0].state == AgentState.IDLE

    async def test_multiple_agents_registration(self, adapter: DifyAdapter) -> None:
        a1 = adapter.register_agent("bot-1")
        a2 = adapter.register_agent("bot-2")
        a3 = adapter.register_agent("bot-3")
        agents = await adapter.list_agents()
        assert len(agents) == 3
        names = {a.name for a in agents}
        assert a1.name in names
        assert a2.name in names
        assert a3.name in names


class TestCozeAdapter:
    @pytest.fixture
    def adapter(self) -> CozeAdapter:
        return CozeAdapter()

    async def test_list_agents_empty_initially(self, adapter: CozeAdapter) -> None:
        agents = await adapter.list_agents()
        assert agents == []

    async def test_register_agent_returns_agent_id(self, adapter: CozeAdapter) -> None:
        agent_id = adapter.register_agent("test-bot")
        assert agent_id.name == "test-bot"
        assert agent_id.namespace == "coze"

    async def test_get_state_source_is_coze(self, adapter: CozeAdapter) -> None:
        agent_id = adapter.register_agent("coze-bot")
        state = await adapter.get_state(agent_id)
        assert state is not None
        assert state.metadata["source"] == "coze"

    async def test_get_state_unregistered_agent(self, adapter: CozeAdapter) -> None:
        from sidecar.protocol import AgentId
        state = await adapter.get_state(AgentId(name="unknown"))
        assert state is None

    async def test_observe_stream_yields_snapshots(self, adapter: CozeAdapter) -> None:
        adapter.register_agent("coze-bot")
        snapshots = []
        async for snapshot in adapter.observe_stream("process task"):
            snapshots.append(snapshot)
        assert len(snapshots) == 1
        assert snapshots[0].current_task == "process task"

    async def test_coze_independent_from_dify(self) -> None:
        dify = DifyAdapter()
        coze = CozeAdapter()
        dify.register_agent("dify-agent")
        coze.register_agent("coze-agent")
        dify_agents = await dify.list_agents()
        coze_agents = await coze.list_agents()
        assert len(dify_agents) == 1
        assert len(coze_agents) == 1
        assert dify_agents[0].name != coze_agents[0].name


class TestAdapterIntegration:
    async def test_dify_and_coze_no_conflict(self) -> None:
        dify = DifyAdapter()
        coze = CozeAdapter()
        d_id = dify.register_agent("dify-agent")
        c_id = coze.register_agent("coze-agent")
        d_state = await dify.get_state(d_id)
        c_state = await coze.get_state(c_id)
        assert d_state is not None
        assert c_state is not None
        assert d_state.metadata["source"] == "dify"
        assert c_state.metadata["source"] == "coze"

    async def test_collector_with_dify_adapter(self) -> None:
        dify = DifyAdapter()
        dify.register_agent("collector-test")
        collector = ObservationCollector(dify)
        observations = await collector.collect_once()
        assert len(observations) >= 1

    async def test_collector_with_coze_adapter(self) -> None:
        coze = CozeAdapter()
        coze.register_agent("collector-test")
        collector = ObservationCollector(coze)
        observations = await collector.collect_once()
        assert len(observations) >= 1

    async def test_full_pipeline_register_collect_state_entropy(self) -> None:
        adapter = DifyAdapter()
        agent_id = adapter.register_agent("pipeline-agent")
        collector = ObservationCollector(adapter)
        observations = await collector.collect_once()
        assert len(observations) >= 2
        state_snapshot = await adapter.get_state(agent_id)
        assert state_snapshot is not None
        assert state_snapshot.state == AgentState.IDLE
        entropy = await adapter.get_entropy(agent_id)
        assert entropy is not None
        assert isinstance(entropy, EntropyReading)
