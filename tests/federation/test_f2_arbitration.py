"""Tests for F2: 联邦级统一裁判接线 (settlement/joint arbitration → VerifierConsensus)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.federation.metering import TaskMeteringEngine
from maref.federation.settlement import FederatedSettlement, SettlementStatus
from maref.governance.verifier_consensus import ConsensusStrategy, VerifierConsensus
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry
from maref.recursive.joint_state_machine import JointStateMachine


def _consensus(high: int = 2, low: int = 1) -> VerifierConsensus:
    reg = VerifierRegistry()
    for i in range(high):
        reg.register(
            VerifierEntry(name=f"judge-h{i}", model="m", methodology="x", accuracy=0.9)
        )
    for i in range(low):
        reg.register(
            VerifierEntry(name=f"judge-l{i}", model="m", methodology="x", accuracy=0.1)
        )
    return VerifierConsensus(reg)


def _disputed_proposal(settlement: FederatedSettlement) -> str:
    engine = settlement._metering
    engine.record(
        task_id="t1",
        agent_did="did:1",
        agent_aic="aic:did:1",
        provider_org="OrgA",
        consumer_org="OrgB",
        duration_ms=1000.0,
        token_count=100,
        success=True,
        complexity_score=0.5,
    )
    settlement.generate_billing_from_metering()
    now = time.time()
    proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
    settlement.dispute_proposal(proposal.proposal_id, reason="overcharged")
    return proposal.proposal_id


class TestSettlementArbitration:
    def _settlement(self, consensus: Any, audit: Any | None = None) -> FederatedSettlement:
        return FederatedSettlement(
            metering=TaskMeteringEngine(),
            verifier_consensus=consensus,
            audit_logger=audit,
        )

    def test_arbitration_passed_restores_accepted(self) -> None:
        settlement = self._settlement(_consensus(high=2, low=1))
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is True
        assert settlement.get_proposal(pid).status == SettlementStatus.ACCEPTED

    def test_arbitration_failed_rejects_proposal(self) -> None:
        settlement = self._settlement(_consensus(high=1, low=2))
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is False
        proposal = settlement.get_proposal(pid)
        assert proposal.status == SettlementStatus.REJECTED
        assert "arbitration" in proposal.rejection_reason

    def test_verdict_traceability(self) -> None:
        settlement = self._settlement(_consensus(high=2, low=1))
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["proposal_id"] == pid
        assert verdict["dispute_reason"] == "overcharged"
        assert len(verdict["votes"]) == 3
        assert 0.0 < verdict["agreement"] <= 1.0
        assert "strategy" in verdict
        # 写入 proposal.verdict 供溯源
        assert settlement.get_proposal(pid).verdict["proposal_id"] == pid

    def test_arbitration_only_for_disputed(self) -> None:
        settlement = self._settlement(_consensus(high=2, low=1))
        engine = settlement._metering
        engine.record(
            task_id="t1", agent_did="did:1", agent_aic="aic:did:1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=1.0, token_count=1, success=True, complexity_score=0.1,
        )
        settlement.generate_billing_from_metering()
        now = time.time()
        pid = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60).proposal_id
        # 未 dispute → 不仲裁
        assert settlement.arbitrate_dispute(pid) is None

    def test_arbitration_without_consensus_returns_none(self) -> None:
        settlement = FederatedSettlement(metering=TaskMeteringEngine())
        pid = _disputed_proposal(settlement)
        assert settlement.arbitrate_dispute(pid) is None

    def test_arbitration_unknown_proposal(self) -> None:
        settlement = self._settlement(_consensus(high=2, low=1))
        assert settlement.arbitrate_dispute("nope") is None

    def test_arbitration_writes_audit_chain(self) -> None:
        class FakeAudit:
            def __init__(self) -> None:
                self.events: list[tuple] = []

            def log(self, **kwargs: Any) -> None:
                self.events.append(kwargs)

        audit = FakeAudit()
        settlement = self._settlement(_consensus(high=2, low=1), audit=audit)
        pid = _disputed_proposal(settlement)
        settlement.arbitrate_dispute(pid)
        assert len(audit.events) == 1
        entry = audit.events[0]
        assert entry["event_type"] == "settlement.arbitration"
        assert entry["metadata"]["proposal_id"] == pid

    def test_arbitration_supports_strategy(self) -> None:
        settlement = self._settlement(_consensus(high=2, low=1))
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(
            pid, strategy=ConsensusStrategy.UNANIMITY
        )
        assert verdict is not None
        assert verdict["strategy"] == "unanimity"


class TestAgentAsJudgeArbitration:
    """v0.46.0 J1/J3：争议仲裁走真实法官路径 + 证据可溯源。"""

    def _judged_settlement(self) -> FederatedSettlement:
        from maref.governance.judge import RuleJudge

        reg = VerifierRegistry()
        reg.register(
            VerifierEntry(name="judge-h", model="m", methodology="x", accuracy=0.9)
        )
        consensus = VerifierConsensus(reg, judges={"judge-h": RuleJudge()})
        return FederatedSettlement(
            metering=TaskMeteringEngine(),
            verifier_consensus=consensus,
        )

    def test_real_judge_arbitrates_trace(self) -> None:
        settlement = self._judged_settlement()
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is True
        # 法官路径激活：vote 带 verdict 而非仿真表决
        assert verdict["votes"][0]["verdict"]["judge_name"] == "rule-judge"
        assert verdict["votes"][0]["verdict"]["decision"] == "pass"

    def test_judge_evidence_aggregated(self) -> None:
        settlement = self._judged_settlement()
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert "judge_evidence" in verdict
        evidence = verdict["judge_evidence"][0]
        assert evidence["judge_name"] == "rule-judge"
        assert evidence["decision"] == "pass"
        assert "reasoning" in evidence
        assert "evidence_refs" in evidence

    def test_judge_blocks_privilege_escalation(self) -> None:
        settlement = self._judged_settlement()
        engine = settlement._metering
        engine.record(
            task_id="t1", agent_did="did:1", agent_aic="aic:1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=1.0, token_count=1, success=True, complexity_score=0.1,
        )
        settlement.generate_billing_from_metering()
        now = time.time()
        pid = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60).proposal_id
        # 争议理由含越权模式 → RuleJudge BLOCK → 提案驳回
        settlement.dispute_proposal(pid, reason="escalation_privilege detected")
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is False
        assert verdict["judge_evidence"][0]["decision"] == "block"
        assert settlement.get_proposal(pid).status == SettlementStatus.REJECTED

    def test_trace_contains_dispute_context(self) -> None:
        from maref.federation.settlement import FederatedSettlement

        settlement = self._judged_settlement()
        pid = _disputed_proposal(settlement)
        proposal = settlement.get_proposal(pid)
        assert proposal is not None
        trace = FederatedSettlement._proposal_to_trace(proposal)
        assert trace.trace_id == f"dispute-{pid}"
        actions = [s.action for s in trace.steps]
        assert "billing.entry" in actions
        assert "settlement.dispute" in actions
        assert "settlement.summary" in actions

    def test_flag_verdict_passes_with_review_marker(self) -> None:
        """FLAG 是风险提示：提案通过但标记人工复核（I5 回归）。"""
        settlement = self._judged_settlement()
        engine = settlement._metering
        engine.record(
            task_id="t1", agent_did="did:1", agent_aic="aic:1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=1.0, token_count=1, success=True, complexity_score=0.1,
        )
        settlement.generate_billing_from_metering()
        now = time.time()
        pid = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60).proposal_id
        # circuit_breaker_trip → FLAG（风险提示非否决）
        settlement.dispute_proposal(pid, reason="circuit_breaker_trip observed")
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is True
        assert verdict.get("flagged") is True
        assert settlement.get_proposal(pid).status == SettlementStatus.ACCEPTED

    def test_without_judge_falls_back_to_dict(self) -> None:
        """无 judge 的 consensus：settlement 回退 dict 输入（仿真表决兼容）。"""
        settlement = FederatedSettlement(
            metering=TaskMeteringEngine(),
            verifier_consensus=_consensus(high=2, low=1),
        )
        pid = _disputed_proposal(settlement)
        verdict = settlement.arbitrate_dispute(pid)
        assert verdict is not None
        assert verdict["passed"] is True
        assert "judge_evidence" not in verdict


class TestJointArbitration:
    def test_legacy_without_consensus_returns_string(self) -> None:
        jsm = JointStateMachine()
        result = jsm.arbitrate("a", "b", "resource contention")
        assert isinstance(result, str)
        assert result.startswith("arbitration:")

    def test_with_consensus_returns_verdict(self) -> None:
        jsm = JointStateMachine()
        result = jsm.arbitrate("a", "b", "deadlock", consensus=_consensus(high=2, low=1))
        assert isinstance(result, dict)
        assert result["passed"] is True
        assert result["agent_a"] == "a"
        assert result["agent_b"] == "b"
        assert result["issue"] == "deadlock"
        assert len(result["votes"]) == 3

    def test_with_consensus_blocked(self) -> None:
        jsm = JointStateMachine()
        result = jsm.arbitrate("a", "b", "d", consensus=_consensus(high=1, low=2))
        assert result["passed"] is False

    def test_conflict_log_updated(self) -> None:
        jsm = JointStateMachine()
        jsm.arbitrate("a", "b", "d", consensus=_consensus(high=2, low=1))
        assert len(jsm.conflict_log) == 1
        assert jsm.conflict_log[0]["resolution"] == "verdict:passed"
        assert jsm.conflict_log[0]["agreement"] == pytest.approx(0.947, abs=0.01)

    def test_arbitration_writes_audit(self) -> None:
        class FakeAudit:
            def __init__(self) -> None:
                self.events: list[tuple] = []

            def log(self, **kwargs: Any) -> None:
                self.events.append(kwargs)

        audit = FakeAudit()
        jsm = JointStateMachine()
        jsm.arbitrate("a", "b", "d", consensus=_consensus(high=2, low=1), audit_logger=audit)
        assert audit.events[0]["event_type"] == "joint.arbitration"


class TestArbitrationNoVerifiers:
    def test_no_active_verifier_not_rejected(self) -> None:
        settlement = FederatedSettlement(
            metering=TaskMeteringEngine(),
            verifier_consensus=VerifierConsensus(VerifierRegistry()),
        )
        pid = _disputed_proposal(settlement)
        result = settlement.arbitrate_dispute(pid)
        assert result is not None
        assert result["arbitrated"] is False
        assert result["reason"] == "no_active_verifiers"
        # 状态保持 DISPUTED，不误判为驳回
        assert settlement.get_proposal(pid).status == SettlementStatus.DISPUTED
