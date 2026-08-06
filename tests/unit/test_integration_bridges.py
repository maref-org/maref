"""
M6 Athena Integration Bridge Tests

Covers all 6 integration bridges:
- M6.1: DeerFlow DAG node definitions
- M6.2: Symphony protocol adapter
- M6.3: HITL approval tier routing
- M6.4: GrowthBook Feature Flag bridge
- M6.5: Memory system bridge (autoDream/Karpathy)
- M6.6: LLM Gateway routing decisions
"""

from __future__ import annotations

import json

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.deerflow_bridge import DeerFlowBridge, DeerFlowDAG
from maref.integration.flag_bridge import FlagBridge, PolicySnapshot, RolloutStage
from maref.integration.gateway import GatewayRoute, GatewayRouter
from maref.integration.hitl import HITLRouter, HITLStatus, HITLTier
from maref.integration.memory_bridge import MemoryBridge, MemoryPriority, MemoryStage
from maref.integration.symphony import SymphonyAdapter, SymphonyMessageType


class TestDeerFlowBridge:
    """M6.1: DeerFlow DAG node bridge."""

    def test_build_governance_dag(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        assert isinstance(dag, DeerFlowDAG)
        assert len(dag.nodes) == 10
        assert dag.name == "maref_governance"

    def test_all_states_have_nodes(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        node_types = {n.node_type for n in dag.nodes}
        for state in GovernanceState:
            assert f"maref.state.{state.name}" in node_types

    def test_node_has_gray_code_metadata(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        for node in dag.nodes:
            assert "gray_code" in node.metadata
            assert "entropy" in node.metadata

    def test_halt_node_is_terminal(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        halt_node = next(n for n in dag.nodes if n.id == "governance_halt")
        assert halt_node.metadata["is_terminal"] is True

    def test_build_observation_pipeline_dag(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_observation_pipeline_dag()
        assert len(dag.nodes) == 5
        pipeline_ids = {n.id for n in dag.nodes}
        assert "observation_collect" in pipeline_ids
        assert "knowledge_sink" in pipeline_ids

    def test_validate_dag(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        result = bridge.validate_dag(dag)
        assert result["valid"] is True
        assert result["error_count"] == 0
        assert result["node_count"] == 10

    def test_export_dag_json(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        exported = bridge.export_dag(dag)
        parsed = json.loads(exported)
        assert parsed["name"] == "maref_governance"
        assert len(parsed["nodes"]) == 10

    def test_dag_to_yaml(self) -> None:
        bridge = DeerFlowBridge()
        dag = bridge.build_governance_dag()
        yaml_str = dag.to_yaml()
        assert "DeerFlow DAG" in yaml_str
        assert "governance_init" in yaml_str

    def test_custom_configs_override_defaults(self) -> None:
        bridge = DeerFlowBridge()
        custom = {GovernanceState.INIT: {"auto_advance": False, "timeout_seconds": 60}}
        dag = bridge.build_governance_dag(custom_configs=custom)
        init_node = next(n for n in dag.nodes if n.id == "governance_init")
        assert init_node.config["auto_advance"] is False
        assert init_node.config["timeout_seconds"] == 60


class TestSymphonyAdapter:
    """M6.2: Symphony protocol adapter."""

    def setup_method(self) -> None:
        self.sm = GovernanceStateMachine()
        self.adapter = SymphonyAdapter(self.sm)

    def test_build_claim(self) -> None:
        msg = self.adapter.build_claim()
        assert msg.msg_type == SymphonyMessageType.CLAIM
        assert "capabilities" in msg.payload
        assert len(msg.payload["capabilities"]) > 0

    def test_build_heartbeat(self) -> None:
        msg = self.adapter.build_heartbeat()
        assert msg.msg_type == SymphonyMessageType.HEARTBEAT
        assert "state" in msg.payload
        assert msg.payload["state"] == "INIT"

    def test_build_status_includes_transitions(self) -> None:
        self.sm.transition(GovernanceState.OBSERVE, "test")
        msg = self.adapter.build_status()
        assert msg.payload["current_state"] == "OBSERVE"
        valid = msg.payload["valid_transitions"]
        assert len(valid) > 0

    def test_handle_transition_command(self) -> None:
        from maref.integration.symphony import SymphonyMessage, SymphonyMessageType

        cmd = SymphonyMessage(
            msg_type=SymphonyMessageType.COMMAND,
            source="test",
            payload={"command": "transition", "target_state": "OBSERVE"},
        )
        resp = self.adapter.handle_command(cmd)
        assert resp.payload["success"] is True
        assert resp.payload["current_state"] == "OBSERVE"

    def test_handle_invalid_transition(self) -> None:
        from maref.integration.symphony import SymphonyMessage, SymphonyMessageType

        cmd = SymphonyMessage(
            msg_type=SymphonyMessageType.COMMAND,
            source="test",
            payload={"command": "transition", "target_state": "HALT"},
        )
        resp = self.adapter.handle_command(cmd)
        assert resp.payload["success"] is False

    def test_handle_force_stabilize(self) -> None:
        from maref.integration.symphony import SymphonyMessage, SymphonyMessageType

        cmd = SymphonyMessage(
            msg_type=SymphonyMessageType.COMMAND,
            source="test",
            payload={"command": "force_stabilize"},
        )
        resp = self.adapter.handle_command(cmd)
        assert resp.payload["success"] is True

    def test_handle_unknown_command(self) -> None:
        from maref.integration.symphony import SymphonyMessage, SymphonyMessageType

        cmd = SymphonyMessage(
            msg_type=SymphonyMessageType.COMMAND,
            source="test",
            payload={"command": "destroy"},
        )
        resp = self.adapter.handle_command(cmd)
        assert resp.msg_type == SymphonyMessageType.ERROR
        assert "unknown_command" in resp.payload["error"]

    def test_export_workflow_md(self) -> None:
        md = self.adapter.export_workflow_md()
        assert "MAREF Governance" in md
        assert "WORKFLOW.md" in md
        assert "Valid Transitions" in md

    def test_message_to_json(self) -> None:
        msg = self.adapter.build_heartbeat()
        j = msg.to_json()
        parsed = json.loads(j)
        assert parsed["source"] == "maref-governance"


class TestHITLRouter:
    """M6.3: HITL approval tier routing."""

    def test_route_critical_to_p0(self) -> None:
        router = HITLRouter()
        event = router.route("critical", "anomaly", "test critical")
        assert event.tier == HITLTier.P0_RESPONSE
        assert event.severity == "critical"

    def test_route_warning_to_p1(self) -> None:
        router = HITLRouter()
        event = router.route("warning", "drift", "test warning")
        assert event.tier == HITLTier.P1_ESCALATE

    def test_route_info_to_p2(self) -> None:
        router = HITLRouter()
        event = router.route("info", "status", "test info")
        assert event.tier == HITLTier.P2_LOG

    def test_route_normal_to_p3(self) -> None:
        router = HITLRouter()
        event = router.route("normal", "heartbeat", "test normal")
        assert event.tier == HITLTier.P3_OBSERVE

    def test_p0_is_blocking(self) -> None:
        router = HITLRouter()
        assert router.is_blocking(HITLTier.P0_RESPONSE) is True
        assert router.is_blocking(HITLTier.P1_ESCALATE) is False

    def test_p1_can_auto_approve(self) -> None:
        router = HITLRouter()
        event = router.route("warning", "drift", "auto approve test")
        assert router.can_auto_approve(event) is True

    def test_approve_and_reject(self) -> None:
        router = HITLRouter()
        event = router.route("warning", "drift", "approval test")
        assert router.approve(event.event_id, "reviewer1") == HITLStatus.APPROVED
        event2 = router.route("critical", "anomaly", "rejection test")
        assert router.reject(event2.event_id, "too risky") == HITLStatus.REJECTED

    def test_get_pending_by_tier(self) -> None:
        router = HITLRouter()
        router.route("critical", "anomaly", "p0 pending")
        router.route("warning", "drift", "p1 pending")
        p0_pending = router.get_pending(HITLTier.P0_RESPONSE)
        assert len(p0_pending) == 1
        assert p0_pending[0].tier == HITLTier.P0_RESPONSE

    def test_get_stats(self) -> None:
        router = HITLRouter()
        router.route("critical", "anomaly", "test")
        router.route("warning", "drift", "test")
        stats = router.get_stats()
        assert stats["total_events"] == 2
        assert "by_tier" in stats

    def test_update_tier_mapping(self) -> None:
        router = HITLRouter()
        router.update_tier_mapping("critical", HITLTier.P1_ESCALATE)
        event = router.route("critical", "anomaly", "demoted critical")
        assert event.tier == HITLTier.P1_ESCALATE

    def test_event_counter_increments(self) -> None:
        router = HITLRouter()
        e1 = router.route("critical", "anomaly", "first")
        e2 = router.route("warning", "drift", "second")
        assert e1.event_id == "hitl-000001"
        assert e2.event_id == "hitl-000002"


class TestFlagBridge:
    """M6.4: Feature Flag bridge (GrowthBook-compatible)."""

    def test_create_flag_canary_1(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        flag = bridge.create_flag(baseline, candidate, "test_policy")

        assert flag.key.startswith("maref_policy_")
        assert len(flag.variations) == 2
        assert flag.metadata["stage"] == 1

    def test_advance_to_full(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        flag = bridge.create_flag(baseline, candidate)

        bridge.advance_stage(flag, RolloutStage.FULL)
        assert flag.metadata["stage"] == 100
        assert flag.default_variation == 1

    def test_rollback(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        flag = bridge.create_flag(baseline, candidate)

        bridge.rollback(flag, "FNR too high")
        assert flag.metadata["stage"] == 0
        assert flag.metadata["stage_name"] == "ROLLED_BACK"

    def test_export_growthbook_json(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        bridge.create_flag(baseline, candidate, "test_export")

        exported = bridge.export_all()
        assert len(exported) == 1
        gb_json = exported[0]
        assert gb_json["key"].startswith("maref_policy_")
        assert "variations" in gb_json

    def test_build_canary_pipeline(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        pipeline = bridge.build_canary_pipeline(baseline, candidate, "canary_test")

        assert len(pipeline) == 4
        assert pipeline[0]["stage"] == 1
        assert pipeline[-1]["stage"] == 100

    def test_get_active_flags(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})

        active = bridge.create_flag(baseline, candidate, "active_flag", RolloutStage.CANARY_10)
        bridge.rollback(active)

        active_flags = bridge.get_active_flags()
        assert len(active_flags) == 0

    def test_get_stats(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"kl_warning": 0.05})
        candidate = PolicySnapshot(config={"kl_warning": 0.03})
        bridge.create_flag(baseline, candidate, "flag_a")
        bridge.create_flag(baseline, candidate, "flag_b")

        stats = bridge.get_stats()
        assert stats["total_flags"] == 2


class TestMemoryBridge:
    """M6.5: Memory system bridge (autoDream + Karpathy)."""

    def test_push_to_autodream(self) -> None:
        bridge = MemoryBridge()
        entry = bridge.push_to_autodream(
            content="High entropy in DECIDE state correlates with oscillation",
            confidence=0.85,
            priority=MemoryPriority.HIGH,
            tags=["entropy", "oscillation"],
        )
        assert entry.stage == MemoryStage.ORIENT
        assert entry.confidence == 0.85
        assert entry.priority == MemoryPriority.HIGH

    def test_push_to_karpathy(self) -> None:
        bridge = MemoryBridge()
        entry = bridge.push_to_karpathy(
            content="FNR decreased from 66.7% to 5.3% with dual-threshold detection",
            confidence=0.92,
            tags=["fnr", "dual-threshold", "observability"],
        )
        assert entry.stage == MemoryStage.CONSOLIDATE
        assert entry.priority == MemoryPriority.HIGH
        assert entry.to_karpathy_wiki_entry()["confidence"] == 0.92

    def test_query_memory_by_content(self) -> None:
        bridge = MemoryBridge()
        bridge.push_to_autodream("entropy correlation found", confidence=0.8)
        bridge.push_to_karpathy("observability fix deployed", confidence=0.9)

        results = bridge.query_memory("entropy")
        assert len(results) == 1
        assert "entropy" in results[0].content

    def test_query_memory_by_tag(self) -> None:
        bridge = MemoryBridge()
        bridge.push_to_autodream("test A", tags=["entropy"])
        bridge.push_to_autodream("test B", tags=["oscillation"])

        results = bridge.query_memory("test", tag_filter=["entropy"])
        assert len(results) == 1
        assert "entropy" in results[0].tags

    def test_extract_insights_from_graph(self) -> None:
        bridge = MemoryBridge()
        stats = {
            "orphan_ratio": 0.6,
            "active_hypotheses": [
                {"id": "H1", "description": "Entropy threshold too low", "confidence": 0.8},
                {"id": "H2", "description": "Weak signal ignored", "confidence": 0.3},
            ],
        }
        insights = bridge.extract_insights_from_graph(stats, min_confidence=0.5)
        assert len(insights) == 2

    def test_export_all(self) -> None:
        bridge = MemoryBridge()
        bridge.push_to_autodream("hypothesis 1", confidence=0.85)
        bridge.push_to_karpathy("finding 1", confidence=0.92)

        exported = bridge.export_all()
        assert len(exported["autodream_queue"]) == 1
        assert len(exported["karpathy_entries"]) == 1

    def test_get_stats(self) -> None:
        bridge = MemoryBridge()
        bridge.push_to_autodream("test", confidence=0.85, priority=MemoryPriority.HIGH)
        bridge.push_to_karpathy("test", confidence=0.3)

        stats = bridge.get_stats()
        assert stats["total_entries"] == 2
        assert stats["high_confidence_count"] == 1


class TestGatewayRouter:
    """M6.6: LLM Gateway routing bridge."""

    def test_low_entropy_routes_cheap(self) -> None:
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.OBSERVE, entropy=0)
        assert decision.route == GatewayRoute.CHEAP
        assert decision.entropy == 0

    def test_high_entropy_routes_deterministic(self) -> None:
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ACT, entropy=4)
        assert decision.route == GatewayRoute.DETERMINISTIC

    def test_halt_routes_fallback(self) -> None:
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.HALT, entropy=0)
        assert decision.route == GatewayRoute.FALLBACK

    def test_circuit_open_routes_fallback(self) -> None:
        router = GatewayRouter()
        router.set_circuit_open(True)
        decision = router.compute_route(GovernanceState.OBSERVE, entropy=1)
        assert decision.route == GatewayRoute.FALLBACK
        assert "circuit breaker" in decision.explanation.lower()

    def test_budget_cheap_affects_routing(self) -> None:
        router = GatewayRouter(budget_tier="cheap")
        decision = router.compute_route(GovernanceState.OBSERVE, entropy=0)
        assert decision.route == GatewayRoute.CHEAP

    def test_budget_premium_affects_routing(self) -> None:
        router = GatewayRouter(budget_tier="premium")
        decision = router.compute_route(GovernanceState.EVALUATE, entropy=3)
        assert decision.route in (GatewayRoute.CAPABLE, GatewayRoute.DETERMINISTIC)

    def test_decision_history_recorded(self) -> None:
        router = GatewayRouter()
        router.compute_route(GovernanceState.OBSERVE, entropy=0)
        router.compute_route(GovernanceState.ACT, entropy=4)
        assert len(router.get_recent_decisions(10)) == 2

    def test_get_stats(self) -> None:
        router = GatewayRouter()
        router.compute_route(GovernanceState.OBSERVE, entropy=0)
        router.compute_route(GovernanceState.ACT, entropy=4)
        stats = router.get_stats()
        assert stats["total_decisions"] == 2
        assert "route_distribution" in stats

    def test_routing_confidence_between_0_and_1(self) -> None:
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ANALYZE, entropy=2)
        assert 0.0 < decision.confidence <= 1.0

    def test_all_states_produce_valid_route(self) -> None:
        router = GatewayRouter()
        for state in GovernanceState:
            for entropy in range(5):
                decision = router.compute_route(state, entropy=entropy)
                assert isinstance(decision.route, GatewayRoute)
