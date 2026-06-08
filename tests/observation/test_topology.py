"""Tests for TopologyTracker."""

from maref.observation.topology import TopologyTracker


class TestTopologyTracker:
    def test_record_call_creates_edge(self):
        tracker = TopologyTracker()
        tracker.record_call("agent-a", "agent-b", latency_ms=100)
        graph = tracker.get_graph()
        assert graph["edge_count"] == 1
        assert graph["node_count"] == 2

    def test_record_call_accumulates(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b", latency_ms=100)
        tracker.record_call("a", "b", latency_ms=200, error=True)
        edges = tracker.get_edge_summary()
        assert len(edges) == 1
        assert edges[0]["call_count"] == 2
        assert edges[0]["avg_latency_ms"] == 150.0
        assert edges[0]["error_rate"] == 0.5

    def test_set_node_status(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b")
        tracker.set_node_status("a", "degraded")
        graph = tracker.get_graph()
        node_a = next(n for n in graph["nodes"] if n["agent_id"] == "a")
        assert node_a["status"] == "degraded"

    def test_multiple_edges(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b")
        tracker.record_call("b", "c")
        tracker.record_call("a", "c")
        graph = tracker.get_graph()
        assert graph["edge_count"] == 3
        assert graph["node_count"] == 3

    def test_data_types_tracked(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b", data_type="query")
        tracker.record_call("a", "b", data_type="command")
        edges = tracker.get_edge_summary()
        assert "query" in edges[0]["data_types"]
        assert "command" in edges[0]["data_types"]

    def test_clear_stale(self):
        tracker = TopologyTracker(window_seconds=0.001)
        tracker.record_call("a", "b")
        import time
        time.sleep(0.01)
        cleared = tracker.clear_stale()
        assert cleared >= 1
