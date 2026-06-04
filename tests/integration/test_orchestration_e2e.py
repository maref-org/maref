from __future__ import annotations

from typing import Any

from maref.recursive.agent_handoff import (
    AgentHandoffProtocol,
    HandoffReason,
    HandoffRequest,
)
from maref.recursive.agent_marketplace import (
    AgentMarketplace,
    CapabilityListing,
    TrustLevel,
)
from maref.recursive.hybrid_decomposer import HybridDecomposer
from maref.recursive.joint_state_machine import JointStateMachine
from maref.recursive.orchestration_perf import (
    ConcurrentOrchestrator,
    OrchestrationCache,
)
from maref.recursive.safety_gate import SafetyGateV2
from maref.recursive.self_orchestrator import SelfOrchestrator


class MockLLM:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self._response = response

    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._response or {"subtasks": []}


class TestFullPipelineHybridDecomposition:
    def test_simple_optimize_with_hybrid(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": "observe_perf",
                    "description": "Observe performance",
                    "capabilities": ["observe", "collect"],
                    "dependencies": [],
                },
                {
                    "id": "analyze_bottlenecks",
                    "description": "Analyze bottlenecks",
                    "capabilities": ["graph_query", "hypothesis_test"],
                    "dependencies": ["observe_perf"],
                },
                {
                    "id": "propose_fixes",
                    "description": "Propose fixes",
                    "capabilities": ["state_transition"],
                    "dependencies": ["analyze_bottlenecks"],
                },
                {
                    "id": "verify_trust",
                    "description": "Verify trust",
                    "capabilities": ["trust_evaluate", "vc_verify"],
                    "dependencies": ["propose_fixes"],
                },
            ]
        }
        llm = MockLLM(response)
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("optimize_system")
        assert result.dag.node_count == 4
        assert result.decomposition_source == "hybrid"
        assert len(result.dispatch_results) == 4

    def test_unknown_task_with_hybrid_llm(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": "investigate",
                    "description": "Investigate unknown task",
                    "capabilities": ["observe", "collect"],
                    "dependencies": [],
                },
                {
                    "id": "report_findings",
                    "description": "Report findings",
                    "capabilities": ["vc_verify"],
                    "dependencies": ["investigate"],
                },
            ]
        }
        llm = MockLLM(response)
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("unknown_emergent_task")
        assert result.dag.node_count == 2
        assert result.decomposition_source == "hybrid"

    def test_llm_timeout_falls_back_to_template(self) -> None:
        decomp = HybridDecomposer()
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("diagnose_anomaly")
        assert result.dag.node_count == 3
        assert result.decomposition_source == "hybrid"

    def test_safety_gate_rejects_dangerous_and_falls_back(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": f"task_{i}",
                    "description": f"Task {i}",
                    "capabilities": ["halt", "circuit_break"],
                    "dependencies": [],
                }
                for i in range(9)
            ]
        }
        llm = MockLLM(response)
        sg = SafetyGateV2()
        decomp = HybridDecomposer(llm_backend=llm, safety_gate=sg)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("dangerous_task")
        assert result.dag.node_count == 0


class TestFullPipelineHandoff:
    def test_handoff_full_flow(self) -> None:
        handoff_protocol = AgentHandoffProtocol()
        jsm = JointStateMachine()

        jsm.register_agent("governance_agent")
        jsm.register_agent("kg_agent")
        jsm.register_agent("sidecar_agent")

        handoff_protocol.set_trust("governance_agent", "kg_agent", 0.8)

        req = HandoffRequest(
            from_agent="governance_agent",
            to_agent="kg_agent",
            reason=HandoffReason.SUBTASK_COMPLETE,
            task_context={"task": "verify_decision"},
            transfer_state={"decision": "approved", "confidence": 0.9},
        )
        result = handoff_protocol.request_handoff(req)
        assert result.accepted is True

        assert jsm.initiate_handoff("governance_agent", "kg_agent") is True
        assert jsm.agents["governance_agent"] == "HANDOFF_SOURCE"
        assert jsm.agents["kg_agent"] == "HANDOFF_TARGET"

        assert jsm.complete_handoff("governance_agent") is True
        assert jsm.agents["governance_agent"] == "DONE"
        assert jsm.agents["kg_agent"] == "RUNNING"

        handoff_protocol.complete_handoff(result.handoff_id, {"status": "completed"})
        stats = handoff_protocol.stats()
        assert stats["completed"] == 1

    def test_handoff_capability_mismatch(self) -> None:
        handoff_protocol = AgentHandoffProtocol()
        jsm = JointStateMachine()
        jsm.register_agent("sidecar_agent")
        jsm.register_agent("governance_agent")

        handoff_protocol.set_trust("sidecar_agent", "governance_agent", 0.6)
        req = HandoffRequest(
            from_agent="sidecar_agent",
            to_agent="governance_agent",
            reason=HandoffReason.CAPABILITY_MISMATCH,
        )
        result = handoff_protocol.request_handoff(req)
        assert result.accepted is True

    def test_handoff_escalation_requires_trust(self) -> None:
        handoff_protocol = AgentHandoffProtocol()
        handoff_protocol.set_trust("sidecar_agent", "governance_agent", 0.4)
        req = HandoffRequest(
            from_agent="sidecar_agent",
            to_agent="governance_agent",
            reason=HandoffReason.ESCALATION,
        )
        result = handoff_protocol.request_handoff(req)
        assert result.accepted is False

    def test_handoff_timeout_rollback(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b", timeout_seconds=0.001)
        import time
        time.sleep(0.01)
        timed_out = jsm.check_handoff_timeout()
        assert len(timed_out) > 0
        assert jsm.agents["agent_a"] == "RUNNING"


class TestFullPipelineMarketplaceIntegration:
    def test_marketplace_list_and_negotiate(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.economy.register_agent("buyer", initial_balance=100.0)
        marketplace.economy.register_agent("seller", initial_balance=100.0)

        listing = CapabilityListing(
            agent_id="seller",
            capability="graph_query",
            price=20.0,
            trust_requirement=TrustLevel.MEDIUM,
            sla={"latency_ms": 100},
        )
        marketplace.publish(listing)

        discovered = marketplace.discover("graph_query")
        assert len(discovered) == 1

        result = marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        assert result.accepted is True

        wallet = marketplace.economy.get_wallet("buyer")
        assert wallet is not None
        assert wallet.balance < 100.0

    def test_marketplace_multiple_agents(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.economy.register_agent("agent_a", initial_balance=100.0)
        marketplace.economy.register_agent("agent_b", initial_balance=100.0)
        marketplace.economy.register_agent("agent_c", initial_balance=100.0)

        marketplace.publish(CapabilityListing("agent_a", "observe", price=5.0))
        marketplace.publish(CapabilityListing("agent_b", "observe", price=3.0))
        marketplace.publish(CapabilityListing("agent_c", "graph_query", price=8.0))

        results = marketplace.discover("observe")
        assert len(results) == 2
        assert results[0].price == 3.0
        assert results[1].price == 5.0


class TestFullPipelineSafetyIntegration:
    def test_safety_gate_across_layers(self) -> None:
        sg = SafetyGateV2()

        threat = sg.detect_core_removal("circuit_breaker_config")
        assert threat.blocked is True

        dec_threat = sg.validate_decomposition(13, ["observe"])
        assert dec_threat.blocked is True

        hoff_threat = sg.validate_handoff(
            "sidecar", "governance",
            ["observe"], ["halt", "circuit_break"],
        )
        assert hoff_threat.blocked is True

        cap_threat = sg.validate_capability_assignment(
            ["halt"], ["observe"],
        )
        assert cap_threat.blocked is True

    def test_concurrent_orchestrator_with_safety(self) -> None:
        ConcurrentOrchestrator()
        c = OrchestrationCache(max_size=100)
        c.put("test", "value")
        assert c.get("test") == "value"


class TestFullPipelineBackwardCompatibility:
    def test_original_orchestrator_still_works(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        result = orch.orchestrate("optimize_system")
        assert result.dag.node_count == 4
        assert result.timed_out is False
        assert len(result.sync_log) > 0

    def test_original_decomposer_still_works(self) -> None:
        from maref.recursive.task_decomposer import TaskDecomposer
        dec = TaskDecomposer()
        dag = dec.decompose("optimize_system")
        assert dag.node_count == 4

    def test_original_jsm_still_works(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance("a", "RUNNING")
        jsm.advance("b", "RUNNING")
        assert jsm.all_at_barrier("RUNNING") is True
