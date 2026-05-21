from __future__ import annotations

from maref.recursive.agent_economy import (
    AgentEconomy,
    AgentWallet,
    CreditToken,
)


class TestAgentWallet:
    def test_create_wallet(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=100.0)
        assert wallet.balance == 100.0

    def test_can_spend(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=50.0)
        assert wallet.can_spend(30.0)
        assert not wallet.can_spend(60.0)

    def test_credit(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=100.0)
        wallet.credit(50.0)
        assert wallet.balance == 150.0

    def test_debit(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=100.0)
        result = wallet.debit(30.0)
        assert result == 70.0

    def test_debit_insufficient(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=10.0)
        assert wallet.debit(100.0) is None

    def test_frozen_cannot_spend(self) -> None:
        wallet = AgentWallet(agent_id="a1", balance=100.0, frozen=True)
        assert not wallet.can_spend(10.0)


class TestCreditToken:
    def test_create(self) -> None:
        tok = CreditToken(token_id="t1", owner_id="a1", amount=100.0)
        assert tok.owner_id == "a1"

    def test_transfer(self) -> None:
        tok = CreditToken("t1", "a1", 100.0)
        result = tok.transfer("a2", 30.0)
        assert result == 30.0
        assert tok.amount == 70.0

    def test_transfer_insufficient(self) -> None:
        tok = CreditToken("t1", "a1", 10.0)
        assert tok.transfer("a2", 100.0) is None


class TestAgentEconomy:
    def setup_method(self) -> None:
        self.economy = AgentEconomy()

    def test_register_agent(self) -> None:
        wallet = self.economy.register_agent("agent_1", 200.0)
        assert wallet.balance == 200.0

    def test_propose_trade(self) -> None:
        self.economy.register_agent("buyer", 100.0)
        self.economy.register_agent("seller", 50.0)
        trade = self.economy.propose_trade("buyer", "seller", "data", 30.0)
        assert trade is not None
        assert trade.item == "data"

    def test_propose_trade_insufficient(self) -> None:
        self.economy.register_agent("buyer", 10.0)
        self.economy.register_agent("seller", 50.0)
        trade = self.economy.propose_trade("buyer", "seller", "data", 100.0)
        assert trade is None

    def test_execute_trade(self) -> None:
        self.economy.register_agent("buyer", 100.0)
        self.economy.register_agent("seller", 50.0)
        trade = self.economy.propose_trade("buyer", "seller", "data", 30.0)
        receipt = self.economy.execute_trade(trade.trade_id)
        assert receipt is not None
        assert self.economy.get_wallet("buyer").balance < 100.0
        assert self.economy.get_wallet("seller").balance > 50.0

    def test_file_dispute(self) -> None:
        self.economy.register_agent("buyer", 100.0)
        self.economy.register_agent("seller", 50.0)
        trade = self.economy.propose_trade("buyer", "seller", "data", 30.0)
        self.economy.execute_trade(trade.trade_id)
        dispute = self.economy.file_dispute(
            trade.trade_id, "buyer", "quality_issue",
        )
        assert dispute is not None

    def test_resolve_dispute(self) -> None:
        self.economy.register_agent("buyer", 100.0)
        self.economy.register_agent("seller", 50.0)
        trade = self.economy.propose_trade("buyer", "seller", "data", 30.0)
        self.economy.execute_trade(trade.trade_id)
        dispute = self.economy.file_dispute(
            trade.trade_id, "buyer", "quality_issue",
        )
        resolved = self.economy.resolve_dispute(
            dispute.dispute_id, "partial_refund", penalty=5.0, refund_amount=10.0,
        )
        assert resolved is not None
        assert resolved.status == "resolved"

    def test_sanction_agent(self) -> None:
        self.economy.register_agent("bad_agent", 100.0)
        sanction = self.economy.sanction_agent(
            "bad_agent", "penalty", "fraud", penalty=20.0,
        )
        assert sanction is not None
        wallet = self.economy.get_wallet("bad_agent")
        assert wallet.balance == 80.0

    def test_sanction_freeze(self) -> None:
        self.economy.register_agent("frozen_agent", 100.0)
        sanction = self.economy.sanction_agent(
            "frozen_agent", "freeze", "severe_violation",
        )
        assert sanction is not None
        wallet = self.economy.get_wallet("frozen_agent")
        assert wallet.frozen

    def test_recover_agent(self) -> None:
        self.economy.register_agent("recover_me", 100.0)
        self.economy.sanction_agent("recover_me", "freeze", "test")
        result = self.economy.recover_agent("recover_me")
        assert result is not None
        assert not self.economy.get_wallet("recover_me").frozen

    def test_full_economy_cycle(self) -> None:
        self.economy.register_agent("buyer", 100.0)
        self.economy.register_agent("seller", 50.0)
        result = self.economy.full_economy_cycle("buyer", "seller", "dataset", 40.0)
        assert result["status"] == "cycle_complete"
        assert result["trade"] == "dataset@40.0"

    def test_get_statistics(self) -> None:
        self.economy.register_agent("a1", 100.0)
        self.economy.register_agent("a2", 200.0)
        stats = self.economy.get_statistics()
        assert stats["total_agents"] == 2
        assert stats["total_balance"] == 300.0
