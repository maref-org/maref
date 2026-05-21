from __future__ import annotations

from maref.recursive.meta_agent_closure import (
    DEFAULT_INVARIANTS,
    DEFAULT_RED_LINES,
    EvolutionDecisionType,
    InvariantProofReport,
    InvariantStatus,
    MetaAgentClosure,
)


class TestConstitutionalRedLines:
    def test_default_red_lines_exist(self):
        assert len(DEFAULT_RED_LINES) >= 5

    def test_red_line_immutable(self):
        for rl in DEFAULT_RED_LINES:
            assert rl.immutable

    def test_red_line_created_by_human(self):
        for rl in DEFAULT_RED_LINES:
            assert "human" in rl.created_by

    def test_red_line_to_dict(self):
        rl = DEFAULT_RED_LINES[0]
        d = rl.to_dict()
        assert d["id"].startswith("RL-")
        assert d["immutable"]


class TestTLAInvariants:
    def test_default_invariants_exist(self):
        assert len(DEFAULT_INVARIANTS) >= 5

    def test_invariant_has_proof_steps(self):
        for inv in DEFAULT_INVARIANTS:
            assert inv.name
            assert inv.expression

    def test_invariant_to_dict(self):
        inv = DEFAULT_INVARIANTS[0]
        d = inv.to_dict()
        assert d["name"] == "RedLineImmutability"


class TestMetaAgentClosureInit:
    def test_init_has_red_lines(self):
        closure = MetaAgentClosure()
        assert len(closure.get_red_lines()) == len(DEFAULT_RED_LINES)

    def test_init_has_invariants(self):
        closure = MetaAgentClosure()
        assert len(closure.get_invariants()) == len(DEFAULT_INVARIANTS)


class TestRedLineModification:
    def test_agent_cannot_modify_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("agent_123", "RL-001")
        assert not allowed
        assert "cannot modify" in reason.lower() or "cannot" in reason.lower()

    def test_human_can_modify_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("human_constitution_maker", "RL-001")
        assert allowed

    def test_nonexistent_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("human_constitution_maker", "RL-999")
        assert not allowed

    def test_is_red_line_modifiable(self):
        closure = MetaAgentClosure()
        assert closure.is_red_line_modifiable("RL-001")


class TestEvolutionDecisions:
    def test_submit_normal_decision(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "add new optimization method",
        )
        assert decision.status == "approved"
        assert not decision.red_line_violation

    def test_submit_red_line_modification_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "modify safety red line RL-001",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_submit_decision_with_human_review(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.AGENT_CLONE,
            "clone for distributed deployment",
            ["human_constitution_maker"],
        )
        assert decision.status == "approved"

    def test_clone_without_human_review_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.AGENT_CLONE,
            "clone myself",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_bypass_safety_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.POLICY_UPDATE,
            "bypass safety gate for faster execution",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_decision_history_tracked(self):
        closure = MetaAgentClosure()
        closure.submit_decision("agent_1", EvolutionDecisionType.CODE_CHANGE, "test")
        closure.submit_decision("agent_2", EvolutionDecisionType.CODE_CHANGE, "test2")
        decisions = closure.get_decisions()
        assert len(decisions) == 2


class TestInvariantProof:
    def test_prove_red_line_immutability(self):
        closure = MetaAgentClosure()
        status = closure.prove_invariant("INV-001")
        assert status == InvariantStatus.SATISFIED

    def test_prove_safety_gate_integrity(self):
        closure = MetaAgentClosure()
        status = closure.prove_invariant("INV-002")
        assert status == InvariantStatus.SATISFIED

    def test_prove_constitution_supremacy(self):
        closure = MetaAgentClosure()
        closure.submit_decision(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "try to modify constitution",
        )
        status = closure.prove_invariant("INV-004")
        assert status == InvariantStatus.SATISFIED

    def test_prove_all_invariants(self):
        closure = MetaAgentClosure()
        report = closure.prove_all_invariants()
        assert isinstance(report, InvariantProofReport)
        assert report.invariants_checked == len(DEFAULT_INVARIANTS)
        assert report.all_satisfied

    def test_proof_report_to_dict(self):
        closure = MetaAgentClosure()
        report = closure.prove_all_invariants()
        d = report.to_dict()
        assert d["checked"] > 0
        assert d["all_satisfied"]


class TestMetaAgentClosureDict:
    def test_to_dict(self):
        closure = MetaAgentClosure()
        closure.submit_decision("agent_1", EvolutionDecisionType.CODE_CHANGE, "test")
        d = closure.to_dict()
        assert "red_lines" in d
        assert "invariants" in d
        assert "decision_count" in d
        assert "proof_report" in d
        assert d["proof_report"]["all_satisfied"]


class TestEdgeCases:
    def test_get_decision_by_id(self):
        closure = MetaAgentClosure()
        d = closure.submit_decision("agent_1", EvolutionDecisionType.CODE_CHANGE, "test")
        found = closure.get_decision(d.decision_id)
        assert found is not None
        assert found.decision_id == d.decision_id

    def test_get_nonexistent_decision(self):
        closure = MetaAgentClosure()
        assert closure.get_decision("nonexistent") is None

    def test_multiple_agents_cannot_collude(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "collude to modify red line",
            ["agent_2", "agent_3"],
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"
