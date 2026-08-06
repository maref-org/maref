from __future__ import annotations

from maref.security.trust_api import TrustAPI
from maref.security.trust_graph import TrustGraph, TrustPropagation
from maref.security.trust_visualization import TrustVisualizer
from maref.security.weighted_consensus import ConsensusVote, WeightedConsensusEngine


class TestTrustGraphBasics:
    """T2.1: 跨Agent信任关系图谱测试"""

    def test_add_agent(self):
        graph = TrustGraph()
        graph.add_agent("agent-a", initial_trust=50.0)
        assert "agent-a" in graph.agents
        assert graph.get_trust("agent-a") == 50.0

    def test_add_trust_edge(self):
        graph = TrustGraph()
        graph.add_agent("agent-a")
        graph.add_agent("agent-b")
        graph.add_edge("agent-a", "agent-b", trust_score=80.0, weight=1.0)

        edge = graph.get_edge("agent-a", "agent-b")
        assert edge is not None
        assert edge.trust_score == 80.0
        assert edge.weight == 1.0

    def test_get_neighbors(self):
        graph = TrustGraph()
        graph.add_agent("a")
        graph.add_agent("b")
        graph.add_agent("c")
        graph.add_edge("a", "b", 70.0)
        graph.add_edge("a", "c", 90.0)

        neighbors = graph.get_neighbors("a")
        assert len(neighbors) == 2
        assert "b" in neighbors
        assert "c" in neighbors

    def test_remove_agent_cascades(self):
        graph = TrustGraph()
        graph.add_agent("a")
        graph.add_agent("b")
        graph.add_edge("a", "b", 80.0)

        graph.remove_agent("a")
        assert "a" not in graph.agents
        assert graph.get_edge("a", "b") is None

    def test_update_trust_score(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=50.0)
        graph.update_trust("a", 75.0)
        assert graph.get_trust("a") == 75.0

    def test_trust_score_bounds(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=50.0)
        graph.update_trust("a", 150.0)  # 超出上限
        assert graph.get_trust("a") == 100.0

        graph.update_trust("a", -50.0)  # 超出下限
        assert graph.get_trust("a") == 0.0

    def test_graph_to_dict(self):
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=60.0)
        graph.add_agent("b", initial_trust=70.0)
        graph.add_edge("a", "b", 80.0)

        data = graph.to_dict()
        assert "agents" in data
        assert "edges" in data
        assert len(data["agents"]) == 2
        assert len(data["edges"]) == 1

    def test_graph_from_dict(self):
        data = {
            "agents": {
                "a": {"trust_score": 60.0},
                "b": {"trust_score": 70.0},
            },
            "edges": [
                {"source": "a", "target": "b", "trust_score": 80.0, "weight": 1.0},
            ],
        }
        graph = TrustGraph.from_dict(data)
        assert "a" in graph.agents
        assert "b" in graph.agents
        assert graph.get_edge("a", "b") is not None


class TestTrustPropagation:
    """T2.2: 信任传播算法测试"""

    def test_propagate_direct_trust(self):
        """直接信任传播：a信任b(80)，则b的信任分受a影响"""
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=90.0)
        graph.add_agent("b", initial_trust=50.0)
        graph.add_edge("a", "b", trust_score=80.0, weight=1.0)

        propagator = TrustPropagation(graph, decay_factor=0.5)
        new_scores = propagator.propagate(iterations=1)

        # b 的信任分应被提升（因为 a 高信任且信任 b）
        assert new_scores["b"] > 50.0

    def test_propagate_with_decay(self):
        """信任传播衰减：a->b->c，c 收到的信任应衰减"""
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=100.0)
        graph.add_agent("b", initial_trust=50.0)
        graph.add_agent("c", initial_trust=50.0)
        graph.add_edge("a", "b", 100.0)
        graph.add_edge("b", "c", 100.0)

        propagator = TrustPropagation(graph, decay_factor=0.5)
        scores = propagator.propagate(iterations=2)

        # c 通过 b 间接获得 a 的信任，但有衰减
        # a(100) -> b(提升) -> c(提升，但衰减)
        assert scores["c"] > 50.0
        assert scores["c"] < scores["b"]  # c < b 因为有衰减

    def test_propagate_convergence(self):
        """信任传播应收敛"""
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=100.0)
        graph.add_agent("b", initial_trust=0.0)
        graph.add_edge("a", "b", 100.0)

        propagator = TrustPropagation(graph, decay_factor=0.3)
        scores1 = propagator.propagate(iterations=20)
        scores2 = propagator.propagate(iterations=30)

        # 20次和30次迭代结果应接近（收敛）
        assert abs(scores1["b"] - scores2["b"]) < 1.0

    def test_propagate_no_incoming_edges(self):
        """无入边的 agent 信任分不变"""
        graph = TrustGraph()
        graph.add_agent("a", initial_trust=50.0)
        graph.add_agent("b", initial_trust=60.0)
        # 无 edge

        propagator = TrustPropagation(graph)
        scores = propagator.propagate(iterations=3)

        assert scores["a"] == 50.0
        assert scores["b"] == 60.0

    def test_transitive_trust_calculation(self):
        """传递信任计算：a信任b(80)，b信任c(90)，则a对c的传递信任"""
        graph = TrustGraph()
        graph.add_agent("a")
        graph.add_agent("b")
        graph.add_agent("c")
        graph.add_edge("a", "b", 80.0)
        graph.add_edge("b", "c", 90.0)

        propagator = TrustPropagation(graph, decay_factor=0.8)
        transitive = propagator.calculate_transitive_trust("a", "c")

        # 传递信任 = 80 * 0.8 * 90 / 100 = 57.6
        assert transitive > 0
        assert transitive <= 80.0  # 不能超过直接信任


class TestWeightedConsensusEngine:
    """T3.1: 加权共识引擎测试"""

    def test_weighted_consensus_formula(self):
        """验证公式 W_agent = 1/|N_i| * Σ T_ij"""
        engine = WeightedConsensusEngine()

        # agent-1 的邻居对它的信任：a(80), b(60)
        # W_1 = (80 + 60) / 2 = 70.0
        neighbors_trust = {"agent-a": 80.0, "agent-b": 60.0}
        weight = engine.calculate_weight(neighbors_trust)
        assert weight == 70.0

    def test_consensus_with_weights(self):
        """高权重 agent 对共识结果影响更大"""
        engine = WeightedConsensusEngine()

        votes = [
            ConsensusVote(agent_id="high-trust", value="option-a", weight=90.0),
            ConsensusVote(agent_id="low-trust", value="option-b", weight=30.0),
            ConsensusVote(agent_id="mid-trust", value="option-a", weight=60.0),
        ]

        result = engine.decide(votes)
        # option-a: 90 + 60 = 150, option-b: 30
        assert result == "option-a"

    def test_consensus_tie_breaking(self):
        """平票时应有确定性结果"""
        engine = WeightedConsensusEngine()

        votes = [
            ConsensusVote(agent_id="a", value="option-a", weight=50.0),
            ConsensusVote(agent_id="b", value="option-b", weight=50.0),
        ]

        result = engine.decide(votes)
        # 平票时，按 agent_id 字典序选择
        assert result in ("option-a", "option-b")

    def test_empty_votes(self):
        """空投票应返回 None"""
        engine = WeightedConsensusEngine()
        result = engine.decide([])
        assert result is None

    def test_dynamic_weight_update(self):
        """T3.2: 动态权重更新"""
        engine = WeightedConsensusEngine()

        # 初始权重
        initial_weight = engine.calculate_weight({"a": 80.0, "b": 60.0})
        assert initial_weight == 70.0

        # 更新信任值
        updated_weight = engine.calculate_weight({"a": 90.0, "b": 70.0})
        assert updated_weight == 80.0
        assert updated_weight > initial_weight

    def test_weighted_consensus_with_penalty(self):
        """拜占庭 agent 应被降低权重"""
        engine = WeightedConsensusEngine()

        votes = [
            ConsensusVote(agent_id="normal-1", value="correct", weight=80.0),
            ConsensusVote(agent_id="normal-2", value="correct", weight=70.0),
            ConsensusVote(agent_id="byzantine", value="wrong", weight=50.0),
        ]

        # 标记 byzantine agent
        engine.penalize_agent("byzantine", penalty=0.5)

        result = engine.decide(votes)
        # correct: 80 + 70 = 150, wrong: 50 * 0.5 = 25
        assert result == "correct"


class TestTrustAPI:
    """T4: 信任API测试"""

    def setup_api(self):
        from maref.security.trust_graph import TrustGraph

        graph = TrustGraph()
        graph.add_agent("agent-1", initial_trust=75.0)
        graph.add_agent("agent-2", initial_trust=60.0)
        graph.add_edge("agent-1", "agent-2", 80.0)
        return TrustAPI(graph)

    def test_trust_score(self):
        api = self.setup_api()
        score = api.trust_score("agent-1")
        assert score == 75.0

    def test_trust_score_unknown_agent(self):
        api = self.setup_api()
        score = api.trust_score("unknown")
        assert score is None

    def test_get_trust_history(self):
        api = self.setup_api()
        # 记录几次更新
        api.update_trust("agent-1", 80.0, reason="good_behavior")
        api.update_trust("agent-1", 85.0, reason="completed_task")

        history = api.get_trust_history("agent-1")
        assert len(history) >= 2
        assert history[-1]["score"] == 85.0
        assert history[-1]["reason"] == "completed_task"

    def test_get_trust_history_empty(self):
        api = self.setup_api()
        history = api.get_trust_history("agent-2")
        # agent-2 无历史记录
        assert len(history) == 0

    def test_set_trust(self):
        api = self.setup_api()
        api.set_trust("agent-1", 90.0, reason="manual_override")

        assert api.trust_score("agent-1") == 90.0
        history = api.get_trust_history("agent-1")
        assert history[-1]["score"] == 90.0
        assert history[-1]["reason"] == "manual_override"

    def test_set_trust_bounds(self):
        api = self.setup_api()
        api.set_trust("agent-1", 150.0)
        assert api.trust_score("agent-1") == 100.0

        api.set_trust("agent-1", -20.0)
        assert api.trust_score("agent-1") == 0.0

    def test_api_list_agents(self):
        api = self.setup_api()
        agents = api.list_agents()
        assert "agent-1" in agents
        assert "agent-2" in agents

    def test_api_get_trust_report(self):
        api = self.setup_api()
        report = api.get_trust_report("agent-1")

        assert "agent_id" in report
        assert "trust_score" in report
        assert "neighbors" in report
        assert report["agent_id"] == "agent-1"


class TestTrustVisualizer:
    """T6: 信任可视化测试"""

    def setup_graph(self):
        from maref.security.trust_graph import TrustGraph

        graph = TrustGraph()
        graph.add_agent("a", initial_trust=90.0)
        graph.add_agent("b", initial_trust=70.0)
        graph.add_agent("c", initial_trust=50.0)
        graph.add_edge("a", "b", 80.0)
        graph.add_edge("b", "c", 60.0)
        return graph

    def test_visualizer_nodes(self):
        graph = self.setup_graph()
        viz = TrustVisualizer(graph)

        nodes = viz.get_nodes()
        assert len(nodes) == 3
        assert all("id" in n and "trust_score" in n for n in nodes)

    def test_visualizer_edges(self):
        graph = self.setup_graph()
        viz = TrustVisualizer(graph)

        edges = viz.get_edges()
        assert len(edges) == 2
        assert all("source" in e and "target" in e and "trust_score" in e for e in edges)

    def test_visualizer_cytoscape_format(self):
        graph = self.setup_graph()
        viz = TrustVisualizer(graph)

        cyto = viz.to_cytoscape_format()
        assert "nodes" in cyto
        assert "edges" in cyto
        assert len(cyto["nodes"]) == 3
        assert len(cyto["edges"]) == 2

    def test_visualizer_status_summary(self):
        graph = self.setup_graph()
        viz = TrustVisualizer(graph)

        summary = viz.get_status_summary()
        assert "total_agents" in summary
        assert "total_edges" in summary
        assert "avg_trust" in summary
        assert summary["total_agents"] == 3
        assert summary["total_edges"] == 2
