"""Unit tests for FederatedSettlement (cross-org settlement)."""

from __future__ import annotations

import time

import pytest

from maref.federation.metering import TaskMeteringEngine
from maref.federation.settlement import (
    FederatedSettlement,
    SettlementStatus,
)


@pytest.fixture
def metering() -> TaskMeteringEngine:
    return TaskMeteringEngine()


@pytest.fixture
def settlement(metering: TaskMeteringEngine) -> FederatedSettlement:
    return FederatedSettlement(metering=metering)


def _record_sample_metric(
    engine: TaskMeteringEngine,
    task_id: str = "task-1",
    provider_org: str = "OrgA",
    consumer_org: str = "OrgB",
    agent_did: str = "did:1",
    duration_ms: float = 1000.0,
    token_count: int = 100,
    success: bool = True,
    complexity: float = 0.5,
):
    return engine.record(
        task_id=task_id,
        agent_did=agent_did,
        agent_aic=f"aic:{agent_did}",
        provider_org=provider_org,
        consumer_org=consumer_org,
        duration_ms=duration_ms,
        token_count=token_count,
        success=success,
        complexity_score=complexity,
    )


class TestSettlementPricing:
    def test_compute_amount_basic(self, settlement: FederatedSettlement) -> None:
        class FakeMetric:
            duration_ms = 1000.0
            token_count = 100
            success = False
            complexity_score = 0.0

        amount = settlement.compute_amount(FakeMetric())
        # base(1.0) + tokens(100*0.0001=0.01) + duration(1000*0.0005=0.5) + complexity(0) = 1.51
        assert abs(amount - 1.51) < 0.01

    def test_compute_amount_success_bonus(self, settlement: FederatedSettlement) -> None:
        class FailedMetric:
            duration_ms = 0.0
            token_count = 0
            success = False
            complexity_score = 0.0

        class SuccessMetric:
            duration_ms = 0.0
            token_count = 0
            success = True
            complexity_score = 0.0

        failed_amount = settlement.compute_amount(FailedMetric())
        success_amount = settlement.compute_amount(SuccessMetric())
        # Success bonus is 0.5 → multiplier 1.5
        assert abs(success_amount - failed_amount * 1.5) < 0.01

    def test_custom_pricing_rules(self, metering: TaskMeteringEngine) -> None:
        settlement = FederatedSettlement(
            metering=metering, pricing_rules={"per_task": 10.0}
        )
        class M:
            duration_ms = 0.0
            token_count = 0
            success = False
            complexity_score = 0.0
        assert abs(settlement.compute_amount(M()) - 10.0) < 0.01

    def test_set_price(self, settlement: FederatedSettlement) -> None:
        settlement.set_price("per_task", 5.0)
        assert settlement.pricing["per_task"] == 5.0


class TestSettlementBilling:
    def test_record_billing_cross_org(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        metric = _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        entry = settlement.record_billing(metric)
        assert entry.entry_id.startswith("bill_")
        assert entry.provider_org == "OrgA"
        assert entry.consumer_org == "OrgB"
        assert entry.amount > 0

    def test_record_billing_intra_org_no_charge(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        metric = _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgA")
        entry = settlement.record_billing(metric)
        assert entry.entry_id == ""  # no real billing entry
        assert entry.amount == 0.0

    def test_record_billing_updates_ledger(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        metric = _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.record_billing(metric)
        # OrgB owes OrgA → balance positive for OrgA.
        assert settlement.get_balance("OrgA", "OrgB") > 0
        assert settlement.get_balance("OrgB", "OrgA") < 0

    def test_generate_billing_from_metering_idempotent(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, task_id="t1", provider_org="OrgA", consumer_org="OrgB")
        _record_sample_metric(metering, task_id="t2", provider_org="OrgA", consumer_org="OrgB")

        first_batch = settlement.generate_billing_from_metering()
        assert len(first_batch) == 2
        # Second call should produce no new entries (idempotent).
        second_batch = settlement.generate_billing_from_metering()
        assert len(second_batch) == 0

    def test_generate_billing_skips_internal_tasks(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, task_id="t1", provider_org="OrgA", consumer_org="OrgA")
        entries = settlement.generate_billing_from_metering()
        assert len(entries) == 0  # internal task → no billing


class TestSettlementProposals:
    def test_generate_proposal_aggregates_entries(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        for i in range(3):
            _record_sample_metric(
                metering, task_id=f"t{i}",
                provider_org="OrgA", consumer_org="OrgB",
            )
        settlement.generate_billing_from_metering()

        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        assert proposal.proposal_id.startswith("set_")
        assert len(proposal.entries) == 3
        assert proposal.total_amount > 0
        assert proposal.status == SettlementStatus.PROPOSED

    def test_generate_proposal_empty_period(
        self, settlement: FederatedSettlement
    ) -> None:
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        assert len(proposal.entries) == 0
        assert proposal.total_amount == 0.0

    def test_accept_proposal(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        assert settlement.accept_proposal(proposal.proposal_id) is True
        assert proposal.status == SettlementStatus.ACCEPTED
        assert proposal.resolved_at is not None

    def test_accept_proposal_rejects_non_proposed(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        settlement.accept_proposal(proposal.proposal_id)
        # Already accepted → cannot accept again.
        assert settlement.accept_proposal(proposal.proposal_id) is False

    def test_reject_proposal_with_reason(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        assert settlement.reject_proposal(proposal.proposal_id, reason="disputed charges") is True
        assert proposal.status == SettlementStatus.REJECTED
        assert proposal.rejection_reason == "disputed charges"

    def test_settle_proposal_updates_ledger(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        balance_before = settlement.get_balance("OrgA", "OrgB")
        settlement.accept_proposal(proposal.proposal_id)
        settlement.settle_proposal(proposal.proposal_id)

        assert proposal.status == SettlementStatus.SETTLED
        balance_after = settlement.get_balance("OrgA", "OrgB")
        # Settling reduces the outstanding balance.
        assert balance_after < balance_before

    def test_settle_proposal_rejects_non_accepted(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        # Can't settle a PROPOSED (not yet accepted) proposal.
        assert settlement.settle_proposal(proposal.proposal_id) is False

    def test_dispute_proposal(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)

        assert settlement.dispute_proposal(proposal.proposal_id, reason="charge mismatch") is True
        assert proposal.status == SettlementStatus.DISPUTED
        assert proposal.dispute_reason == "charge mismatch"

    def test_dispute_rejects_settled(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        settlement.accept_proposal(proposal.proposal_id)
        settlement.settle_proposal(proposal.proposal_id)

        assert settlement.dispute_proposal(proposal.proposal_id) is False

    def test_list_proposals_filter_by_org(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, task_id="t1", provider_org="OrgA", consumer_org="OrgB")
        _record_sample_metric(metering, task_id="t2", provider_org="OrgC", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()

        settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        settlement.generate_proposal("OrgC", "OrgB", now - 60, now + 60)

        # Filter by OrgA → only the OrgA→OrgB proposal.
        orga_proposals = settlement.list_proposals(org="OrgA")
        assert len(orga_proposals) == 1
        assert orga_proposals[0].provider_org == "OrgA"

        # Filter by OrgB → both proposals (OrgB is consumer in both).
        orgb_proposals = settlement.list_proposals(org="OrgB")
        assert len(orgb_proposals) == 2

    def test_list_proposals_filter_by_status(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        p1 = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        settlement.accept_proposal(p1.proposal_id)

        settlement.generate_proposal("OrgA", "OrgB", now - 120, now - 60)
        # Second proposal stays PROPOSED.

        accepted = settlement.list_proposals(status=SettlementStatus.ACCEPTED)
        proposed = settlement.list_proposals(status=SettlementStatus.PROPOSED)
        assert len(accepted) == 1
        assert len(proposed) == 1


class TestSettlementLedger:
    def test_get_balance_no_transactions(self, settlement: FederatedSettlement) -> None:
        assert settlement.get_balance("OrgA", "OrgB") == 0.0

    def test_get_balance_directional(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()

        # OrgA is provider → positive balance (OrgB owes OrgA).
        assert settlement.get_balance("OrgA", "OrgB") > 0
        # Reverse direction → negative.
        assert settlement.get_balance("OrgB", "OrgA") < 0

    def test_get_ledger(self, settlement: FederatedSettlement, metering: TaskMeteringEngine) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        ledger = settlement.get_ledger()
        assert len(ledger) == 1
        assert ledger[0].provider_org == "OrgA"
        assert ledger[0].consumer_org == "OrgB"
        assert ledger[0].balance > 0


class TestSettlementSummary:
    def test_settlement_summary(
        self, settlement: FederatedSettlement, metering: TaskMeteringEngine
    ) -> None:
        _record_sample_metric(metering, provider_org="OrgA", consumer_org="OrgB")
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        settlement.accept_proposal(proposal.proposal_id)

        summary = settlement.settlement_summary()
        assert summary["total_billing_entries"] == 1
        assert summary["total_proposals"] == 1
        assert summary["status_counts"]["accepted"] == 1
        assert summary["ledger_entries"] == 1
        assert "pricing" in summary
