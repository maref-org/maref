from __future__ import annotations

import pytest

from maref.integration.flag_bridge import PolicySnapshot
from maref.learning.ab_test import ABResult, ABWinner
from maref.orchestration.deployment import (
    CanaryDecision,
    DeploymentOrchestrator,
    DeploymentRecord,
    DeploymentStatus,
)


@pytest.fixture
def baseline() -> PolicySnapshot:
    return PolicySnapshot(config={"param": 0.5}, metrics={"fnr": 0.1, "fpr": 0.05})


@pytest.fixture
def candidate() -> PolicySnapshot:
    return PolicySnapshot(config={"param": 0.6}, metrics={"fnr": 0.08, "fpr": 0.04})


class TestDeploymentOrchestrator:
    def test_propose_creates_record(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("test-policy", PolicySnapshot(config={}), PolicySnapshot(config={}))
        assert rec.id.startswith("deploy-")
        assert rec.status == DeploymentStatus.VALIDATED

    def test_propose_with_failed_gates(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose(
            "test-policy",
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
            gates=[("social_impact", False), ("constitution", True)],
        )
        assert rec.status == DeploymentStatus.PROPOSED
        assert "social_impact" in rec.gates_failed
        assert "constitution" in rec.gates_passed

    def test_propose_with_all_gates_passed(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose(
            "test-policy",
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
            gates=[("social_impact", True), ("constitution", True)],
        )
        assert rec.status == DeploymentStatus.VALIDATED
        assert rec.gates_passed == ["social_impact", "constitution"]

    def test_start_canary_returns_flag(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("canary-test", PolicySnapshot(config={}), PolicySnapshot(config={}))
        flag = orchestrator.start_canary(rec.id)
        assert flag is not None
        assert flag.key.startswith("maref_policy_")

    def test_start_canary_unknown_deployment(self) -> None:
        orchestrator = DeploymentOrchestrator()
        assert orchestrator.start_canary("nonexistent") is None

    def test_start_canary_sets_canary_status(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("canary-status", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        assert rec.status == DeploymentStatus.CANARY

    def test_evaluate_canary_promote(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("eval-promote", PolicySnapshot(config={}), PolicySnapshot(config={}))

        orchestrator.start_canary(rec.id)
        orchestrator.record_canary_metrics(
            rec.id,
            ABResult(
                winner=ABWinner.STRATEGY_B,
                confidence=0.8,
                decisions={},
                metric_deltas={},
                details={},
            ),
        )
        decision = orchestrator.evaluate_canary(rec.id)
        assert decision == CanaryDecision.PROMOTE

    def test_evaluate_canary_rollback(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("eval-rollback", PolicySnapshot(config={}), PolicySnapshot(config={}))

        orchestrator.start_canary(rec.id)
        orchestrator.record_canary_metrics(
            rec.id,
            ABResult(
                winner=ABWinner.STRATEGY_A,
                confidence=0.8,
                decisions={},
                metric_deltas={},
                details={},
            ),
        )
        decision = orchestrator.evaluate_canary(rec.id)
        assert decision == CanaryDecision.ROLLBACK

    def test_evaluate_canary_hold(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("eval-hold", PolicySnapshot(config={}), PolicySnapshot(config={}))

        orchestrator.start_canary(rec.id)
        orchestrator.record_canary_metrics(
            rec.id,
            ABResult(
                winner=ABWinner.NONE,
                confidence=0.4,
                decisions={},
                metric_deltas={},
                details={},
            ),
        )
        decision = orchestrator.evaluate_canary(rec.id)
        assert decision == CanaryDecision.HOLD

    def test_evaluate_canary_no_metrics(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("eval-nometrics", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        decision = orchestrator.evaluate_canary(rec.id)
        assert decision == CanaryDecision.HOLD

    def test_evaluate_canary_force_decision(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("eval-force", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        decision = orchestrator.evaluate_canary(rec.id, force_decision=CanaryDecision.PROMOTE)
        assert decision == CanaryDecision.PROMOTE

    def test_promote(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("promote-test", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        assert orchestrator.promote(rec.id, "all metrics green")
        assert rec.status == DeploymentStatus.PROMOTED
        assert rec.promoted_at > 0

    def test_promote_unknown(self) -> None:
        orchestrator = DeploymentOrchestrator()
        assert not orchestrator.promote("nonexistent")

    def test_rollback(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("rollback-test", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        assert orchestrator.rollback(rec.id, "metrics degraded")
        assert rec.status == DeploymentStatus.ROLLED_BACK
        assert rec.rolled_back_at > 0

    def test_rollback_unknown(self) -> None:
        orchestrator = DeploymentOrchestrator()
        assert not orchestrator.rollback("nonexistent")

    def test_get_deployment(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("get-test", PolicySnapshot(config={}), PolicySnapshot(config={}))
        assert orchestrator.get_deployment(rec.id) == rec
        assert orchestrator.get_deployment("nonexistent") is None

    def test_list_deployments_all(self) -> None:
        orchestrator = DeploymentOrchestrator()
        orchestrator.propose("d1", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.propose("d2", PolicySnapshot(config={}), PolicySnapshot(config={}))
        assert len(orchestrator.list_deployments()) == 2

    def test_list_deployments_filtered(self) -> None:
        orchestrator = DeploymentOrchestrator()
        rec = orchestrator.propose("filter-me", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.propose("other", PolicySnapshot(config={}), PolicySnapshot(config={}))
        orchestrator.start_canary(rec.id)
        canary_list = orchestrator.list_deployments(status=DeploymentStatus.CANARY)
        validated_list = orchestrator.list_deployments(status=DeploymentStatus.VALIDATED)
        assert len(canary_list) == 1
        assert canary_list[0].policy_name == "filter-me"
        assert len(validated_list) == 1

    def test_summary(self) -> None:
        orchestrator = DeploymentOrchestrator()
        orchestrator.propose("s1", PolicySnapshot(config={}), PolicySnapshot(config={}))
        s = orchestrator.summary()
        assert s["total_deployments"] == 1
        assert s["active_canaries"] == 0

    def test_record_to_dict(self) -> None:
        rec = DeploymentRecord(
            id="test-id",
            policy_name="test-policy",
            baseline=PolicySnapshot(config={}),
            candidate=PolicySnapshot(config={}),
            status=DeploymentStatus.PROPOSED,
        )
        d = rec.to_dict()
        assert d["id"] == "test-id"
        assert d["status"] == "proposed"

    def test_full_lifecycle(self) -> None:
        orchestrator = DeploymentOrchestrator()
        # Phase 1: propose
        rec = orchestrator.propose(
            "full-lifecycle",
            PolicySnapshot(config={"v": 1}, metrics={"fnr": 0.1}),
            PolicySnapshot(config={"v": 2}, metrics={"fnr": 0.08}),
            gates=[("social_impact", True), ("constitution", True)],
        )
        assert rec.status == DeploymentStatus.VALIDATED

        # Phase 2: canary
        flag = orchestrator.start_canary(rec.id)
        assert flag is not None

        # Record metrics
        orchestrator.record_canary_metrics(
            rec.id,
            ABResult(
                winner=ABWinner.STRATEGY_B,
                confidence=0.85,
                decisions={"fnr": 1},
                metric_deltas={"fnr": 0.02},
                details={},
            ),
        )

        # Phase 3: promote
        decision = orchestrator.evaluate_canary(rec.id)
        assert decision == CanaryDecision.PROMOTE
        assert orchestrator.promote(rec.id, "canary passed all gates")
        assert rec.status == DeploymentStatus.PROMOTED
