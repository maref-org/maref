"""Agent topology tracker — visualize agent communication relationships.

Consumes trace/span data to build a real-time directed graph of
agent-to-agent interactions. Each edge records call count, latency,
and error rate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class TopologyEdge:
    source: str
    target: str
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0
    last_seen: float = 0.0
    data_types: set[str] = field(default_factory=set)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.call_count, 1)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(self.call_count, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "call_count": self.call_count,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "error_rate": round(self.error_rate, 3),
            "last_seen": self.last_seen,
            "data_types": list(self.data_types),
        }


@dataclass
class TopologyNode:
    agent_id: str
    status: str = "idle"  # idle | busy | error | degraded
    task_count: int = 0
    last_active: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "task_count": self.task_count,
            "last_active": self.last_active,
        }


class TopologyTracker:
    """Real-time agent interaction topology tracker.

    Usage:
        tracker = TopologyTracker()
        # Record an interaction
        tracker.record_call("agent-a", "agent-b", latency_ms=150, data_type="query")
        # Get topology for visualization
        graph = tracker.get_graph()
    """

    def __init__(self, window_seconds: float = 300.0) -> None:
        self._edges: dict[tuple[str, str], TopologyEdge] = {}
        self._nodes: dict[str, TopologyNode] = {}
        self._lock = Lock()
        self._window = window_seconds

    def record_call(
        self,
        source: str,
        target: str,
        latency_ms: float = 0.0,
        error: bool = False,
        data_type: str = "",
    ) -> None:
        with self._lock:
            now = time.time()
            key = (source, target)
            if key not in self._edges:
                self._edges[key] = TopologyEdge(source=source, target=target)
            edge = self._edges[key]
            edge.call_count += 1
            edge.total_latency_ms += latency_ms
            if error:
                edge.error_count += 1
            edge.last_seen = now
            if data_type:
                edge.data_types.add(data_type)

            # Update nodes
            for agent_id in (source, target):
                if agent_id not in self._nodes:
                    self._nodes[agent_id] = TopologyNode(agent_id=agent_id)
                node = self._nodes[agent_id]
                node.last_active = now
                node.task_count += 1
                if error and agent_id == source:
                    node.status = "error"

    def set_node_status(self, agent_id: str, status: str) -> None:
        with self._lock:
            if agent_id not in self._nodes:
                self._nodes[agent_id] = TopologyNode(agent_id=agent_id)
            self._nodes[agent_id].status = status
            self._nodes[agent_id].last_active = time.time()

    def get_graph(self) -> dict[str, Any]:
        with self._lock:
            cutoff = time.time() - self._window
            edges = [
                e.to_dict()
                for e in self._edges.values()
                if e.last_seen >= cutoff
            ]
            nodes = [
                n.to_dict()
                for n in self._nodes.values()
                if n.last_active >= cutoff
            ]
            return {
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }

    def get_edge_summary(self) -> list[dict[str, Any]]:
        with self._lock:
            cutoff = time.time() - self._window
            return [
                e.to_dict()
                for e in sorted(
                    self._edges.values(),
                    key=lambda x: -x.call_count,
                )
                if e.last_seen >= cutoff
            ]

    def clear_stale(self) -> int:
        with self._lock:
            cutoff = time.time() - self._window * 2
            stale_edges = [k for k, e in self._edges.items() if e.last_seen < cutoff]
            stale_nodes = [k for k, n in self._nodes.items() if n.last_active < cutoff]
            for k in stale_edges:
                del self._edges[k]
            for k in stale_nodes:
                del self._nodes[k]
            return len(stale_edges) + len(stale_nodes)
