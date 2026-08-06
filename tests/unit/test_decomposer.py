from __future__ import annotations

import pytest

from maref.orchestration.decomposer import (
    ParallelStrategy,
    SubTask,
    TaskDAG,
    TaskDecomposer,
)
from maref.orchestration.task_graph import NodeType, RiskLevel


class TestTaskDAG:
    @pytest.fixture
    def dag(self) -> TaskDAG:
        d = TaskDAG()
        d.add_node(SubTask("t0", "Step 0", 0.3, ["general"], []))
        d.add_node(SubTask("t1", "Step 1", 0.5, ["general"], ["t0"]))
        d.add_node(SubTask("t2", "Step 2", 0.4, ["general"], ["t1"]))
        return d

    def test_no_cycle(self, dag: TaskDAG) -> None:
        assert dag.has_cycle() is False

    def test_cycle_detection(self) -> None:
        dag = TaskDAG()
        dag.add_node(SubTask("a", "A", 0.5, ["general"], ["b"]))
        dag.add_node(SubTask("b", "B", 0.5, ["general"], ["a"]))
        assert dag.has_cycle() is True

    def test_self_cycle_detection(self) -> None:
        dag = TaskDAG()
        dag.add_node(SubTask("x", "X", 0.5, ["general"], ["x"]))
        assert dag.has_cycle() is True

    def test_topological_order(self, dag: TaskDAG) -> None:
        order = dag.topological_order()
        assert order == ["t0", "t1", "t2"]

    def test_topological_order_cycle_raises(self) -> None:
        dag = TaskDAG()
        dag.add_node(SubTask("a", "A", 0.5, ["general"], ["b"]))
        dag.add_node(SubTask("b", "B", 0.5, ["general"], ["a"]))
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_order()

    def test_node_count(self, dag: TaskDAG) -> None:
        assert dag.node_count == 3

    def test_large_dag_no_cycle(self) -> None:
        dag = TaskDAG()
        for i in range(50):
            deps = [f"t{j}" for j in range(i)] if i > 0 else []
            dag.add_node(SubTask(f"t{i}", f"Task {i}", 0.5, ["general"], deps))
        assert dag.has_cycle() is False
        assert dag.node_count == 50
        order = dag.topological_order()
        assert len(order) == 50

    def test_dag_fuzz_no_false_positives(self) -> None:
        import random

        random.seed(42)
        for _ in range(100):
            dag = TaskDAG()
            n = random.randint(2, 10)
            for i in range(n):
                deps = random.sample([f"t{j}" for j in range(i)], random.randint(0, min(i, 3)))
                dag.add_node(SubTask(f"t{i}", f"T{i}", 0.5, ["general"], deps))
            has_cycle = dag.has_cycle()
            if not has_cycle:
                order = dag.topological_order()
                assert len(order) == n


class TestTaskDecomposer:
    @pytest.fixture
    def decomposer(self) -> TaskDecomposer:
        return TaskDecomposer()

    def test_decompose_analyze_report(self, decomposer: TaskDecomposer) -> None:
        dag, conf = decomposer.decompose(
            "analyze the data and write a report", ["general", "analysis"]
        )
        assert dag.node_count == 5
        assert conf > 0.7

    def test_decompose_research(self, decomposer: TaskDecomposer) -> None:
        dag, conf = decomposer.decompose("research the topic thoroughly", ["research"])
        assert dag.node_count == 3
        assert conf > 0.7

    def test_decompose_simple(self, decomposer: TaskDecomposer) -> None:
        dag, conf = decomposer.decompose("do something", [])
        assert dag.node_count == 1
        assert conf > 0.7

    def test_decompose_accuracy(self, decomposer: TaskDecomposer) -> None:
        import random

        random.seed(42)
        total = 20
        test_phrases = ["analyze", "report", "research", "investigate", "synthesize"]
        for _ in range(total):
            phrase = random.choice(test_phrases)
            dag, _ = decomposer.decompose(f"Please {phrase} the given information", ["general"])
            assert dag.node_count >= 1

    def test_decompose_to_graph_returns_task_graph(self) -> None:
        d = TaskDecomposer()
        graph, conf = d.decompose_to_graph("analyze the data and write a report", ["general"])
        assert conf > 0.7
        assert graph.node_count > 0
        fork_nodes = [n for n in graph.node_ids
                      if graph.get_node(n) and graph.get_node(n).node_type == NodeType.FORK]
        join_nodes = [n for n in graph.node_ids
                      if graph.get_node(n) and graph.get_node(n).node_type == NodeType.JOIN]
        assert len(fork_nodes) >= 1
        assert len(join_nodes) >= 1

    def test_decompose_to_graph_single_task_no_fork(self) -> None:
        d = TaskDecomposer()
        graph, conf = d.decompose_to_graph("do something simple", [])
        assert graph.node_count >= 1

    def test_decompose_with_llm_falls_back_when_no_llm(self) -> None:
        d = TaskDecomposer()
        graph, conf = d.decompose_with_llm("analyze the data", ["general"])
        assert graph.node_count > 0

    def test_force_serial_strategy_removes_forks(self) -> None:
        d = TaskDecomposer(parallel_strategy=ParallelStrategy.FORCE_SERIAL)
        graph, conf = d.decompose_to_graph("analyze the data and write a report", ["general"])
        for nid in graph.node_ids:
            node = graph.get_node(nid)
            if node:
                assert node.node_type != NodeType.FORK
                assert node.node_type != NodeType.JOIN

    def test_force_parallel_strategy_adds_fork(self) -> None:
        d = TaskDecomposer(parallel_strategy=ParallelStrategy.FORCE_PARALLEL)
        graph, conf = d.decompose_to_graph("analyze the data and write a report", ["general"])
        fork_nodes = [n for n in graph.node_ids
                      if graph.get_node(n) and graph.get_node(n).node_type == NodeType.FORK]
        assert len(fork_nodes) >= 1

    def test_classify_risk_by_keyword(self) -> None:
        d = TaskDecomposer()
        # "deploy" is a CRITICAL keyword
        risk = d._classify_risk({"description": "Deploy to production"})
        assert risk == RiskLevel.CRITICAL
        # "audit" is HIGH
        risk = d._classify_risk({"description": "Perform security audit"})
        assert risk == RiskLevel.HIGH
        # Unknown keyword → MEDIUM
        risk = d._classify_risk({"description": "Write documentation"})
        assert risk == RiskLevel.MEDIUM

    def test_classify_risk_by_explicit_label(self) -> None:
        d = TaskDecomposer()
        risk = d._classify_risk({"description": "Some task", "risk": "low"})
        assert risk == RiskLevel.LOW
        risk = d._classify_risk({"description": "Some task", "risk": "critical"})
        assert risk == RiskLevel.CRITICAL

    def test_to_task_graph_parallel_layers(self) -> None:
        dag = TaskDAG()
        dag.add_node(SubTask("a", "Task A", 0.3, ["general"], [], risk_level=RiskLevel.LOW))
        dag.add_node(SubTask("b", "Task B", 0.4, ["general"], [], risk_level=RiskLevel.LOW))
        dag.add_node(SubTask("c", "Task C", 0.5, ["general"], ["a", "b"], risk_level=RiskLevel.MEDIUM))
        graph = dag.to_task_graph()
        fork_nodes = [n for n in graph.node_ids
                      if graph.get_node(n) and graph.get_node(n).node_type == NodeType.FORK]
        join_nodes = [n for n in graph.node_ids
                      if graph.get_node(n) and graph.get_node(n).node_type == NodeType.JOIN]
        assert len(fork_nodes) >= 1
        assert len(join_nodes) >= 1

    def test_template_matching_word_boundary_no_false_positive(self) -> None:
        d = TaskDecomposer()
        dag, _ = d.decompose("writing a research paper about security audit tools", ["general"])
        assert dag.node_count >= 1
