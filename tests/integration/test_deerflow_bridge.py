from __future__ import annotations

import json

from maref.governance.types import GovernanceState
from maref.integration.deerflow_bridge import (
    DeerFlowBridge,
    DeerFlowDAG,
    DeerFlowNode,
)


class TestDeerFlowNode:
    def test_to_dict(self) -> None:
        node = DeerFlowNode(
            id="test-node",
            node_type="maref.state.DECIDE",
            config={"threshold": 0.7},
            depends_on=["prev-node"],
            metadata={"key": "val"},
        )
        d = node.to_dict()
        assert d["id"] == "test-node"
        assert d["type"] == "maref.state.DECIDE"
        assert d["config"] == {"threshold": 0.7}
        assert d["depends_on"] == ["prev-node"]
        assert d["metadata"] == {"key": "val"}

    def test_to_dict_empty_defaults(self) -> None:
        node = DeerFlowNode(id="n1", node_type="type.a")
        d = node.to_dict()
        assert d["config"] == {}
        assert d["depends_on"] == []
        assert d["metadata"] == {}


class TestDeerFlowDAG:
    def test_to_dict(self) -> None:
        node = DeerFlowNode(id="n1", node_type="type.a")
        dag = DeerFlowDAG(name="test_dag", nodes=[node])
        d = dag.to_dict()
        assert d["name"] == "test_dag"
        assert d["version"] == "1.0"
        assert len(d["nodes"]) == 1

    def test_to_yaml(self) -> None:
        node = DeerFlowNode(
            id="n1", node_type="type.a", config={"key": "val"}, depends_on=["n0"]
        )
        dag = DeerFlowDAG(name="test", nodes=[node])
        yaml = dag.to_yaml()
        assert "DeerFlow DAG: test" in yaml
        assert "id: n1" in yaml
        assert "type: type.a" in yaml
        assert "depends_on: [n0]" in yaml

    def test_to_yaml_no_config_or_deps(self) -> None:
        node = DeerFlowNode(id="n1", node_type="type.a")
        dag = DeerFlowDAG(name="empty", nodes=[node])
        yaml = dag.to_yaml()
        assert "config:" not in yaml
        assert "depends_on:" not in yaml


class TestDeerFlowBridge:
    def test_build_governance_dag_includes_all_states(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        assert isinstance(dag, DeerFlowDAG)
        assert dag.name == "maref_governance"
        assert len(dag.nodes) == len(list(GovernanceState))

    def test_build_governance_dag_node_types(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        for state in GovernanceState:
            matching = [
                n for n in dag.nodes if n.node_type == f"maref.state.{state.name}"
            ]
            assert len(matching) == 1, f"Missing node for {state.name}"

    def test_build_governance_dag_with_custom_config(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag(
            custom_configs={GovernanceState.DECIDE: {"require_quorum": True}}
        )
        decide_node = next(
            n for n in dag.nodes if n.id == "governance_decide"
        )
        assert decide_node.config["require_quorum"] is True

    def test_build_governance_dag_custom_name(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag(dag_name="custom_dag")
        assert dag.name == "custom_dag"

    def test_build_governance_dag_gray_code_metadata(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        for node in dag.nodes:
            assert "gray_code" in node.metadata
            assert "entropy" in node.metadata
            assert "is_terminal" in node.metadata

    def test_build_observation_pipeline_dag(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_observation_pipeline_dag()
        assert dag.name == "maref_observation_pipeline"
        assert len(dag.nodes) == 5
        node_ids = [n.id for n in dag.nodes]
        assert "observation_collect" in node_ids
        assert "probe_read" in node_ids
        assert "anomaly_detect" in node_ids
        assert "governance_decide" in node_ids
        assert "knowledge_sink" in node_ids

    def test_observation_pipeline_dependencies(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_observation_pipeline_dag()
        probe = next(n for n in dag.nodes if n.id == "probe_read")
        assert "observation_collect" in probe.depends_on

    def test_validate_dag_valid(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        result = bridge.validate_dag(dag)
        assert result["valid"] is True
        assert result["error_count"] == 0
        assert result["node_count"] == len(list(GovernanceState))

    def test_validate_dag_invalid_state(self) -> None:
        bridge = DeerFlowBridge()
        dag = DeerFlowDAG(
            name="bad",
            nodes=[DeerFlowNode(id="bad", node_type="maref.state.INVALID_STATE")],
        )
        result = bridge.validate_dag(dag)
        assert result["valid"] is False
        assert result["error_count"] >= 1

    def test_validate_dag_missing_dependency(self) -> None:
        bridge = DeerFlowBridge()
        dag = DeerFlowDAG(
            name="bad",
            nodes=[
                DeerFlowNode(
                    id="n1", node_type="type.a", depends_on=["nonexistent"]
                )
            ],
        )
        result = bridge.validate_dag(dag)
        assert result["valid"] is False
        assert any("nonexistent" in e for e in result["errors"])

    def test_validate_dag_halt_warning(self) -> None:
        bridge = DeerFlowBridge()
        dag = DeerFlowDAG(
            name="halt_test",
            nodes=[
                DeerFlowNode(id="start", node_type="maref.state.INIT"),
                DeerFlowNode(id="governance_halt", node_type="maref.state.HALT"),
            ],
        )
        result = bridge.validate_dag(dag)
        assert result["valid"] is True  # halt warning is not an error
        assert result["warning_count"] >= 1

    def test_validate_dag_halt_no_warning_when_depended(self) -> None:
        bridge = DeerFlowBridge()
        dag = DeerFlowDAG(
            name="halt_with_dep",
            nodes=[
                DeerFlowNode(id="start", node_type="maref.state.INIT"),
                DeerFlowNode(
                    id="governance_halt",
                    node_type="maref.state.HALT",
                    depends_on=["start"],
                ),
                DeerFlowNode(
                    id="after_halt",
                    node_type="maref.state.REPORT",
                    depends_on=["governance_halt"],
                ),
            ],
        )
        result = bridge.validate_dag(dag)
        # No warning about halt having no dependents
        assert not any("HALT" in w for w in result["warnings"])

    def test_export_dag(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        exported = bridge.export_dag(dag)
        parsed = json.loads(exported)
        assert parsed["name"] == "maref_governance"
        assert len(parsed["nodes"]) == len(list(GovernanceState))

    def test_build_governance_dag_configs_present(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        for node in dag.nodes:
            assert isinstance(node.config, dict)

    def test_build_governance_dag_entropy_metadata(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        for node in dag.nodes:
            assert isinstance(node.metadata["entropy"], int)
