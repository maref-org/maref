"""Tests for agent_dispatcher.py — dispatching, matching, edge cases."""
from __future__ import annotations

import pytest

from maref.recursive.agent_dispatcher import AgentDispatcher, DispatchResult
from maref.recursive.capability_contracts import CapabilityContract, CapabilityRegistry
from maref.recursive.internal_agents import InternalAgent, InternalAgentRegistry
from maref.recursive.task_decomposer import SubTask


class TestDispatchResult:
    def test_defaults(self):
        result = DispatchResult(subtask_id="st-1", assigned_agent_id="agent-1")
        assert result.score == 0.0
        assert result.contract_score == 0.0
        assert result.match_details is None


class TestAgentDispatcher:
    def test_dispatch_returns_best_agent(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1", "cap2"], "general")
        registry.register("agent-b", "mod.b", ["cap3"], "general")
        dispatcher = AgentDispatcher(registry)
        agent = dispatcher.dispatch(SubTask("st-1", "task", ["cap1", "cap2"]))
        assert agent is not None
        assert agent.agent_id == "agent-a"

    def test_dispatch_returns_none_when_no_match(self):
        registry = InternalAgentRegistry()
        dispatcher = AgentDispatcher(registry)
        agent = dispatcher.dispatch(SubTask("st-1", "task", ["cap1"]))
        assert agent is None

    def test_dispatch_all(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1"], "general")
        registry.register("agent-b", "mod.b", ["cap2"], "general")
        dispatcher = AgentDispatcher(registry)
        results = dispatcher.dispatch_all([
            SubTask("st-1", "task1", ["cap1"]),
            SubTask("st-2", "task2", ["cap2"]),
        ])
        assert len(results) == 2
        assert results[0].assigned_agent_id == "agent-a"
        assert results[1].assigned_agent_id == "agent-b"

    def test_string_match_score_empty_capabilities(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1"], "general")
        dispatcher = AgentDispatcher(registry)
        agent = InternalAgent("agent-a", "mod.a", ["cap1"])
        score = dispatcher._string_match_score(SubTask("st-1", "task", []), agent)
        assert score == 0.5

    def test_string_match_score_full_match(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1", "cap2"], "general")
        dispatcher = AgentDispatcher(registry)
        agent = InternalAgent("agent-a", "mod.a", ["cap1", "cap2"])
        score = dispatcher._string_match_score(
            SubTask("st-1", "task", ["cap1", "cap2"]), agent
        )
        assert score == 1.0

    def test_contract_match_score_no_registry(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1"], "general")
        dispatcher = AgentDispatcher(registry)
        agent = InternalAgent("agent-a", "mod.a", ["cap1"])
        score, details = dispatcher._contract_match_score(
            SubTask("st-1", "task", ["cap1"]), agent
        )
        assert score == 0.0
        assert details == []

    def test_contract_match_score_with_registry(self):
        registry = InternalAgentRegistry()
        contract_registry = CapabilityRegistry()
        contract_registry.register(CapabilityContract("cap1", "1.0"))
        registry.register("agent-a", "mod.a", [], "general",
                          contracts=[CapabilityContract("cap1", "1.0")])
        dispatcher = AgentDispatcher(registry, contract_registry)
        agent = InternalAgent("agent-a", "mod.a", [],
                              contracts=[CapabilityContract("cap1", "1.0")])
        score, details = dispatcher._contract_match_score(
            SubTask("st-1", "task", ["cap1"]), agent
        )
        assert score == 1.0
        assert "cap1" in details

    def test_capability_match_score(self):
        registry = InternalAgentRegistry()
        registry.register("agent-a", "mod.a", ["cap1"], "general")
        dispatcher = AgentDispatcher(registry)
        agent = InternalAgent("agent-a", "mod.a", ["cap1"])
        score, cscore, details = dispatcher._capability_match_score(
            SubTask("st-1", "task", ["cap1"]), agent
        )
        assert score == 1.0
        assert cscore == 0.0

    def test_dispatch_all_empty(self):
        registry = InternalAgentRegistry()
        dispatcher = AgentDispatcher(registry)
        results = dispatcher.dispatch_all([])
        assert results == []
