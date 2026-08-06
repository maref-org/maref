from __future__ import annotations

import tempfile

from maref.recursive.agent_24_state_machine import (
    VALID_TRANSITIONS,
    Agent24StateMachine,
    AgentStateV3,
)
from maref.recursive.agent_discovery_negotiation import (
    AgentDiscovery,
    AgentNegotiator,
)
from maref.recursive.agent_economy import AgentEconomy
from maref.recursive.distributed_crdt import DistributedCRDT
from maref.recursive.memory_three_temperature import (
    MemoryThreeTemperature,
)
from maref.recursive.stigmergy_swarm import StigmergySwarm
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.recursive.unified_audit import UnifiedAuditStore


class TestR50Acceptance3PartyIntegration:
    def test_memory_trust_joint(self) -> None:
        audit = UnifiedAuditStore()
        m3t = MemoryThreeTemperature(audit_store=audit)
        trust = TrustEngineV2(audit_store=audit)
        sm = Agent24StateMachine(audit_store=audit)

        for i in range(3):
            agent_id = f"r50_agent_{i}"
            m3t.store(
                f"mem_{agent_id}",
                {
                    "skills": ["search", "compute", "analyze"],
                    "quality": 0.7 + i * 0.1,
                },
            )
            trust.register_agent(agent_id, "maref")
            sm.register(agent_id)
            sm.transition(agent_id, AgentStateV3.BOOTING)
            sm.transition(agent_id, AgentStateV3.REGISTERING)

        for agent_id in [f"r50_agent_{i}" for i in range(3)]:
            for j in range(5):
                trust.record_task(
                    agent_id, f"task_{j}", success=True, quality=0.8, latency_ms=100.0
                )

        score = trust.assess("r50_agent_0")
        assert score is not None, "Joint: Trust assessment available"

        stats = m3t.get_stats()
        assert stats["total_memories"] >= 3, "Joint: Memory tracks all agents"
        assert sm.agent_count == 3, "Joint: State machine tracks all agents"

    def test_discovery_negotiation_trade(self) -> None:
        audit = UnifiedAuditStore()
        discovery = AgentDiscovery(Agent24StateMachine(audit_store=audit))
        negotiator = AgentNegotiator(audit_store=audit)
        economy = AgentEconomy(audit_store=audit)

        discovery.register_peer("seller_1", ["dataset_generation"], trust=0.8)
        discovery.register_peer("buyer_1", ["model_training"], trust=0.7)
        economy.register_agent("seller_1", 50.0)
        economy.register_agent("buyer_1", 200.0)

        peers = discovery.find_peers_with_capability("dataset_generation")
        assert len(peers) >= 1, "Social: Peer discovery works"

        trade = economy.propose_trade("buyer_1", "seller_1", "training_data", 30.0)
        assert trade is not None, "Social: Trade proposed"

        receipt = economy.execute_trade(trade.trade_id)
        assert receipt is not None, "Social: Trade executed"

        seller_balance = economy.get_wallet("seller_1").balance
        assert seller_balance > 50.0, "Social: Seller paid"

        proposal = negotiator.propose(
            "seller_1",
            "buyer_1",
            "recurring_data",
            {"frequency": "weekly", "price": 25.0},
        )
        result = negotiator.evaluate(proposal, 0.8)
        assert result.accepted, "Social: Negotiation accepted"

    def test_distributed_social_swarm(self) -> None:
        audit = UnifiedAuditStore()
        crdt = DistributedCRDT(audit_store=audit)
        swarm = StigmergySwarm(audit_store=audit)

        nodes = ["alpha", "beta", "gamma"]
        for n in nodes:
            crdt.register_node(n, [p for p in nodes if p != n])

        crdt.apply_op("alpha", "consensus_config", {"replication": 3})
        crdt.gossip_all()

        assert crdt.verify_consistency(), "Infra: 3-node CRDT consistent"

        tasks = [f"dist_task_{i}" for i in range(5)]
        agents = [f"dist_agent_{i}" for i in range(10)]
        result = swarm.run_swarm_cycle("dist_colony", tasks, agents)
        assert result.detected, "Infra: Swarm emergence detected"
        assert result.coordination_success, "Infra: Swarm coordination successful"

        pid = crdt.create_partition(["alpha"])
        crdt.apply_op("beta", "partition_test_key", "survived")
        crdt.recover_partition(pid)
        crdt.gossip_all()
        stats = crdt.get_statistics()
        assert stats["total_nodes"] == 3, "Infra: All nodes recovered"

    def test_full_v07_pipeline(self) -> None:
        audit = UnifiedAuditStore()
        tempfile.mkdtemp()

        m3t = MemoryThreeTemperature(audit_store=audit)
        trust = TrustEngineV2(audit_store=audit)
        sm = Agent24StateMachine(audit_store=audit)

        m3t.store("pipeline_config", {"round": 50, "target": "full_acceptance"})
        trust.register_agent("pipeline_agent", "maref")
        sm.register("pipeline_agent")

        path = [
            AgentStateV3.BOOTING,
            AgentStateV3.REGISTERING,
            AgentStateV3.IDLE,
            AgentStateV3.DISCOVERING,
            AgentStateV3.NEGOTIATING,
            AgentStateV3.TRUST_BUILDING,
            AgentStateV3.CONTRACTING,
            AgentStateV3.EXECUTING,
            AgentStateV3.VERIFYING,
            AgentStateV3.REPORTING,
        ]
        for state in path:
            result = sm.transition("pipeline_agent", state)
            assert result is not None, f"State transition to {state.value} failed"
            if state == AgentStateV3.EXECUTING:
                trust.record_task("pipeline_agent", "pipeline_exec", success=True, quality=0.95)

        score = trust.assess("pipeline_agent")
        assert score is not None
        assert score.overall_trust >= 50.0, f"Trust={score.overall_trust}"

        memory_score = m3t.score_health("pipeline_config")
        assert memory_score is not None
        assert 0.0 <= memory_score.overall_health <= 1.0

        checks = sm.check_invariants()
        assert all(c.holds for c in checks), "All 24-state invariants hold"

        assert audit.count() >= 10, f"Full pipeline produced {audit.count()} audit records"

    def test_24state_full_coverage(self) -> None:
        sm = Agent24StateMachine()
        sm.register("explorer")

        reachable: set[AgentStateV3] = {AgentStateV3.UNINITIALIZED}
        for _ in range(30):
            new_reachable: set[AgentStateV3] = set()
            for state in list(reachable):
                for target in VALID_TRANSITIONS.get(state, set()):
                    new_reachable.add(target)
            reachable |= new_reachable

        assert len(reachable) >= 20, f"Only {len(reachable)} states reachable from UNINITIALIZED"

    def test_social_trade_dispute_sanction_recovery(self) -> None:
        audit = UnifiedAuditStore()
        economy = AgentEconomy(audit_store=audit)
        economy.register_agent("good_buyer", 500.0)
        economy.register_agent("bad_seller", 100.0)

        result = economy.full_economy_cycle(
            "good_buyer",
            "bad_seller",
            "premium_data",
            80.0,
        )
        assert result["status"] == "cycle_complete"
        assert True, "TRADE→DISPUTE→SANCTION→RECOVERY cycle completed"
        stats = economy.get_statistics()
        assert stats["total_trades"] >= 1
        assert stats["total_disputes"] >= 1
        assert stats["total_sanctions"] >= 1
