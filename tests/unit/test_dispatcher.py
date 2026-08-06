from __future__ import annotations

import pytest

from maref.identity.did_registry import AgentDID
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import AgentDispatcher


class TestAgentDispatcher:
    @pytest.fixture
    def dispatcher(self) -> AgentDispatcher:
        d = AgentDispatcher()
        d.register_agent(AgentDID.generate(), ["general", "analysis", "writing"])
        d.register_agent(AgentDID.generate(), ["general", "research"])
        d.register_agent(AgentDID.generate(), ["math", "coding"])
        return d

    def test_dispatch_returns_result(self, dispatcher: AgentDispatcher) -> None:
        task = SubTask("t0", "Test", 0.5, ["general"], [])
        result = dispatcher.dispatch(task)
        assert result is not None
        assert result.task_id == "t0"
        assert 0.0 <= result.confidence <= 1.0

    def test_dispatch_prefers_matching_capabilities(self, dispatcher: AgentDispatcher) -> None:
        task = SubTask("t0", "Test", 0.5, ["analysis"], [])
        result = dispatcher.dispatch(task)
        assert result is not None
        best_caps = dispatcher._agent_capabilities[result.agent_did]
        assert "analysis" in best_caps

    def test_dispatch_all_dimensions_nonzero(self, dispatcher: AgentDispatcher) -> None:
        task = SubTask("t0", "Test", 0.5, ["general"], [])
        result = dispatcher.dispatch(task)
        assert result is not None
        for dim_name in dispatcher._dimension_weights:
            assert dim_name in result.match_dimensions
            assert result.match_dimensions[dim_name] >= 0.0

    def test_dispatch_performance_updates(self, dispatcher: AgentDispatcher) -> None:
        task = SubTask("t0", "Test", 0.5, ["general"], [])
        result1 = dispatcher.dispatch(task)
        assert result1 is not None
        dispatcher.update_performance(result1.agent_did, 0.95)
        result2 = dispatcher.dispatch(task)
        assert result2 is not None
        assert result2.confidence > result1.confidence

    def test_register_and_dispatch_specialized(self, dispatcher: AgentDispatcher) -> None:
        coding_did = AgentDID.generate()
        dispatcher.register_agent(coding_did, ["coding", "debugging"])
        task = SubTask("t0", "Test", 0.5, ["coding", "debugging"], [])
        result = dispatcher.dispatch(task)
        assert result is not None
        assert result.agent_did == coding_did

    def test_multiple_tasks_different_dispatches(self, dispatcher: AgentDispatcher) -> None:
        task_a = SubTask("a", "Analysis", 0.5, ["analysis"], [])
        task_b = SubTask("b", "Coding", 0.5, ["coding"], [])
        result_a = dispatcher.dispatch(task_a)
        result_b = dispatcher.dispatch(task_b)
        assert result_a is not None and result_b is not None
