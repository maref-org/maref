import asyncio
import pytest
from sidecar.collector import AgentAdapter, MockAgentAdapter, ObservationCollector
from sidecar.protocol import AgentId, AgentState, EntropyReading, ObservationType


class FailingAdapter(AgentAdapter):
    async def list_agents(self):
        raise RuntimeError("fail")

    async def get_state(self, agent_id):
        raise RuntimeError("fail")

    async def get_entropy(self, agent_id):
        raise RuntimeError("fail")


@pytest.fixture
def mock_adapter():
    return MockAgentAdapter(num_agents=2)


@pytest.fixture
def collector(mock_adapter):
    return ObservationCollector(mock_adapter, buffer_size=10, poll_interval=0.1)


class TestMockAgentAdapter:
    @pytest.mark.asyncio
    async def test_list_agents(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        assert len(agents) == 2
        assert agents[0].name == "agent-0"

    @pytest.mark.asyncio
    async def test_get_state(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        state = await mock_adapter.get_state(agents[0])
        assert state is not None
        assert state.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_get_state_unknown(self, mock_adapter):
        unknown = AgentId(name="x", namespace="y")
        assert await mock_adapter.get_state(unknown) is None

    @pytest.mark.asyncio
    async def test_get_entropy(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        ent = await mock_adapter.get_entropy(agents[0])
        assert ent is not None
        assert ent.level == "normal"

    @pytest.mark.asyncio
    async def test_get_entropy_critical(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        mock_adapter.set_entropy(agents[0], 4.0)
        ent = await mock_adapter.get_entropy(agents[0])
        assert ent.level == "critical"

    @pytest.mark.asyncio
    async def test_get_entropy_warning(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        mock_adapter.set_entropy(agents[0], 2.0)
        ent = await mock_adapter.get_entropy(agents[0])
        assert ent.level == "warning"

    @pytest.mark.asyncio
    async def test_set_state_and_task(self, mock_adapter):
        agents = await mock_adapter.list_agents()
        mock_adapter.set_state(agents[0], AgentState.RUNNING)
        mock_adapter.set_task(agents[0], "task1", 0.5)
        mock_adapter.set_pending(agents[0], 3)
        state = await mock_adapter.get_state(agents[0])
        assert state.state == AgentState.RUNNING
        assert state.current_task == "task1"
        assert state.task_progress == 0.5
        assert state.pending_messages == 3


class TestObservationCollector:
    @pytest.mark.asyncio
    async def test_collect_once(self, collector):
        obs = await collector.collect_once()
        assert len(obs) == 4  # 2 agents * 2 obs types

    @pytest.mark.asyncio
    async def test_callbacks(self, collector):
        called = []
        collector.add_callback(lambda o: called.append(o))
        await collector.collect_once()
        assert len(called) == 4

    def test_remove_callback(self, collector):
        def cb(o):
            pass
        collector.add_callback(cb)
        collector.remove_callback(cb)
        assert cb not in collector._callbacks

    @pytest.mark.asyncio
    async def test_notify_anomaly(self, collector):
        collector.notify_anomaly()
        assert collector._anomaly_detected is True

    @pytest.mark.asyncio
    async def test_run_and_stop(self, collector):
        task = asyncio.create_task(collector.run())
        await asyncio.sleep(0.15)
        collector.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert collector._running is False

    @pytest.mark.asyncio
    async def test_backoff(self, collector):
        await collector.collect_once()
        assert collector._consecutive_clean == 0

    @pytest.mark.asyncio
    async def test_anomaly_resets_backoff(self, collector):
        await collector.collect_once()
        collector.notify_anomaly()
        await collector.collect_once()
        assert collector._current_interval == collector._base_interval

    def test_get_recent(self, collector):
        assert collector.get_recent(10) == []

    def test_get_buffer_size(self, collector):
        assert collector.get_buffer_size() == 0

    @pytest.mark.asyncio
    async def test_failing_adapter(self):
        c = ObservationCollector(FailingAdapter(), buffer_size=10)
        with pytest.raises(RuntimeError):
            await c.collect_once()
