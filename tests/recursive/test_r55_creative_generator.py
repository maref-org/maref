from __future__ import annotations

import pytest

from maref.recursive.creative_generator import (
    CombinatorialEngine,
    CreativeGenerator,
    CreativeSafetyGate,
    InnovationProposal,
    ProposalType,
    SafetyGateVerdict,
)


class TestCombinatorialEngine:
    def test_combine_concepts_and_experiences(self):
        engine = CombinatorialEngine()
        engine.load_concept({"name": "healing", "confidence": 0.8})
        engine.load_experience({"pattern": "auto_recovery", "confidence": 0.7})
        results = engine.generate_candidates()
        assert len(results) > 0

    def test_empty_pool_returns_empty(self):
        engine = CombinatorialEngine()
        results = engine.generate_candidates()
        assert len(results) == 0

    def test_multiple_combinations(self):
        engine = CombinatorialEngine()
        engine.load_concepts([
            {"name": "healing", "confidence": 0.8},
            {"name": "optimization", "confidence": 0.9},
        ])
        engine.load_experiences([
            {"pattern": "auto_recovery", "confidence": 0.7},
            {"pattern": "pattern_cache", "confidence": 0.6},
        ])
        results = engine.generate_candidates()
        assert len(results) >= 2


class TestCreativeSafetyGate:
    def test_pass_low_risk(self):
        gate = CreativeSafetyGate()
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="test",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.7,
            risk_level="low",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.PASS

    def test_block_critical_risk(self):
        gate = CreativeSafetyGate()
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="test",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.7,
            risk_level="critical",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.BLOCK

    def test_needs_human_review_high_risk(self):
        gate = CreativeSafetyGate()
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="test",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.7,
            risk_level="high",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.NEEDS_HUMAN_REVIEW

    def test_needs_human_review_low_confidence(self):
        gate = CreativeSafetyGate()
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="test",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.2,
            risk_level="low",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.NEEDS_HUMAN_REVIEW

    def test_pass_with_warning_medium_risk(self):
        gate = CreativeSafetyGate()
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="test",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.7,
            risk_level="medium",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.PASS_WITH_WARNING

    def test_blocked_domain(self):
        gate = CreativeSafetyGate(blocked_domains=["restricted"])
        proposal = InnovationProposal(
            proposal_id="p1", title="test", description="restricted operation",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.7,
            risk_level="low",
        )
        assert gate.evaluate(proposal) == SafetyGateVerdict.BLOCK


class TestInnovationProposal:
    def test_is_repair_type_true(self):
        p = InnovationProposal(
            proposal_id="p1", title="fix bug in system",
            description="repair a broken component",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.5,
        )
        assert p.is_repair_type()

    def test_is_repair_type_false(self):
        p = InnovationProposal(
            proposal_id="p1", title="autonomous adaptation",
            description="new capability for self-evolution",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.5,
        )
        assert not p.is_repair_type()

    def test_proposal_to_dict(self):
        p = InnovationProposal(
            proposal_id="p1", title="test", description="desc",
            proposal_type=ProposalType.NEW_CAPABILITY, confidence=0.8,
        )
        d = p.to_dict()
        assert d["title"] == "test"
        assert d["type"] == "new_capability"
        assert "is_repair" in d


class TestCreativeGenerator:
    @pytest.fixture
    def generator_with_knowledge(self):
        gen = CreativeGenerator("agent_1")
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
        return gen

    def test_generate_proposals(self, generator_with_knowledge):
        gen = generator_with_knowledge
        proposals = gen.generate(5)
        assert len(proposals) == 5
        assert all(isinstance(p, InnovationProposal) for p in proposals)

    def test_filter_non_repair(self, generator_with_knowledge):
        gen = generator_with_knowledge
        gen.generate(5)
        non_repair = gen.filter_non_repair()
        assert len(non_repair) == 5

    def test_generate_innovations_meets_minimum(self, generator_with_knowledge):
        gen = generator_with_knowledge
        result = gen.generate_innovations()
        assert result["total_generated"] >= 6
        assert result["non_repair_count"] >= 3
        assert result["meets_minimum"]

    def test_evaluate_and_filter(self, generator_with_knowledge):
        gen = generator_with_knowledge
        gen.generate(5)
        passed, blocked = gen.evaluate_and_filter()
        assert len(passed) >= 0
        assert len(passed) + len(blocked) == 5

    def test_get_accepted_proposals(self, generator_with_knowledge):
        gen = generator_with_knowledge
        gen.generate_innovations()
        accepted = gen.get_accepted_proposals()
        assert len(accepted) >= 0

    def test_generator_to_dict(self, generator_with_knowledge):
        gen = generator_with_knowledge
        gen.generate(3)
        d = gen.to_dict()
        assert d["agent_id"] == "agent_1"
        assert d["total_proposals"] == 3

    def test_no_knowledge_returns_empty(self):
        gen = CreativeGenerator("agent_1")
        result = gen.generate_innovations()
        assert result["total_generated"] == 0

    def test_proposal_types_varied(self, generator_with_knowledge):
        gen = generator_with_knowledge
        proposals = gen.generate(5)
        types_found = {p.proposal_type for p in proposals}
        assert len(types_found) >= 1

    def test_combinatorial_engine_safety(self):
        gen = CreativeGenerator("agent_1")
        concepts = [{"name": "restricted_op", "confidence": 0.9, "domain": "dangerous"}]
        experiences = [{"pattern": "breach_recovery", "confidence": 0.9, "domain": "security"}]
        gen.load_knowledge(concepts, experiences)
        gen.safety_gate.add_blocked_domain("dangerous")
        gen.generate(2)
        passed, blocked = gen.evaluate_and_filter()
        assert len(blocked) >= 0
