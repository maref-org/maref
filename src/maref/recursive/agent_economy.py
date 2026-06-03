from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


class EconomyPhase(str, Enum):
    TRADE = "trade"
    DISPUTE = "dispute"
    SANCTION = "sanction"
    RECOVERY = "recovery"


@dataclass
class CreditToken:
    token_id: str
    owner_id: str
    amount: float
    issued_at: float = field(default_factory=time.time)
    transaction_history: list[str] = field(default_factory=list)

    def transfer(self, new_owner: str, amount: float) -> float | None:
        if amount > self.amount:
            return None
        self.amount -= amount
        self.transaction_history.append(f"transfer_{amount}_to_{new_owner}_{int(time.time())}")
        return amount

    def deposit(self, amount: float) -> float:
        self.amount += amount
        self.transaction_history.append(f"deposit_{amount}_{int(time.time())}")
        return self.amount


@dataclass
class AgentWallet:
    agent_id: str
    balance: float = 100.0
    total_earned: float = 0.0
    total_spent: float = 0.0
    reputation: float = 0.5
    frozen: bool = False

    def can_spend(self, amount: float) -> bool:
        return not self.frozen and self.balance >= amount

    def credit(self, amount: float) -> float:
        self.balance += amount
        self.total_earned += amount
        return self.balance

    def debit(self, amount: float) -> float | None:
        if not self.can_spend(amount):
            return None
        self.balance -= amount
        self.total_spent += amount
        return self.balance


@dataclass
class TradeProposal:
    trade_id: str
    buyer_id: str
    seller_id: str
    item: str
    price: float
    status: str = "pending"
    timestamp: float = field(default_factory=time.time)


@dataclass
class TradeReceipt:
    trade_id: str
    buyer_id: str
    seller_id: str
    item: str
    price: float
    completed_at: float = field(default_factory=time.time)
    buyer_balance_after: float = 0.0
    seller_balance_after: float = 0.0

    def to_audit_record(self, round_num: int = 45) -> UnifiedAuditRecord:
        return UnifiedAuditRecord(
            record_id=make_record_id("trade", hash(self.trade_id) % 100000),
            timestamp=self.completed_at,
            layer="evolution",
            round=round_num,
            event_type="agent_trade",
            source_module="AgentEconomy",
            target_module=f"{self.buyer_id}↔{self.seller_id}",
            decision=f"trade_{self.item}",
            justification=f"Price={self.price}, item={self.item}",
            outcome="success",
            context_refs=[self.trade_id],
        )


@dataclass
class DisputeRecord:
    dispute_id: str
    trade_id: str
    complainant_id: str
    respondent_id: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "filed"
    resolution: str = ""
    penalty: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class SanctionRecord:
    sanction_id: str
    target_id: str
    sanction_type: str
    amount: float = 0.0
    duration_seconds: float = 3600.0
    reason: str = ""
    status: str = "active"
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self) -> None:
        if self.expires_at == 0.0:
            self.expires_at = self.issued_at + self.duration_seconds

    def is_active(self) -> bool:
        return self.status == "active" and time.time() < self.expires_at


class AgentEconomy:
    TRADE_FEE_RATE = 0.01
    DISPUTE_THRESHOLD = 0.3
    SANCTION_PENALTY_RATE = 0.1

    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._wallets: dict[str, AgentWallet] = {}
        self._trades: dict[str, TradeProposal] = {}
        self._receipts: list[TradeReceipt] = []
        self._disputes: dict[str, DisputeRecord] = {}
        self._sanctions: dict[str, SanctionRecord] = {}
        self._audit_store = audit_store or UnifiedAuditStore()

    def register_agent(self, agent_id: str, initial_balance: float = 100.0) -> AgentWallet:
        wallet = AgentWallet(agent_id=agent_id, balance=initial_balance)
        self._wallets[agent_id] = wallet
        return wallet

    def get_wallet(self, agent_id: str) -> AgentWallet | None:
        return self._wallets.get(agent_id)

    def propose_trade(
        self, buyer_id: str, seller_id: str, item: str, price: float
    ) -> TradeProposal | None:
        buyer = self._wallets.get(buyer_id)
        if buyer is None or not buyer.can_spend(price):
            return None
        trade = TradeProposal(
            trade_id=f"trade_{buyer_id}_{seller_id}_{int(time.time())}",
            buyer_id=buyer_id,
            seller_id=seller_id,
            item=item,
            price=price,
        )
        self._trades[trade.trade_id] = trade
        return trade

    def execute_trade(self, trade_id: str) -> TradeReceipt | None:
        trade = self._trades.get(trade_id)
        if trade is None or trade.status != "pending":
            return None

        buyer = self._wallets.get(trade.buyer_id)
        seller = self._wallets.get(trade.seller_id)
        if buyer is None or seller is None:
            return None

        fee = trade.price * self.TRADE_FEE_RATE
        total_cost = trade.price + fee

        buyer_result = buyer.debit(total_cost)
        if buyer_result is None:
            return None

        seller.credit(trade.price)

        trade.status = "completed"
        receipt = TradeReceipt(
            trade_id=trade_id,
            buyer_id=trade.buyer_id,
            seller_id=trade.seller_id,
            item=trade.item,
            price=trade.price,
            buyer_balance_after=buyer.balance,
            seller_balance_after=seller.balance,
        )
        self._receipts.append(receipt)
        self._audit_store.append(receipt.to_audit_record())
        return receipt

    def file_dispute(
        self,
        trade_id: str,
        complainant_id: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
    ) -> DisputeRecord | None:
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        respondent_id = (
            trade.seller_id
            if complainant_id == trade.buyer_id
            else trade.buyer_id
            if complainant_id == trade.seller_id
            else None
        )
        if respondent_id is None:
            return None

        dispute = DisputeRecord(
            dispute_id=f"dispute_{trade_id}_{int(time.time())}",
            trade_id=trade_id,
            complainant_id=complainant_id,
            respondent_id=respondent_id,
            reason=reason,
            evidence=evidence or {},
            timestamp=time.time(),
        )
        self._disputes[dispute.dispute_id] = dispute
        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("disp", hash(dispute.dispute_id) % 100000),
                timestamp=time.time(),
                layer="evolution",
                round=45,
                event_type="agent_dispute_filed",
                source_module="AgentEconomy",
                target_module=respondent_id,
                decision=f"dispute_{reason[:20]}",
                justification=f"Trade {trade_id}, complainant={complainant_id}",
                outcome="pending",
                context_refs=[trade_id, dispute.dispute_id],
            )
        )
        return dispute

    def resolve_dispute(
        self, dispute_id: str, resolution: str, penalty: float = 0.0, refund_amount: float = 0.0
    ) -> DisputeRecord | None:
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            return None

        dispute.status = "resolved"
        dispute.resolution = resolution
        dispute.penalty = penalty

        respondent = self._wallets.get(dispute.respondent_id)
        complainant = self._wallets.get(dispute.complainant_id)

        if penalty > 0 and respondent is not None:
            respondent.debit(penalty)
            if complainant is not None and refund_amount > 0:
                complainant.credit(refund_amount)

        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("disp_res", hash(dispute_id) % 100000),
                timestamp=time.time(),
                layer="evolution",
                round=45,
                event_type="agent_dispute_resolved",
                source_module="AgentEconomy",
                target_module=dispute.respondent_id,
                decision=resolution,
                justification=f"Penalty={penalty}, refund={refund_amount}",
                outcome="success",
                context_refs=[dispute_id],
            )
        )
        return dispute

    def sanction_agent(
        self,
        target_id: str,
        sanction_type: str,
        reason: str,
        penalty: float = 0.0,
        duration_seconds: float = 3600.0,
    ) -> SanctionRecord | None:
        wallet = self._wallets.get(target_id)
        if wallet is None:
            return None

        sanction = SanctionRecord(
            sanction_id=f"sanction_{target_id}_{int(time.time())}",
            target_id=target_id,
            sanction_type=sanction_type,
            amount=penalty,
            duration_seconds=duration_seconds,
            reason=reason,
        )

        if sanction_type == "freeze":
            wallet.frozen = True
        elif sanction_type == "penalty" and penalty > 0:
            wallet.debit(penalty)

        sanction.status = "active"
        self._sanctions[sanction.sanction_id] = sanction
        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("sanc", hash(sanction.sanction_id) % 100000),
                timestamp=time.time(),
                layer="evolution",
                round=45,
                event_type="agent_sanctioned",
                source_module="AgentEconomy",
                target_module=target_id,
                decision=f"{sanction_type}_{reason[:15]}",
                justification=f"Penalty={penalty}, duration={duration_seconds}s",
                outcome="success",
                context_refs=[sanction.sanction_id],
            )
        )
        return sanction

    def recover_agent(self, target_id: str) -> SanctionRecord | None:
        wallet = self._wallets.get(target_id)
        if wallet is None or not wallet.frozen:
            return None

        wallet.frozen = False

        for sanction in self._sanctions.values():
            if sanction.target_id == target_id and sanction.status == "active":
                sanction.status = "recovered"
                self._audit_store.append(
                    UnifiedAuditRecord(
                        record_id=make_record_id("rec", hash(sanction.sanction_id) % 100000),
                        timestamp=time.time(),
                        layer="evolution",
                        round=45,
                        event_type="agent_recovered",
                        source_module="AgentEconomy",
                        target_module=target_id,
                        decision="recover",
                        justification=f"Sanction {sanction.sanction_id} lifted",
                        outcome="success",
                        context_refs=[sanction.sanction_id],
                    )
                )
                return sanction
        return None

    def full_economy_cycle(
        self, buyer: str, seller: str, item: str, price: float
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"phase": EconomyPhase.TRADE.value}

        trade = self.propose_trade(buyer, seller, item, price)
        if trade is None:
            result["status"] = "trade_failed"
            return result

        receipt = self.execute_trade(trade.trade_id)
        if receipt is None:
            result["status"] = "execution_failed"
            return result
        result["trade"] = f"{item}@{price}"

        result["phase"] = EconomyPhase.DISPUTE.value
        dispute = self.file_dispute(
            trade.trade_id,
            buyer,
            "quality_not_as_described",
            {"actual_quality": 0.3, "promised_quality": 0.8},
        )
        if dispute:
            result["dispute"] = dispute.dispute_id

            resolved = self.resolve_dispute(
                dispute.dispute_id,
                "partial_refund",
                penalty=price * 0.2,
                refund_amount=price * 0.5,
            )
            if resolved:
                result["resolution"] = resolved.resolution

        result["phase"] = EconomyPhase.SANCTION.value
        sanction = self.sanction_agent(seller, "penalty", "low_quality_goods", penalty=price * 0.1)
        if sanction:
            result["sanction"] = sanction.sanction_id

        result["phase"] = EconomyPhase.RECOVERY.value
        self.recover_agent(seller)
        result["status"] = "cycle_complete"
        return result

    def get_statistics(self) -> dict[str, Any]:
        wallets = list(self._wallets.values())
        total_balance = sum(w.balance for w in wallets)
        total_trades = len(self._receipts)
        return {
            "total_agents": len(wallets),
            "total_balance": round(total_balance, 2),
            "total_trades": total_trades,
            "total_disputes": len(self._disputes),
            "total_sanctions": len(self._sanctions),
            "avg_balance": round(total_balance / max(len(wallets), 1), 2),
            "trade_volume": round(sum(r.price for r in self._receipts), 2),
        }

    @property
    def wallets(self) -> dict[str, AgentWallet]:
        return dict(self._wallets)

    def clear(self) -> None:
        self._wallets.clear()
        self._trades.clear()
        self._receipts.clear()
        self._disputes.clear()
        self._sanctions.clear()
