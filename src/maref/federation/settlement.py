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

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from maref.federation.metering import TaskMeteringEngine
from maref.governance.db import DatabaseManager
from maref.governance.trace import Trace, TraceStep


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
    "per_task": 1.0,  # base charge per task
    "per_token": 0.0001,  # charge per token processed
    "per_ms": 0.0005,  # charge per millisecond of duration
    "success_bonus": 0.5,  # bonus multiplier for successful tasks
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
    # v0.44.0 F2：争议仲裁溯源 verdict（加权法官表决结果）。
    verdict: dict[str, Any] = field(default_factory=dict)

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
            "verdict": dict(self.verdict),
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


# ------------------------------------------------------------------
# Reconciliation primitives (Phase 3.2)
# ------------------------------------------------------------------


def billing_charge_key(entry: BillingEntry) -> str:
    """Stable reconciliation key for a billing entry (server-independent).

    Uses ``provider|consumer|task_id`` — the shared execution identity
    that both the provider and the consumer server agree on.  Server-local
    fields (``entry_id``, ``metric_id``) are excluded on purpose.
    """
    return f"{entry.provider_org}|{entry.consumer_org}|{entry.task_id}"


def billing_fingerprint(entry: BillingEntry) -> str:
    """Deterministic content fingerprint of a billing entry.

    Excludes server-local fields (``entry_id``, ``metric_id``,
    ``timestamp``) so that identical charges recorded on different
    servers hash equal.  The amount is rounded to 4 decimals, matching
    :meth:`BillingEntry.to_dict`.
    """
    raw = (
        f"{entry.provider_org}|{entry.consumer_org}|{entry.task_id}"
        f"|{entry.agent_did}|{round(entry.amount, 4)}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def merkle_root(fingerprints: list[str]) -> str | None:
    """Build a binary Merkle root from content fingerprints.

    Fingerprints are sorted before hashing so the root is independent
    of insertion order.  Returns ``None`` for an empty list.
    """
    if not fingerprints:
        return None
    leaves = sorted(fingerprints)
    while len(leaves) > 1:
        next_level: list[str] = []
        for i in range(0, len(leaves) - 1, 2):
            combined = leaves[i] + leaves[i + 1]
            next_level.append(hashlib.sha256(combined.encode()).hexdigest())
        if len(leaves) % 2 == 1:
            next_level.append(leaves[-1])
        leaves = next_level
    return leaves[0]


class FederatedSettlement:
    """Cross-organization settlement engine.

    Wraps a :class:`TaskMeteringEngine` to compute billing entries from
    recorded metrics and manage the settlement lifecycle.
    """

    def __init__(
        self,
        metering: TaskMeteringEngine,
        pricing_rules: dict[str, float] | None = None,
        db_path: str | Path | None = None,
        verifier_consensus: Any | None = None,
        audit_logger: Any | None = None,
        judges: dict[str, Any] | None = None,
    ) -> None:
        self._metering = metering
        self._pricing = dict(_DEFAULT_PRICING)
        if pricing_rules:
            self._pricing.update(pricing_rules)
        self._billing_entries: list[BillingEntry] = []
        self._proposals: dict[str, SettlementProposal] = {}
        self._ledger: dict[str, LedgerEntry] = {}
        # v0.44.0 F2：联邦级统一裁判接线 — 争议提交到加权法官表决。
        # v0.46.0 J2：注入 Agent-as-a-Judge 法官，争议走真实仲裁路径。
        self._verifier_consensus = verifier_consensus
        if self._verifier_consensus is not None and judges:
            try:
                self._verifier_consensus._judges = judges
            except AttributeError:
                pass
        self._audit_logger = audit_logger
        self._db: DatabaseManager | None = None
        if db_path is not None:
            self._db = DatabaseManager(db_path)
            self._init_schema()
            self._load_from_disk()

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS billing_entries (
                entry_id     TEXT PRIMARY KEY,
                provider_org TEXT NOT NULL,
                consumer_org TEXT NOT NULL,
                task_id      TEXT NOT NULL,
                agent_did    TEXT NOT NULL,
                amount       REAL NOT NULL,
                metric_id    TEXT NOT NULL,
                timestamp    REAL NOT NULL,
                description  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settlement_proposals (
                proposal_id      TEXT PRIMARY KEY,
                provider_org     TEXT NOT NULL,
                consumer_org     TEXT NOT NULL,
                period_start     REAL NOT NULL,
                period_end       REAL NOT NULL,
                entry_ids        TEXT NOT NULL,
                total_amount     REAL NOT NULL,
                status           TEXT NOT NULL,
                created_at       REAL NOT NULL,
                resolved_at      REAL,
                rejection_reason TEXT NOT NULL DEFAULT '',
                dispute_reason   TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS ledger_entries (
                org_pair_key TEXT PRIMARY KEY,
                provider_org TEXT NOT NULL,
                consumer_org TEXT NOT NULL,
                balance      REAL NOT NULL,
                settled      REAL NOT NULL
            );
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        # Billing entries
        for row in self._db.fetchall("SELECT * FROM billing_entries ORDER BY timestamp"):
            entry = BillingEntry(
                entry_id=row["entry_id"],
                provider_org=row["provider_org"],
                consumer_org=row["consumer_org"],
                task_id=row["task_id"],
                agent_did=row["agent_did"],
                amount=row["amount"],
                metric_id=row["metric_id"],
                timestamp=row["timestamp"],
                description=row["description"],
            )
            self._billing_entries.append(entry)
        # Proposals
        for row in self._db.fetchall("SELECT * FROM settlement_proposals ORDER BY created_at"):
            entry_ids = json.loads(row["entry_ids"])
            entries = [e for e in self._billing_entries if e.entry_id in entry_ids]
            proposal = SettlementProposal(
                proposal_id=row["proposal_id"],
                provider_org=row["provider_org"],
                consumer_org=row["consumer_org"],
                period_start=row["period_start"],
                period_end=row["period_end"],
                entries=entries,
                total_amount=row["total_amount"],
                status=SettlementStatus(row["status"]),
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
                rejection_reason=row["rejection_reason"],
                dispute_reason=row["dispute_reason"],
            )
            self._proposals[proposal.proposal_id] = proposal
        # Ledger
        for row in self._db.fetchall("SELECT * FROM ledger_entries"):
            key = row["org_pair_key"]
            self._ledger[key] = LedgerEntry(
                provider_org=row["provider_org"],
                consumer_org=row["consumer_org"],
                balance=row["balance"],
                settled=row["settled"],
            )

    def _persist_billing(self, entry: BillingEntry) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO billing_entries "
            "(entry_id, provider_org, consumer_org, task_id, agent_did, "
            "amount, metric_id, timestamp, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.entry_id,
                entry.provider_org,
                entry.consumer_org,
                entry.task_id,
                entry.agent_did,
                entry.amount,
                entry.metric_id,
                entry.timestamp,
                entry.description,
            ),
        )

    def _persist_proposal(self, proposal: SettlementProposal) -> None:
        if self._db is None:
            return
        entry_ids = json.dumps([e.entry_id for e in proposal.entries])
        self._db.execute(
            "INSERT OR REPLACE INTO settlement_proposals "
            "(proposal_id, provider_org, consumer_org, period_start, period_end, "
            "entry_ids, total_amount, status, created_at, resolved_at, "
            "rejection_reason, dispute_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.proposal_id,
                proposal.provider_org,
                proposal.consumer_org,
                proposal.period_start,
                proposal.period_end,
                entry_ids,
                proposal.total_amount,
                proposal.status.value,
                proposal.created_at,
                proposal.resolved_at,
                proposal.rejection_reason,
                proposal.dispute_reason,
            ),
        )

    def _persist_ledger(self, key: str, ledger: LedgerEntry) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO ledger_entries "
            "(org_pair_key, provider_org, consumer_org, balance, settled) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, ledger.provider_org, ledger.consumer_org, ledger.balance, ledger.settled),
        )

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
        success_multiplier = 1.0 + self._pricing["success_bonus"] if metric.success else 1.0
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
        self._persist_billing(entry)
        return entry

    def generate_billing_from_metering(self, since: float | None = None) -> list[BillingEntry]:
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
        self._persist_proposal(proposal)
        return proposal

    def accept_proposal(self, proposal_id: str) -> bool:
        """Accept a proposed settlement.  Returns False if not in PROPOSED state."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.PROPOSED:
            return False
        proposal.status = SettlementStatus.ACCEPTED
        proposal.resolved_at = time.time()
        self._persist_proposal(proposal)
        return True

    def reject_proposal(self, proposal_id: str, reason: str = "") -> bool:
        """Reject a proposed settlement."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.PROPOSED:
            return False
        proposal.status = SettlementStatus.REJECTED
        proposal.resolved_at = time.time()
        proposal.rejection_reason = reason
        self._persist_proposal(proposal)
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

        # Persist proposal first (SETTLED) so a crash won't re-settle on restart.
        self._persist_proposal(proposal)

        # Update ledger: reduce balance, increase settled.
        key = _org_pair_key(proposal.provider_org, proposal.consumer_org)
        ledger = self._ledger.get(key)
        if ledger is not None:
            ledger.balance -= proposal.total_amount
            ledger.settled += proposal.total_amount
            self._persist_ledger(key, ledger)
        return True

    def dispute_proposal(self, proposal_id: str, reason: str = "") -> bool:
        """Mark a proposal as disputed (halts settlement)."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return False
        if proposal.status in (SettlementStatus.SETTLED, SettlementStatus.REJECTED):
            return False
        proposal.status = SettlementStatus.DISPUTED
        proposal.dispute_reason = reason
        proposal.resolved_at = time.time()
        self._persist_proposal(proposal)
        return True

    def arbitrate_dispute(
        self,
        proposal_id: str,
        strategy: Any | None = None,
        weight_key: str = "accuracy",
    ) -> dict[str, Any] | None:
        """将争议提交到加权法官表决（v0.44.0 F2 联邦级统一裁判）。

        仅对 DISPUTED 提案生效。争议内容（``SettlementProposal.to_dict``）
        进入 :class:`VerifierConsensus.evaluate` 加权表决，输出可溯源
        verdict（含逐票记录、策略与一致率）：

        - 表决通过（``passed``）→ 争议成立，提案回到 ACCEPTED，可继续结算；
        - 表决不通过 → 争议驳回，提案置 REJECTED。

        verdict 写入 ``proposal.verdict`` 并通过 audit_logger 写审计链
        （event_type=``settlement.arbitration``），供事后复核。

        Args:
            proposal_id: 待仲裁的争议提案 ID。
            strategy: 表决策略（缺省用 VerifierConsensus 默认）。
            weight_key: 加权键（缺省 accuracy）。

        Returns:
            溯源 verdict dict；提案不存在/非 DISPUTED/未接线共识引擎时
            返回 None。
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != SettlementStatus.DISPUTED:
            return None
        if self._verifier_consensus is None:
            return None

        # v0.46.0 J1：争议提交为结构化 Trace，激活 Agent-as-a-Judge 真实仲裁路径。
        # 未注入法官时 verifier 保持仿真表决（向后兼容）。
        item: Trace | dict[str, Any] = self._proposal_to_trace(proposal)
        kwargs: dict[str, Any] = {"weight_key": weight_key}
        if strategy is not None:
            kwargs["strategy"] = strategy
        result = self._verifier_consensus.evaluate(item, **kwargs)

        if not result.votes:
            # 无可用 verifier：无法仲裁，不得误判为驳回（保持 DISPUTED）。
            return {
                "arbitrated": False,
                "reason": "no_active_verifiers",
                "proposal_id": proposal_id,
            }

        verdict: dict[str, Any] = result.to_dict()
        verdict["arbitrated"] = True
        verdict["proposal_id"] = proposal_id
        verdict["dispute_reason"] = proposal.dispute_reason
        # v0.46.0 J3：聚合各法官证据，供事后复核（judge_name/decision/reasoning）。
        judge_evidence: list[dict[str, Any]] = []
        for vote in result.votes:
            if "verdict" in vote and isinstance(vote["verdict"], dict):
                v = vote["verdict"]
                judge_evidence.append({
                    "verifier": vote.get("verifier", ""),
                    "weight": vote.get("weight", 0.0),
                    "judge_name": v.get("judge_name", ""),
                    "decision": v.get("decision", ""),
                    "reasoning": v.get("reasoning", ""),
                    "evidence_refs": list(v.get("evidence_refs", [])),
                })
        if judge_evidence:
            verdict["judge_evidence"] = judge_evidence

        if result.passed:
            proposal.status = SettlementStatus.ACCEPTED
        else:
            proposal.status = SettlementStatus.REJECTED
            proposal.rejection_reason = f"arbitration: {proposal.dispute_reason}"
        proposal.resolved_at = time.time()
        proposal.verdict = verdict
        self._persist_proposal(proposal)

        if self._audit_logger is not None:
            self._audit_logger.log(
                event_type="settlement.arbitration",
                actor="federated_settlement",
                action="arbitrate_dispute",
                details=(
                    f"proposal={proposal_id} passed={result.passed} "
                    f"agreement={result.agreement:.3f}"
                ),
                metadata=verdict,
            )
        return verdict

    @staticmethod
    def _proposal_to_trace(proposal: SettlementProposal) -> Trace:
        """把争议提案转为结构化执行轨迹（v0.46.0 J1）。

        将结算争议还原为可供法官仲裁的 TraceStep 序列：
        - 每笔计费条目（BillingEntry）→ 一条 TraceStep（action=billing.entry）
        - 争议声明（dispute）→ 一条 TraceStep（action=settlement.dispute）
        - 结算金额汇总 → 一条 TraceStep（action=settlement.summary）

        法官据此对"金额是否合理/条目是否越界"做模式仲裁。
        """
        trace = Trace(
            trace_id=f"dispute-{proposal.proposal_id}",
            agent_id=f"{proposal.consumer_org}->{proposal.provider_org}",
        )
        for entry in proposal.entries:
            trace.add_step(
                TraceStep(
                    agent_id=entry.agent_did,
                    action="billing.entry",
                    decision=(
                        "credit" if entry.amount >= 0 else "debit"
                    ),
                    context_hash=entry.entry_id,
                    ts=entry.timestamp,
                    metadata={
                        "provider_org": entry.provider_org,
                        "consumer_org": entry.consumer_org,
                        "task_id": entry.task_id,
                        "metric_id": entry.metric_id,
                        "amount": round(entry.amount, 4),
                    },
                )
            )
        if proposal.dispute_reason:
            trace.add_step(
                TraceStep(
                    agent_id=proposal.consumer_org,
                    action="settlement.dispute",
                    decision=proposal.dispute_reason,
                    metadata={"proposal_id": proposal.proposal_id},
                )
            )
        trace.add_step(
            TraceStep(
                agent_id=proposal.provider_org,
                action="settlement.summary",
                decision=f"total={round(proposal.total_amount, 4)}",
                metadata={
                    "proposal_id": proposal.proposal_id,
                    "entry_count": len(proposal.entries),
                },
            )
        )
        return trace

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
            proposals = [p for p in proposals if p.provider_org == org or p.consumer_org == org]
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
        self._persist_ledger(key, ledger)

    # ------------------------------------------------------------------
    # Reconciliation (Phase 3.2)
    # ------------------------------------------------------------------

    def billing_entries(self) -> list[BillingEntry]:
        """Return all recorded billing entries (read-only copy)."""
        return list(self._billing_entries)

    def compute_settlement_root(self) -> dict[str, Any]:
        """Compute the local settlement Merkle root over billing content.

        The root is deterministic across servers: identical charges
        produce an identical root, enabling cross-server reconciliation
        without shipping the full ledgers.
        """
        fingerprints = [billing_fingerprint(e) for e in self._billing_entries]
        return {
            "root_hash": merkle_root(fingerprints),
            "tree_size": len(fingerprints),
        }

    def ledger_snapshot(self) -> dict[str, Any]:
        """Export the local ledger as a reconciler-consumable snapshot.

        Each entry carries a ``charge_key`` (provider|consumer|task_id)
        and a content ``fingerprint``; see :func:`billing_charge_key`
        and :func:`billing_fingerprint`.
        """
        entries: list[dict[str, Any]] = [
            {
                "charge_key": billing_charge_key(e),
                "fingerprint": billing_fingerprint(e),
                "entry_id": e.entry_id,
                "provider_org": e.provider_org,
                "consumer_org": e.consumer_org,
                "task_id": e.task_id,
                "agent_did": e.agent_did,
                "amount": round(e.amount, 4),
            }
            for e in self._billing_entries
        ]
        return {
            "root_hash": merkle_root([e["fingerprint"] for e in entries]),
            "tree_size": len(entries),
            "entries": entries,
        }

    def authoritative_snapshot(self) -> dict[str, Any]:
        """Recompute the expected ledger from metering records (no mutation).

        Used as the arbitration source of truth when a reconciliation
        detects conflicts: the metering engine is the authoritative
        record of what actually happened.
        """
        entries: list[dict[str, Any]] = []
        for metric in self._metering.iter_all_metrics():
            if metric.provider_org == metric.consumer_org:
                continue
            amount = self.compute_amount(metric)
            entry = BillingEntry(
                entry_id="",
                provider_org=metric.provider_org,
                consumer_org=metric.consumer_org,
                task_id=metric.task_id,
                agent_did=metric.agent_did,
                amount=amount,
                metric_id=metric.metric_id,
                description="authoritative recomputation from metering",
            )
            entries.append(
                {
                    "charge_key": billing_charge_key(entry),
                    "fingerprint": billing_fingerprint(entry),
                    "provider_org": entry.provider_org,
                    "consumer_org": entry.consumer_org,
                    "task_id": entry.task_id,
                    "agent_did": entry.agent_did,
                    "amount": round(entry.amount, 4),
                }
            )
        return {
            "root_hash": merkle_root([e["fingerprint"] for e in entries]),
            "tree_size": len(entries),
            "entries": entries,
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def settlement_summary(self) -> dict[str, Any]:
        """Return a global summary of the settlement engine."""
        proposals = list(self._proposals.values())
        status_counts: dict[str, int] = {}
        for p in proposals:
            status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1

        total_outstanding = sum(abs(e.balance) for e in self._ledger.values())
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
