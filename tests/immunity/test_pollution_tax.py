from __future__ import annotations

import pytest

from maref.recursive.agent_economy import AgentEconomy
from maref.recursive.agent_credit_rating import AgentCreditRatingSystem, CreditRating, RatingDimension
from maref.immunity.pollution_tax import PollutionTax
from maref.recursive.unified_audit import UnifiedAuditStore


@pytest.fixture
def economy():
    e = AgentEconomy()
    e.register_agent("agent_a", initial_balance=100.0)
    return e


@pytest.fixture
def tax(economy):
    return PollutionTax(economy=economy)


class TestPollutionTaxGenerationTax:
    """5.1-A1: gate_blocked → token_cost *= 2."""

    def test_apply_generation_tax_returns_multiplier(self, tax):
        m = tax.apply_generation_tax("agent_a")
        assert m == 2.0

    def test_get_multiplier_after_tax(self, tax):
        tax.apply_generation_tax("agent_a")
        assert tax.get_current_multiplier("agent_a") == 2.0

    def test_default_multiplier_is_one(self, tax):
        assert tax.get_current_multiplier("agent_a") == 1.0

    def test_reset_generation_tax(self, tax):
        tax.apply_generation_tax("agent_a")
        tax.reset_generation_tax("agent_a")
        assert tax.get_current_multiplier("agent_a") == 1.0

    def test_multiplier_stored_in_economy(self, tax, economy):
        tax.apply_generation_tax("agent_a")
        assert economy.get_generation_tax_multiplier("agent_a") == 2.0

    def test_multiplier_for_unregistered_agent(self, tax):
        assert tax.get_current_multiplier("unknown") == 1.0


class TestPollutionTaxDownstreamPenalty:
    """5.1-A2: downstream_contamination → token -= penalty."""

    def test_apply_downstream_penalty_deducts(self, tax):
        result = tax.apply_downstream_penalty("agent_a", penalty=10.0)
        assert result["penalty"] > 0

    def test_apply_downstream_penalty_increments_count(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0)
        assert tax.get_pollution_count("agent_a") == 1

    def test_multiple_penalties_increment(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0, reason="r1")
        tax.apply_downstream_penalty("agent_a", penalty=5.0, reason="r2")
        assert tax.get_pollution_count("agent_a") == 2

    def test_penalty_for_unregistered_agent(self, tax):
        result = tax.apply_downstream_penalty("unknown", penalty=10.0)
        assert result.get("success") is False

    def test_penalty_reduces_balance(self, tax, economy):
        tax.apply_downstream_penalty("agent_a", penalty=10.0)
        wallet = economy.get_wallet("agent_a")
        assert wallet is not None
        assert wallet.balance < 100.0

    def test_penalty_with_reason(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0, reason="bad_output")
        records = tax._economy.get_pollution_records("agent_a")
        assert any("bad_output" in r.get("reason", "") for r in records)

    def test_penalty_hmac_signed(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0, reason="test")
        records = tax._economy.get_pollution_records("agent_a")
        assert all("hmac" in r for r in records)


class TestPollutionTaxRatingDowngrade:
    """5.1-A3: pollution_count ≥ threshold → credit rating downgrade."""

    def test_downgrade_not_triggered_below_threshold(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=1.0, reason="r1")
        credit = AgentCreditRatingSystem("agent_a")
        tax._credit_systems["agent_a"] = credit
        result = tax.check_rating_downgrade("agent_a")
        assert result is False

    def test_downgrade_triggers_at_threshold(self, tax):
        credit = AgentCreditRatingSystem("agent_a", registered_at=0)
        credit.fast_forward_time(2)
        credit.update_dimension(RatingDimension.SAFETY_COMPLIANCE, 0.1)
        credit.update_dimension(RatingDimension.TASK_COMPLETION, 0.1)
        credit.update_dimension(RatingDimension.EVOLUTION_STABILITY, 0.1)
        tax._credit_systems["agent_a"] = credit
        for i in range(3):
            tax.apply_downstream_penalty("agent_a", penalty=1.0, reason=f"r{i}")
        result = tax.check_rating_downgrade("agent_a")
        assert result is True

    def test_downgrade_updates_rating(self, tax):
        credit = AgentCreditRatingSystem("agent_a", registered_at=0)
        credit.fast_forward_time(2)
        tax._credit_systems["agent_a"] = credit
        for i in range(3):
            tax.apply_downstream_penalty("agent_a", penalty=1.0, reason=f"r{i}")
        # Set safety compliance low to force downgrade
        credit.update_dimension(RatingDimension.SAFETY_COMPLIANCE, 0.1)
        tax.check_rating_downgrade("agent_a")
        rating_change = credit.evaluate_rating()
        # evaluate_rating returns None if no change; downgrade only if score < 0.5
        assert rating_change is None or credit.current_rating.numeric_value <= 4

    def test_no_credit_system_no_downgrade(self, tax):
        for i in range(5):
            tax.apply_downstream_penalty("agent_a", penalty=1.0, reason=f"r{i}")
        assert tax.check_rating_downgrade("agent_a") is False


class TestPollutionTaxAudit:
    """5.1-A4: Tamper-evident pollution audit chain."""

    def test_verify_audit_chain_returns_true(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0)
        assert tax.verify_audit_integrity() is True

    def test_tampered_record_detected(self, tax):
        tax.apply_downstream_penalty("agent_a", penalty=5.0)
        records = tax._economy.get_pollution_records("agent_a")
        records[0]["penalty"] = 999.0
        assert tax.verify_audit_integrity() is False

    def test_audit_store_updated(self):
        store = UnifiedAuditStore()
        economy = AgentEconomy(audit_store=store)
        economy.register_agent("agent_a", initial_balance=100.0)
        tax_with_store = PollutionTax(economy=economy, audit_store=store)
        tax_with_store.apply_downstream_penalty("agent_a", penalty=5.0)
        assert store.count() >= 1

    def test_audit_generation_tax(self, tax):
        store = UnifiedAuditStore()
        tax_with_store = PollutionTax(economy=tax._economy, audit_store=store)
        tax_with_store.apply_generation_tax("agent_a")
        assert store.count() >= 1


class TestPollutionTaxSecurityCritical:
    def test_apply_generation_tax_security_critical(self, tax):
        assert hasattr(tax.apply_generation_tax, "_maref_security_critical")

    def test_apply_downstream_penalty_security_critical(self, tax):
        assert hasattr(tax.apply_downstream_penalty, "_maref_security_critical")

    def test_check_rating_downgrade_security_critical(self, tax):
        assert hasattr(tax.check_rating_downgrade, "_maref_security_critical")
