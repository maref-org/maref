"""Tests for TrustGraph and TrustPropagation — trust graph and propagation."""

import pytest

from maref.security.trust_graph import TrustAgent, TrustEdge, TrustGraph, TrustPropagation


class TestTrustEdge:
    def test_default_timestamp(self):
        edge = TrustEdge(source="a", target="b", trust_score=80.0)
        assert edge.timestamp > 0


class TestTrustAgent:
    def test_default_score(self):
        agent = TrustAgent(agent_id="agent-1")
        assert agent.trust_score == 50.0


class TestTrustGraph:
    def test_initial_state(self):
        graph = TrustGraph()
        assert len(graph.agents) == 0

    def test_add_agent(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=80.0)
        assert "agent-1" in graph.agents
        assert graph.agents["agent-1"].trust_score == 80.0

    def test_add_agent_default_score(self):
        graph = TrustGraph()
        graph.add_agent("agent-1")
        assert graph.agents["agent-1"].trust_score == 50.0

    def test_add_agent_clamps_score(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=150.0)
        assert graph.agents["agent-1"].trust_score == 100.0
        graph.add_agent("agent-2", initial_trust=-10.0)
        assert graph.agents["agent-2"].trust_score == 0.0

    def test_add_agent_with_metadata(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", metadata={"role": "worker"})
        assert graph.agents["agent-1"].metadata == {"role": "worker"}

    def test_add_agent_duplicate(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=50.0)
        graph.add_agent("agent-1", initial_trust=80.0)
        assert graph.agents["agent-1"].trust_score == 50.0
        assert len(graph.agents) == 1

    def test_remove_agent(self):
        graph = TrustGraph()
        graph.add_agent("agent-1")
        graph.add_agent("agent-2")
        graph.add_edge("agent-1", "agent-2", 80.0)
        graph.remove_agent("agent-1")
        assert "agent-1" not in graph.agents
        assert graph.get_edge("agent-1", "agent-2") is None

    def test_remove_agent_nonexistent(self):
        graph = TrustGraph()
        graph.remove_agent("unknown")
        assert len(graph.agents) == 0

    def test_add_edge(self):
        graph = TrustGraph()
        graph.add_edge("a", "b", 90.0, weight=0.8)
        edge = graph.get_edge("a", "b")
        assert edge is not None
        assert edge.trust_score == 90.0
        assert edge.weight == 0.8

    def test_add_edge_auto_creates_agents(self):
        graph = TrustGraph()
        graph.add_edge("a", "b", 80.0)
        assert "a" in graph.agents
        assert "b" in graph.agents

    def test_get_edge_nonexistent(self):
        graph = TrustGraph()
        assert graph.get_edge("a", "b") is None

    def test_get_neighbors(self):
        graph = TrustGraph()
        graph.add_edge("a", "b", 80.0)
        graph.add_edge("a", "c", 60.0)
        neighbors = graph.get_neighbors("a")
        assert "b" in neighbors
        assert "c" in neighbors

    def test_get_neighbors_empty(self):
        graph = TrustGraph()
        assert graph.get_neighbors("unknown") == []

    def test_get_trust(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=75.0)
        assert graph.get_trust("agent-1") == 75.0

    def test_get_trust_unknown_agent(self):
        graph = TrustGraph()
        assert graph.get_trust("unknown") == 0.0

    def test_update_trust(self):
        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=50.0)
        graph.update_trust("agent-1", 85.0)
        assert graph.get_trust("agent-1") == 85.0

    def test_update_trust_clamps(self):
        graph = TrustGraph()
        graph.add_agent("agent-1")
        graph.update_trust("agent-1", 200.0)
        assert graph.get_trust("agent-1") == 100.0

    def test_update_trust_unknown_agent(self):
        graph = TrustGraph()
        graph.update_trust("unknown", 80.0)
        assert graph.get_trust("unknown") == 0.0

    def test_to_dict(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=70.0)
        graph.add_agent("b", initial_trust=80.0)
        graph.add_edge("a", "b", 90.0)
        d = graph.to_dict()
        assert "a" in d["agents"]
        assert "b" in d["agents"]
        assert len(d["edges"]) == 1

    def test_from_dict(self):
        data = {
            "agents": {"a": {"trust_score": 70.0, "metadata": {}}, "b": {"trust_score": 80.0, "metadata": {}}},
            "edges": [{"source": "a", "target": "b", "trust_score": 90.0, "weight": 1.0}],
        }
        graph = TrustGraph.from_dict(data)
        assert graph.get_trust("a") == 70.0
        assert graph.get_trust("b") == 80.0
        assert graph.get_edge("a", "b") is not None

    def test_from_dict_empty(self):
        graph = TrustGraph.from_dict({})
        assert len(graph.agents) == 0


class TestTrustPropagation:
    def test_propagate_basic(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=80.0)
        graph.add_agent("b", initial_trust=50.0)
        graph.add_edge("a", "b", 90.0)

        prop = TrustPropagation(graph, decay_factor=0.5)
        scores = prop.propagate(iterations=1)
        assert scores["a"] == 80.0
        assert scores["b"] > 50.0

    def test_propagate_no_incoming_edges(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=80.0)
        graph.add_agent("b", initial_trust=50.0)

        prop = TrustPropagation(graph)
        scores = prop.propagate()
        assert scores["a"] == 80.0
        assert scores["b"] == 50.0

    def test_calculate_transitive_trust_self(self):
        graph = TrustGraph()
        graph.add_agent("a")
        prop = TrustPropagation(graph)
        assert prop.calculate_transitive_trust("a", "a") == 100.0

    def test_calculate_transitive_trust_direct(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=80.0)
        graph.add_agent("b", initial_trust=50.0)
        graph.add_edge("a", "b", 90.0)

        prop = TrustPropagation(graph, decay_factor=0.5)
        trust = prop.calculate_transitive_trust("a", "b")
        assert trust > 0
        assert trust <= 100.0

    def test_calculate_transitive_trust_no_path(self):
        graph = TrustGraph()
        graph.add_agent("a")
        graph.add_agent("b")

        prop = TrustPropagation(graph)
        trust = prop.calculate_transitive_trust("a", "b")
        assert trust == 0.0

    def test_edge_score_clamping_add_edge(self):
        graph = TrustGraph()
        graph.add_edge("a", "b", 200.0)
        edge = graph.get_edge("a", "b")
        assert edge.trust_score == 100.0

        graph.add_edge("a", "c", -10.0)
        edge = graph.get_edge("a", "c")
        assert edge.trust_score == 0.0
