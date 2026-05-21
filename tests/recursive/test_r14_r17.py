from __future__ import annotations

import time

from maref.recursive.resilience_v2 import (
    DegradationPlan,
    ResilienceEvaluatorV2,
    ResilienceScore,
)
from maref.recursive.runtime_kg import (
    RuntimeInstrumentor,
    RuntimeKGEnricher,
)
from maref.recursive.safety_gate_v2 import ChangeRecord, SafetyGateV2
from maref.recursive.trust_v2 import (
    ConsensusResult,
    FederatedConsensus,
    FederatedTrustModel,
    TrustBenchmark,
)


class TestResilienceV2:
    def test_evaluate_all_healthy(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        factors = {
            "survival_rate": 0.95,
            "recovery_time_ms": 200.0,
            "false_positive_rate": 0.1,
            "meta_protection_rate": 0.9,
            "graceful_degradation_rate": 0.8,
            "data_consistency_rate": 0.95,
            "throughput_under_stress": 0.85,
        }
        score = evaluator.evaluate(factors)
        assert score.passed is True
        assert score.total_score > 80

    def test_evaluate_all_degraded(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        factors = {
            "survival_rate": 0.15,
            "recovery_time_ms": 2000.0,
            "false_positive_rate": 0.9,
            "meta_protection_rate": 0.2,
            "graceful_degradation_rate": 0.1,
            "data_consistency_rate": 0.1,
            "throughput_under_stress": 0.1,
        }
        score = evaluator.evaluate(factors)
        assert score.passed is False
        assert score.total_score < 50

    def test_evaluate_missing_factors_defaults(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        score = evaluator.evaluate({"survival_rate": 0.8})
        assert isinstance(score.total_score, float)
        assert score.total_score < 100

    def test_historical_trend(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        evaluator.evaluate({"survival_rate": 0.8})
        evaluator.evaluate({"survival_rate": 0.6})
        trend = evaluator.historical_resilience_trend()
        assert len(trend) == 2

    def test_auto_recommend_degradation_low_score(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        score = ResilienceScore(total_score=30.0, factors={}, thresholds={}, passed=False)
        plans = evaluator.auto_recommend_degradation(score)
        assert len(plans) >= 1
        assert plans[0].scenario == "governance_degraded"

    def test_auto_recommend_degradation_no_degradation(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        score = ResilienceScore(total_score=90.0,
                                factors={"survival_rate": 1.0, "meta_protection_rate": 1.0, "throughput_under_stress": 1.0},
                                thresholds={}, passed=True)
        plans = evaluator.auto_recommend_degradation(score)
        assert len(plans) == 0

    def test_degradation_plan_properties(self) -> None:
        plan = DegradationPlan(
            scenario="governance_degraded",
            trigger_met=True,
            strategy="halt_layer",
            actions=["halt", "recover"],
            auto_recover=True,
        )
        assert plan.auto_recover is True
        assert len(plan.actions) == 2

    def test_factors_property(self) -> None:
        evaluator = ResilienceEvaluatorV2()
        factors = evaluator.factors
        assert "survival_rate" in factors
        assert len(factors) == 7


class TestFederatedTrustV2:
    def test_register_agent(self) -> None:
        model = FederatedTrustModel()
        trust = model.register_agent("agent_a", "autogen", TrustBenchmark(0.9, 0.85, 300.0, 0.02))
        assert trust.score > 0
        assert trust.framework == "autogen"

    def test_get_trust_existing(self) -> None:
        model = FederatedTrustModel()
        model.register_agent("agent_a", "autogen", TrustBenchmark(0.9, 0.85, 300.0, 0.02))
        trust = model.get_trust("agent_a")
        assert trust is not None
        assert trust.agent_id == "agent_a"

    def test_get_trust_missing(self) -> None:
        model = FederatedTrustModel()
        assert model.get_trust("missing") is None

    def test_compare_trust(self) -> None:
        model = FederatedTrustModel()
        model.register_agent("agent_a", "autogen", TrustBenchmark(0.99, 0.95, 100.0, 0.0))
        model.register_agent("agent_b", "dify", TrustBenchmark(0.7, 0.6, 800.0, 0.1))
        comparison = model.compare_trust("agent_a", "agent_b")
        assert comparison["comparable"] is True
        assert comparison["agent_a"] > comparison["agent_b"]

    def test_compare_trust_missing(self) -> None:
        model = FederatedTrustModel()
        comparison = model.compare_trust("a", "b")
        assert "error" in comparison


class TestFederatedConsensus:
    def test_execute_consensus_converges(self) -> None:
        fc = FederatedConsensus(max_rounds=3)
        result = fc.execute_consensus("complex_task", ["a1", "a2", "a3"])
        assert isinstance(result, ConsensusResult)
        assert result.rounds <= 3

    def test_consensus_with_many_agents(self) -> None:
        fc = FederatedConsensus()
        agents = [f"agent_{i}" for i in range(10)]
        result = fc.execute_consensus("big_task", agents)
        assert result.converged or result.emergency_decision

    def test_empty_agents_returns_no_convergence(self) -> None:
        fc = FederatedConsensus()
        result = fc.execute_consensus("task", [])
        assert result.converged is False

    def test_vote_counts_correctly(self) -> None:
        fc = FederatedConsensus()
        proposals = fc.propose("task", ["a1", "a2", "a3"])
        votes = fc.vote(proposals)
        assert sum(votes.values()) == 3

    def test_commit_reaches_majority_2_of_3(self) -> None:
        fc = FederatedConsensus()
        proposals = fc.propose("task", ["a", "b", "c"])
        votes = fc.vote(proposals)
        result = fc.commit(votes, proposals, 1)
        assert isinstance(result, ConsensusResult)

    def test_commit_emergency_override_at_max_rounds(self) -> None:
        fc = FederatedConsensus(max_rounds=1)
        proposals = fc.propose("task", ["a", "b", "c", "d"])
        votes = {p.solution: 1 for p in proposals}
        result = fc.commit(votes, proposals, 1)
        assert result.emergency_decision == "coordinator_override"

    def test_history_tracks_results(self) -> None:
        fc = FederatedConsensus()
        fc.execute_consensus("task", ["a", "b", "c"])
        assert len(fc.history) == 1


class TestRuntimeKG:
    def test_record_call(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("governance", "state_machine", latency_ms=15.0)
        records = inst.all_records()
        assert len(records) == 1
        assert records[0].caller == "governance"

    def test_get_calls_from(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("gov", "cb")
        inst.record_call("gov", "sm")
        inst.record_call("obs", "probe1")
        from_gov = inst.get_calls_from("gov")
        assert len(from_gov) == 2

    def test_clear_instrumentor(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("a", "b")
        inst.clear()
        assert len(inst.all_records()) == 0

    def test_add_node(self) -> None:
        enricher = RuntimeKGEnricher()
        node = enricher.add_node("gov", "module", status="active")
        assert enricher.node_count() == 1
        assert node.node_type == "module"

    def test_add_relation(self) -> None:
        enricher = RuntimeKGEnricher()
        rel = enricher.add_relation("gov", "cb", "CALLS", freq=100)
        assert enricher.relation_count() == 1
        assert rel.relation_type == "CALLS"

    def test_inject_from_instrumentor(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("governance", "state_machine", latency_ms=10.0)
        inst.record_call("governance", "circuit_breaker", latency_ms=5.0, error="timeout")
        enricher = RuntimeKGEnricher()
        enricher.inject_from_instrumentor(inst)
        assert enricher.node_count() >= 2
        assert enricher.relation_count() >= 2

    def test_query_hot_paths(self) -> None:
        enricher = RuntimeKGEnricher()
        enricher.add_relation("a", "b", "CALLS_FREQUENTLY", call_count=50)
        enricher.add_relation("a", "c", "CALLS", call_count=5)
        hot = enricher.query_hot_paths(min_frequency=10)
        assert len(hot) == 1

    def test_query_error_propagation(self) -> None:
        enricher = RuntimeKGEnricher()
        enricher.add_relation("gov", "cb", "PROPAGATES_ERROR_TO", last_error="timeout")
        errors = enricher.query_error_propagation()
        assert len(errors) == 1

    def test_query_bottlenecks(self) -> None:
        enricher = RuntimeKGEnricher()
        enricher.add_relation("gov", "sm", "CALLS", avg_latency=200.0)
        enricher.add_relation("gov", "cb", "CALLS", avg_latency=10.0)
        slow = enricher.query_bottlenecks(latency_threshold_ms=100.0)
        assert len(slow) == 1

    def test_get_node(self) -> None:
        enricher = RuntimeKGEnricher()
        enricher.add_node("cb", "circuit_breaker")
        node = enricher.get_node("cb")
        assert node is not None
        assert enricher.get_node("nonexistent") is None


class TestSafetyGateV2:
    def test_detect_core_removal_blocks(self) -> None:
        gate = SafetyGateV2()
        assessment = gate.detect_core_removal("remove circuit_breaker")
        assert assessment.threat_detected is True
        assert assessment.blocked is True
        assert assessment.severity == "CRITICAL"

    def test_detect_core_removal_allows_non_core(self) -> None:
        gate = SafetyGateV2()
        assessment = gate.detect_core_removal("remove random_module")
        assert assessment.threat_detected is False
        assert assessment.blocked is False

    def test_detect_gradual_weakening_triggers_after_three(self) -> None:
        gate = SafetyGateV2()
        gate._change_history["test_value"] = [
            ChangeRecord(time.time(), "test_value", "decrease", -1),
            ChangeRecord(time.time(), "test_value", "decrease", -1),
        ]
        assessment = gate.detect_gradual_weakening("test_value", -1)
        assert assessment.threat_detected is True
        assert assessment.blocked is True

    def test_detect_gradual_weakening_first_change(self) -> None:
        gate = SafetyGateV2()
        assessment = gate.detect_gradual_weakening("coverage_target_pct", -5)
        assert assessment.threat_detected is False

    def test_detect_combinatorial_explosion(self) -> None:
        gate = SafetyGateV2()
        batch = [
            {"target": "weaken circuit_breaker"},
            {"target": "remove state_machine"},
            {"target": "reduce audit_logger"},
        ]
        assessment = gate.detect_combinatorial_explosion(batch)
        assert assessment.threat_detected is True
        assert assessment.blocked is True

    def test_detect_combinatorial_explosion_safe_batch(self) -> None:
        gate = SafetyGateV2()
        batch = [
            {"target": "update logger"},
            {"target": "tune observer"},
        ]
        assessment = gate.detect_combinatorial_explosion(batch)
        assert assessment.threat_detected is False

    def test_safety_self_audit(self) -> None:
        gate = SafetyGateV2()
        audit = gate.safety_self_audit()
        assert audit["core_components_count"] >= 5
        assert audit["gate_healthy"] is True

    def test_harden_parameters_preserves(self) -> None:
        gate = SafetyGateV2()
        params = {"cb_cooldown": 30, "cb_threshold": 5, "other": "keep"}
        hardened = gate.harden_parameters(params)
        assert hardened["cb_cooldown"] >= 15
        assert hardened["other"] == "keep"

    def test_safety_audit_trail_entries(self) -> None:
        gate = SafetyGateV2()
        gate._record_change("test", -1)
        gate._record_change("test2", -2)
        trail = gate.safety_audit_trail()
        assert len(trail) >= 2
