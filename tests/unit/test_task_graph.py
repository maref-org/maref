from __future__ import annotations

import json

from maref.orchestration.task_graph import TaskGraph, TaskNode, TaskStatus


class TestTaskGraph:
    def test_empty_graph(self):
        g = TaskGraph()
        assert g.node_count == 0
        assert g.node_ids == []
        assert g.has_cycle() is False
        assert g.topological_order() == []

    def test_add_single_node(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="Task A"))
        assert g.node_count == 1
        assert g.node_ids == ["a"]

    def test_topological_order_simple(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A", depends_on=[]))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.add_node(TaskNode(task_id="c", description="C", depends_on=["b"]))
        order = g.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_topological_order_multiple_roots(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B"))
        order = g.topological_order()
        assert set(order) == {"a", "b"}

    def test_detect_cycles(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A", depends_on=["b"]))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["c"]))
        g.add_node(TaskNode(task_id="c", description="C", depends_on=["a"]))
        assert g.has_cycle() is True
        cycles = g.detect_cycles()
        assert len(cycles) > 0

    def test_detect_cycles_returns_path(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A", depends_on=["b"]))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        cycles = g.detect_cycles()
        assert len(cycles) == 1
        assert "a" in cycles[0]
        assert "b" in cycles[0]

    def test_no_cycle_for_dag(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.add_node(TaskNode(task_id="c", description="C", depends_on=["a"]))
        assert g.has_cycle() is False
        assert g.detect_cycles() == []

    def test_topological_order_raises_on_cycle(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A", depends_on=["a"]))
        try:
            g.topological_order()
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_add_edge(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B"))
        g.add_edge("b", "a")
        assert g.get_dependencies("b") == ["a"]
        assert g.get_dependents("a") == ["b"]

    def test_add_edge_missing_node(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        try:
            g.add_edge("a", "nonexistent")
            assert False
        except ValueError:
            pass

    def test_remove_node(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.remove_node("a")
        assert g.node_count == 1
        assert "b" in g.node_ids

    def test_get_node(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        node = g.get_node("a")
        assert node is not None
        assert node.task_id == "a"
        assert g.get_node("nonexistent") is None

    def test_get_dependents(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.add_node(TaskNode(task_id="c", description="C", depends_on=["a"]))
        deps = g.get_dependents("a")
        assert sorted(deps) == ["b", "c"]

    def test_get_ready_nodes(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A", depends_on=[]))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.add_node(TaskNode(task_id="c", description="C", depends_on=["a"]))
        assert g.get_ready_nodes() == ["a"]
        g.set_node_status("a", TaskStatus.COMPLETED)
        assert sorted(g.get_ready_nodes()) == ["b", "c"]

    def test_get_ready_nodes_blocked_by_failed_dep(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        g.set_node_status("a", TaskStatus.FAILED)
        assert g.get_ready_nodes() == []

    def test_set_node_status(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.set_node_status("a", TaskStatus.RUNNING)
        assert g.get_node("a").status == TaskStatus.RUNNING

    def test_to_dict(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        data = g.to_dict()
        assert len(data["nodes"]) == 2
        assert "a" in data["edges"]

    def test_from_dict(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="A"))
        g.add_node(TaskNode(task_id="b", description="B", depends_on=["a"]))
        data = g.to_dict()
        g2 = TaskGraph.from_dict(data)
        assert g2.node_count == 2
        assert g2.get_node("a") is not None
        assert g2.topological_order() == g.topological_order()

    def test_to_json(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description='Test "A"'))
        raw = g.to_json()
        data = json.loads(raw)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["task_id"] == "a"

    def test_to_mermaid(self):
        g = TaskGraph()
        g.add_node(TaskNode(task_id="a", description="Task A"))
        g.add_node(TaskNode(task_id="b", description="Task B", depends_on=["a"]))
        mermaid = g.to_mermaid()
        assert "graph TD;" in mermaid
        assert "a --> b" in mermaid or 'a["Task A"]' in mermaid
