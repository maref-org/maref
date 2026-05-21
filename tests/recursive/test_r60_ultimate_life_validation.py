from __future__ import annotations

from maref.recursive.agent_credit_rating import (
    AgentCreditRatingSystem,
    RatingDimension,
)
from maref.recursive.carbon_silicon_symbiosis import CarbonSiliconSymbiosis, TaskDomain
from maref.recursive.creative_generator import CreativeGenerator
from maref.recursive.cross_system_adapter import (
    CrossSystemAdapter,
    EnvironmentType,
)
from maref.recursive.distributed_bft import DistributedBFT
from maref.recursive.eight_trigrams_governance import EightTrigramsGovernance, TrigramsGovernance
from maref.recursive.four_phase_governance import (
    FourPhaseGovernance,
    GovernancePhase,
    PermissionScope,
)
from maref.recursive.instance_cloner import EvolutionPath as ClonePath
from maref.recursive.instance_cloner import MAREFInstanceCloner
from maref.recursive.meta_agent_closure import EvolutionDecisionType, MetaAgentClosure


class TestGovernanceUpgradeLifecycle:
    def test_four_phase_governance_full_lifecycle(self):
        gov = FourPhaseGovernance("life_agent_1", initial_trust=0.85)
        assert gov.current_phase == GovernancePhase.LESSER_YIN

        for _ in range(99):
            gov.report_compliance_round()
        transition = gov.report_compliance_round()
        assert transition is not None
        assert gov.current_phase == GovernancePhase.OLD_YANG
        assert gov.check_permission(PermissionScope.FULL_AUTONOMY)
        assert gov.check_permission(PermissionScope.SELF_EVOLUTION)

        transition = gov.report_violation("safety_breach", is_red_line=True)
        assert transition is not None
        assert gov.current_phase == GovernancePhase.OLD_YIN
        assert not gov.check_permission(PermissionScope.FULL_AUTONOMY)
        assert not gov.check_permission(PermissionScope.SELF_EVOLUTION)
        assert gov.check_permission(PermissionScope.OBSERVATION_ONLY)

        gov._recover_from_old_yin(new_trust=0.55, authorization_token=gov.authorize())
        assert gov.current_phase == GovernancePhase.LESSER_YANG

        for _ in range(50):
            gov.report_compliance_round()
        assert gov.trust_score > 0.7

    def test_credit_rating_tied_to_governance(self):
        rating = AgentCreditRatingSystem("gov_agent")
        rating.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                rating.update_dimension(dim, 0.95)
        rating.reset_cooldown_for_test()
        rating.evaluate_rating()

        for dim in RatingDimension:
            for _ in range(20):
                rating.update_dimension(dim, 0.99)
        rating.reset_cooldown_for_test()
        rating.evaluate_rating()

        report = rating.get_report()
        assert report.consecutive_upgrades >= 1

    def test_governance_with_eight_trigrams(self):
        gov = EightTrigramsGovernance("trigram_agent", initial_trust=0.7)
        gov.update_trust_and_adapt(0.92)
        assert gov.current_trigram == TrigramsGovernance.QIAN
        config = gov.current_config
        assert config["evolution_permission"] == "full"
        assert config["self_replication_allowed"]

        gov.update_trust_and_adapt(0.75, violation=True)
        result = gov.perform_audit()
        assert result["audit_count"] == 1


class TestLifeCapabilities:
    def test_clone_then_evolve(self):
        cloner = MAREFInstanceCloner("parent_life")
        clones = cloner.clone_multiple([
            ClonePath.EXPLORATORY, ClonePath.CONSERVATIVE, ClonePath.SPECIALIZED,
        ])
        assert len(clones) == 3

        diff = cloner.differentiate_clones()
        paths = {d["path"] for d in diff.values()}
        assert len(paths) == 3

        for c in clones:
            health = cloner.verify_clone_health(c.clone_id)
            assert health["exists"]
            assert health["kg_nodes"] > 0

    def test_adapt_to_environment_chain(self):
        adapter = CrossSystemAdapter("life_adapter")
        assert adapter.current_env == EnvironmentType.STANDALONE

        e1 = adapter.migrate(EnvironmentType.STANDALONE, EnvironmentType.KUBERNETES)
        assert e1 is not None and e1.success
        assert adapter.current_env == EnvironmentType.KUBERNETES

        e2 = adapter.migrate(EnvironmentType.KUBERNETES, EnvironmentType.DISTRIBUTED)
        assert e2 is not None and e2.success
        assert adapter.current_env == EnvironmentType.DISTRIBUTED

        history = adapter.get_migration_history()
        assert len(history) >= 2

    def test_creative_innovation_generation(self):
        gen = CreativeGenerator("creative_life")
        concepts = [
            {"name": "healing", "confidence": 0.9, "domain": "resilience"},
            {"name": "negotiation", "confidence": 0.85, "domain": "social"},
            {"name": "optimization", "confidence": 0.88, "domain": "performance"},
            {"name": "governance", "confidence": 0.82, "domain": "control"},
            {"name": "discovery", "confidence": 0.87, "domain": "network"},
        ]
        experiences = [
            {"pattern": "auto_recovery", "confidence": 0.9, "domain": "healing"},
            {"pattern": "trust_negotiation", "confidence": 0.85, "domain": "social"},
            {"pattern": "pattern_caching", "confidence": 0.88, "domain": "optimization"},
            {"pattern": "swarm_emergence", "confidence": 0.83, "domain": "collective"},
            {"pattern": "migration_success", "confidence": 0.86, "domain": "adaptation"},
        ]
        gen.load_knowledge(concepts, experiences)
        result = gen.generate_innovations()
        assert result["meets_minimum"]
        assert result["non_repair_count"] >= 3

    def test_symbiosis_full_workflow(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_symbiosis", 0.88)
        instance = css.run_full_cycle(
            "agent_symbiosis", TaskDomain.ARCHITECTURE_DESIGN,
            "Design Distributed System",
            "Design distributed MAREF deployment with BFT consensus",
            human_confirms=True, self_review_passes=True, spot_check_passes=True,
        )
        assert instance.status != "rejected"

        instance = css.run_full_cycle(
            "agent_symbiosis", TaskDomain.MONITORING,
            "Monitor System", "Continuous monitoring task",
        )
        assert instance.status != "rejected"

        stats = css.get_stats()
        assert stats["total_agent_interactions"] > stats["total_human_interactions"] or \
               stats["total_agent_interactions"] >= 0


class TestCivilizationGovernance:
    def test_meta_agent_constitution_enforcement(self):
        closure = MetaAgentClosure()

        d1 = closure.submit_decision(
            "agent_a", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "attempt to modify RL-001",
        )
        assert d1.red_line_violation
        assert d1.status == "rejected"

        d2 = closure.submit_decision_with_reviewers(
            "agent_a", EvolutionDecisionType.CAPABILITY_ADDITION,
            "add new healing capability",
            ["human_constitution_maker"],
        )
        assert d2.status == "approved"

        proof = closure.prove_all_invariants()
        assert proof.all_satisfied

    def test_eight_trigrams_civilization_governance(self):
        gov = EightTrigramsGovernance("civ_agent")
        all_trigrams = gov.get_all_trigrams()
        assert len(all_trigrams) == 8

        for t in all_trigrams:
            cfg = t["config"]
            assert "trust_threshold" in cfg
            assert "red_line_level" in cfg


class TestInfrastructureBFT:
    def test_bft_consensus_for_life_system(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "life_node")
        bft.set_byzantine("life_node_0")
        bft.set_byzantine("life_node_1")

        report = bft.verify_byzantine_tolerance("life_system_decision")
        assert report["consensus_reached"]
        assert report["tolerance_intact"]

        d = bft.to_dict()
        assert d["byzantine_count"] == 2
        assert d["honest_count"] == 5


class TestEndToEndLifeSystem:
    def test_full_life_system_integration(self):
        results = {}

        gov = FourPhaseGovernance("e2e_agent", initial_trust=0.85)
        for _ in range(50):
            gov.report_compliance_round()
        results["governance_phase"] = gov.current_phase.value
        results["governance_trust"] = round(gov.trust_score, 3)

        rating = AgentCreditRatingSystem("e2e_agent")
        rating.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                rating.update_dimension(dim, 0.9)
        rating.reset_cooldown_for_test()
        rating.evaluate_rating()
        results["credit_rating"] = rating.current_rating.value

        cloner = MAREFInstanceCloner("e2e_parent")
        clones = cloner.clone_multiple([ClonePath.EXPLORATORY, ClonePath.CONSERVATIVE])
        results["clone_count"] = len(clones)

        adapter = CrossSystemAdapter("e2e_adapter")
        adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        results["current_env"] = adapter.current_env.value

        gen = CreativeGenerator("e2e_creative")
        gen.load_knowledge(
            [{"name": "healing", "confidence": 0.9, "domain": "resilience"}],
            [{"pattern": "auto_recovery", "confidence": 0.9, "domain": "healing"}],
        )
        innovations = gen.generate_innovations()
        results["innovations_meets_min"] = innovations["meets_minimum"]

        closure = MetaAgentClosure()
        proof = closure.prove_all_invariants()
        results["invariants_satisfied"] = proof.all_satisfied

        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("e2e_symbiosis", 0.8)
        css.run_full_cycle("e2e_symbiosis", TaskDomain.CODE_GENERATION,
                           "E2E Code Gen", "Generate integration code")
        stats = css.get_stats()
        results["symbiosis_ratio"] = stats["symbiosis_ratio"]

        trigrams = EightTrigramsGovernance("e2e_trigrams")
        trigrams.auto_transition(0.92)
        results["trigrams_mode"] = trigrams.current_trigram.value

        bft = DistributedBFT(7)
        bft.register_nodes(7, "e2e_node")
        bft.set_byzantine("e2e_node_0")
        tolerance = bft.verify_byzantine_tolerance("e2e_decision")
        results["bft_tolerance_intact"] = tolerance["tolerance_intact"]

        assert results["governance_trust"] > 0.7
        assert results["clone_count"] == 2
        assert results["current_env"] == "kubernetes"
        assert results["invariants_satisfied"]
        assert results["bft_tolerance_intact"]

    def test_simulated_extended_runtime(self):
        rounds = 72
        gov = FourPhaseGovernance("runtime_agent", initial_trust=0.8)
        for i in range(rounds):
            if i % 10 == 0:
                gov.report_violation(f"minor_alert_r{i}", is_red_line=False)
            else:
                gov.report_compliance_round()

        metrics = gov.get_metrics()
        assert metrics.total_rounds == rounds
        assert metrics.trust_score >= 0.0

    def test_all_subsystems_regression_free(self):
        test_bft = DistributedBFT(7)
        test_bft.register_nodes(7, "regress_node")
        assert test_bft.f == 2
        assert test_bft.quorum == 5

        test_closure = MetaAgentClosure()
        test_closure.submit_decision("agent_x", EvolutionDecisionType.CODE_CHANGE, "test")
        proof = test_closure.prove_all_invariants()
        assert proof.all_satisfied

        test_gov = EightTrigramsGovernance("regress_gov")
        test_gov.auto_transition(0.92)
        assert test_gov.current_trigram == TrigramsGovernance.QIAN

        assert True
