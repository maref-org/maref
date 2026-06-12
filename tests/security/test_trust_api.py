"""Tests for TrustAPI — trust management interface."""

from unittest.mock import MagicMock

from maref.security.trust_api import TrustAPI


class TestTrustAPI:
    def _make_api(self):
        graph = MagicMock()
        graph.agents = {"agent-1": MagicMock(), "agent-2": MagicMock()}
        graph.get_trust.return_value = 75.0
        graph.get_neighbors.return_value = ["agent-2"]
        return TrustAPI(graph)

    def test_trust_score_returns_value(self):
        api = self._make_api()
        score = api.trust_score("agent-1")
        assert score == 75.0

    def test_trust_score_unknown_agent(self):
        api = self._make_api()
        score = api.trust_score("unknown")
        assert score is None

    def test_set_trust_existing_agent(self):
        api = self._make_api()
        api.set_trust("agent-1", 85.0, reason="good behavior")
        api.graph.update_trust.assert_called_with("agent-1", 85.0)
        history = api.get_trust_history("agent-1")
        assert len(history) == 1
        assert history[0]["score"] == 85.0
        assert history[0]["reason"] == "good behavior"

    def test_set_trust_new_agent(self):
        graph = MagicMock()
        graph.agents = {}
        api = TrustAPI(graph)
        api.set_trust("new-agent", 60.0)
        graph.add_agent.assert_called_with("new-agent", initial_trust=60.0)

    def test_update_trust(self):
        api = self._make_api()
        api.update_trust("agent-1", 90.0, reason="updated")
        api.graph.update_trust.assert_called_with("agent-1", 90.0)

    def test_get_trust_history_empty(self):
        api = self._make_api()
        history = api.get_trust_history("unknown")
        assert history == []

    def test_list_agents(self):
        api = self._make_api()
        agents = api.list_agents()
        assert "agent-1" in agents
        assert "agent-2" in agents

    def test_get_trust_report(self):
        api = self._make_api()
        report = api.get_trust_report("agent-1")
        assert report["agent_id"] == "agent-1"
        assert report["trust_score"] == 75.0
        assert report["trust_tier"] == "MEDIUM"
        assert report["neighbor_count"] == 1
        assert report["history_count"] == 0

    def test_get_trust_report_unknown_agent(self):
        api = self._make_api()
        report = api.get_trust_report("unknown")
        assert "error" in report

    def test_calculate_tier(self):
        assert TrustAPI._calculate_tier(95) == "HIGH"
        assert TrustAPI._calculate_tier(80) == "MEDIUM"
        assert TrustAPI._calculate_tier(90) == "HIGH"
        assert TrustAPI._calculate_tier(70) == "MEDIUM"
        assert TrustAPI._calculate_tier(75) == "MEDIUM"
        assert TrustAPI._calculate_tier(60) == "LOW"
        assert TrustAPI._calculate_tier(50) == "LOW"
        assert TrustAPI._calculate_tier(49) == "UNTRUSTED"
        assert TrustAPI._calculate_tier(0) == "UNTRUSTED"

    def test_get_trust_report_with_history(self):
        api = self._make_api()
        api.set_trust("agent-1", 80.0, reason="test")
        report = api.get_trust_report("agent-1")
        assert report["history_count"] == 1
        assert report["last_updated"] is not None
