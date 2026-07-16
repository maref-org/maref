"""MAREF Cross-Organization Settlement Protocol

Aggregates :class:`~maref.federation.metering.TaskMetric` records into
cross-org billing entries and settlement proposals.  When organization
A's agent serves organization B, the settlement protocol tracks that B
owes A and generates settlement proposals for review.

The settlement lifecycle is::

    PROPOSED → ACCEPTED → SETTLED
            ↘ REJECTED
            ↘ DISPUTED

References:
    - Plan §7 Phase 3: 跨组织结算协议 ``settlement.py``
    - Plan §4.2 workflow steps 13-14: 跨组织账单生成 + 结算协议执行
    - Depends on: :mod:`maref.federation.metering`
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.federation.metering import TaskMeteringEngine


class SettlementStatus(str, Enum):
    """Lifecycle status of a settlement proposal."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SETTLED = "settled"
    DISPUTED = "disputed"


# Default pricing per metric unit (in abstract "settlement units").
# These are configurable via the ``pricing_rules`` constructor arg.
_DEFAULT_PRICING: dict[str, float] = {
    "per_task": 1.0,        # base charge per task
    "per_token": 0.0001,    # charge per token processed
    "per_ms": 0.0005,       # charge per millisecond of duration
    "success_bonus": 0.5,   # bonus multiplier for successful tasks
    "complexity_multiplier": 1.0,  # multiplier for complexity score
}


@dataclass(frozen=True)
class BillingEntry:
    """A single charge entry: ``consumer_org`` owes ``provider_org``.

    ``amount`` is in abstract settlement units (not real currency).
    """

    entry_id: str
    provider_org: str
    consumer_org: str
    task_id: str
    agent_did: str
    amount: float
    metric_id: str
    timestamp: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "provider_org": self.provider_org,
            "consumer_org": self.consumer_org,
            "task_id": self.task_id,
            "agent_did": self.agent_did,
            "amount": round(self.amount, 4),
            "metric_id": self.metric_id,
            "timestamp": self.timestamp,
            "description": self.description,
        }


@dataclass
class SettlementProposal:
    """A proposed settlement for a billing period between two orgs."""

    proposal_id: str
    provider_org: str
    consumer_org: str
    period_start: float
    period_end: float
    entries: list[BillingEntry] = field(default_factory=list)
    total_amount: float = 0.0
    status: SettlementStatus = SettlementStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    rejection_reason: str = ""
    dispute_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "provider_org": self.provider_org,
            "consumer_org": self.consumer_org,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "entry_count": len(self.entries),
            "total_amount": round(self.total_amount, 4),
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "rejection_reason": self.rejection_reason,
            "dispute_reason": self.dispute_reason,
        }


@dataclass
class LedgerEntry:
    """Balance between two organisations.

    ``balance`` > 0 means ``consumer_org`` owes ``provider_org``.
    """

    provider_org: str
    consumer_org: str
    balance: float = 0.0
    settled: float = 0.0  # cumulative settled amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_org": self.provider_org,
            "consumer_org": self.consumer_org,
            "balance": round(self.balance, 4),
            "settled": round(self.settled, 4),
        }


def _org_pair_key(org_a: str, org_b: str) -> str:
    """Stable key for an org pair (alphabetically sorted)."""
    return "|".join(sorted((org_a, org_b)))


class FederatedSettlement:
    """Cross-organization settlement engine.

    Wraps a :class:`TaskMeteringEngine` to compute billing entries from
    recorded metrics and manage the settlement lifecycle.
    """

    def __init__(
        self,
        metering: TaskMeteringEngine,
        pricing_rules: dict[str, float] | None = None,
    ) -> None:
        self._metering = metering
        self._pricing = dict(_DEFAULT_PRICING)
        if pricing_rules:
            self._pricing.update(pricing_rules)
        self._billing_entries: list[BillingEntry] = []
        self._proposals: dict[str, SettlementProposal] = {}
        self._ledger: dict[str, LedgerEntry] = {}

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    @property
    def pricing(self) -> dict[str, float]:
        return dict(self._pricing)

    def set_price(self, key: str, value: float) -> None:
        """Update a single pricing rule."""
        self._pricing[key] = value

    def compute_amount(self, metric: Any) -> float:
        """Compute the settlement amount for a single metric.

        ``metric`` is expected to be a :class:`TaskMetric`-compatible
        object with ``duration_ms``, ``token_count``, ``success``, and
        ``complexity_score`` attributes.
        """
        base = self._pricing["per_task"]
        token_cost = metric.token_count * self._pricing["per_token"]
        duration_cost = metric.duration_ms * self._pricing["per_ms"]
        complexity_bonus = metric.complexity_score * self._pricing["complexity_multiplier"]
        success_multiplier = (
            1.0 + self._pricing["success_bonus"] if metric.success else 1.0
        )
        return (base + token_cost + duration_cost + complexity_bonus) * success_multiplier

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------

    def record_billing(self, metric: Any) -> BillingEntry:
        """Generate and record a billing entry from a task metric.

        ``metric`` must have ``provider_org``, ``consumer_org``,
        ``task_id``, ``agent_did``, and ``metric_id`` attributes.
        No entry is created if provider and consumer are the same org
        (internal tasks are not billable).
        """
        if metric.provider_org == metric.consumer_org:
            # Internal task — not billable across orgs.
            return BillingEntry(
                entry_id="",
                provider_org=metric.provider_org,
                consumer_org=metric.consumer_org,
                task_id=metric.task_id,
                agent_did=metric.agent_did,
                amount=0.0,
                metric_id=metric.metric_id,
                description="internal task — no cross-org charge",
            )

        amount = self.compute_amount(metric)
        entry = BillingEntry(
            entry_id=f"bill_{uuid.uuid4().hex}",
            provider_org=metric.provider_org,
            consumer_org=metric.consumer_org,
            task_id=metric.task_id,
            agent_did=metric.agent_did,
            amount=amount,
            metric_id=metric.metric_id,
            description=f"Task {metric.task_id} executed by {metric.agent_did}",
        )
        self._billing_entries.append(entry)
        self._update_ledger(entry)
        return entry

    def generate_billing_from_metering(
        self, since: float | None = None
    ) -> list[BillingEntry]:
        """Generate billing entries for all recorded metrics.

        If ``since`` is given, only metrics at or after that timestamp
        are processed.  Metrics that already have a billing entry are
        skipped (idempotent).
        """
        existing_metric_ids = {e.metric_id for e in self._billing_entries}
        new_entries: list[BillingEntry] = []

        # Iterate over all metrics via the public API.
        for metric in self._metering.iter_all_metrics():
            if metric.metric_id in existing_metric_ids:
                continue
            if since is not None and metric.timestamp < since:
                continue
            entry = self.record_billing(metric)
            if entry.entry_id:  # skip internal tasks
                new_entries.append(entry)

        return new_entries

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def generate_proposal(
        self,
        provider_org: str,
        consumer_org: str,
        period_start: float,
        period_end: float,
    ) -> SettlementProposal:
        """Generate a settlement proposal for a billing period.

        Aggregates all billing entries between ``provider_org`` and
        ``consumer_org`` within the period into a single proposal.
        """
        entries = [
            e
            for e in self._billing_entries
            if e.provider_org == provider_org
            and e.consumer_org == consumer_org
            and period_start <= e.timestamp <= period_end
        ]
        total = sum(e.amount for e in entries)
        proposal = SettlementProposal(
            proposal_id=f"set_{uuid.uuid4().hex}",
            provider_org=provider_org,
            consumer_org=consumer_org,
            period_start=period_start,
            period_end=period_end,
            entries=list(entries),
            total_amount=total,
        )
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def accept_proposal(self, proposal_id: str) -> bool:
        """Accept a proposed settlement.  Returns False if not in PROPOSED state."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.PROPOSED:
            return False
        proposal.status = SettlementStatus.ACCEPTED
        proposal.resolved_at = time.time()
        return True

    def reject_proposal(
        self, proposal_id: str, reason: str = ""
    ) -> bool:
        """Reject a proposed settlement."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.PROPOSED:
            return False
        proposal.status = SettlementStatus.REJECTED
        proposal.resolved_at = time.time()
        proposal.rejection_reason = reason
        return True

    def settle_proposal(self, proposal_id: str) -> bool:
        """Mark an accepted proposal as settled.

        Updates the ledger to reflect the settled amount.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.ACCEPTED:
            return False
        proposal.status = SettlementStatus.SETTLED
        proposal.resolved_at = time.time()

        # Update ledger: reduce balance, increase settled.
        key = _org_pair_key(proposal.provider_org, proposal.consumer_org)
        ledger = self._ledger.get(key)
        if ledger is not None:
            ledger.balance -= proposal.total_amount
            ledger.settled += proposal.total_amount
        return True

    def dispute_proposal(
        self, proposal_id: str, reason: str = ""
    ) -> bool:
        """Mark a proposal as disputed (halts settlement)."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return False
        if proposal.status in (SettlementStatus.SETTLED, SettlementStatus.REJECTED):
            return False
        proposal.status = SettlementStatus.DISPUTED
        proposal.dispute_reason = reason
        proposal.resolved_at = time.time()
        return True

    def get_proposal(self, proposal_id: str) -> SettlementProposal | None:
        return self._proposals.get(proposal_id)

    def list_proposals(
        self,
        org: str | None = None,
        status: SettlementStatus | None = None,
    ) -> list[SettlementProposal]:
        """List proposals, optionally filtered by org or status."""
        proposals = list(self._proposals.values())
        if org is not None:
            proposals = [
                p for p in proposals
                if p.provider_org == org or p.consumer_org == org
            ]
        if status is not None:
            proposals = [p for p in proposals if p.status == status]
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def get_balance(self, org_a: str, org_b: str) -> float:
        """Get the outstanding balance between two orgs.

        Positive means ``org_b`` owes ``org_a``; negative means
        ``org_a`` owes ``org_b``.  Returns 0.0 if no transactions.
        """
        key = _org_pair_key(org_a, org_b)
        ledger = self._ledger.get(key)
        if ledger is None:
            return 0.0
        # Determine direction: if org_a is the provider, balance is positive.
        if ledger.provider_org == org_a:
            return ledger.balance
        return -ledger.balance

    def get_ledger(self) -> list[LedgerEntry]:
        """Return all ledger entries."""
        return list(self._ledger.values())

    def _update_ledger(self, entry: BillingEntry) -> None:
        key = _org_pair_key(entry.provider_org, entry.consumer_org)
        if key not in self._ledger:
            self._ledger[key] = LedgerEntry(
                provider_org=entry.provider_org,
                consumer_org=entry.consumer_org,
            )
        ledger = self._ledger[key]
        # Ensure direction matches.
        if ledger.provider_org == entry.provider_org:
            ledger.balance += entry.amount
        else:
            ledger.balance -= entry.amount

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def settlement_summary(self) -> dict[str, Any]:
        """Return a global summary of the settlement engine."""
        proposals = list(self._proposals.values())
        status_counts: dict[str, int] = {}
        for p in proposals:
            status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1

        total_outstanding = sum(
            abs(e.balance) for e in self._ledger.values()
        )
        total_settled = sum(e.settled for e in self._ledger.values())

        return {
            "total_billing_entries": len(self._billing_entries),
            "total_proposals": len(proposals),
            "status_counts": status_counts,
            "total_outstanding": round(total_outstanding, 4),
            "total_settled": round(total_settled, 4),
            "ledger_entries": len(self._ledger),
            "pricing": dict(self._pricing),
        }
