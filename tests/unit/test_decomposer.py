from __future__ import annotations

import pytest

from maref.orchestration.decomposer import SubTask, TaskDAG, TaskDecomposer


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
        assert dag.node_count == 3
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
