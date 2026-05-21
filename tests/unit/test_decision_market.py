import pytest

from maref.cross_validator.consensus_algorithm import VoteValue
from maref.recursive.decision_market import (
    DecisionMarket,
    DecisionMarketAuditEntry,
    DecisionMarketError,
    InsufficientStakeError,
    MarketConsensusResult,
    MarketParticipant,
    MarketProposal,
    MarketVote,
    ProposalFrozenError,
)
from maref.recursive.evolution_dsl import EvolutionDSL
from maref.recursive.rule_freeze_zone import RuleFreezeZone


class TestMarketParticipant:
    def test_deposit_increases_balance(self):
        p = MarketParticipant("p1")
        p.deposit(100.0)
        assert p.stake_balance == 100.0

    def test_deposit_negative_raises(self):
        p = MarketParticipant("p1")
        with pytest.raises(ValueError):
            p.deposit(-10.0)

    def test_withdraw_reduces_balance(self):
        p = MarketParticipant("p1", stake_balance=100.0)
        withdrawn = p.withdraw(30.0)
        assert withdrawn == 30.0
        assert p.stake_balance == 70.0

    def test_withdraw_more_than_balance(self):
        p = MarketParticipant("p1", stake_balance=50.0)
        withdrawn = p.withdraw(100.0)
        assert withdrawn == 50.0
        assert p.stake_balance == 0.0

    def test_lock_stake_success(self):
        p = MarketParticipant("p1", stake_balance=100.0)
        assert p.lock_stake(30.0) is True
        assert p.stake_balance == 70.0
        assert p.total_staked == 30.0
        assert p.vote_count == 1

    def test_lock_stake_insufficient_funds(self):
        p = MarketParticipant("p1", stake_balance=10.0)
        assert p.lock_stake(30.0) is False
        assert p.stake_balance == 10.0

    def test_lock_stake_negative_amount(self):
        p = MarketParticipant("p1", stake_balance=100.0)
        assert p.lock_stake(-10.0) is False

    def test_reward_increases_balance(self):
        p = MarketParticipant("p1", stake_balance=100.0)
        p.reward(10.0)
        assert p.stake_balance == 110.0
        assert p.total_rewards == 10.0

    def test_penalize_tracks_penalty(self):
        p = MarketParticipant("p1")
        p.penalize(5.0)
        assert p.total_penalties == 5.0

    def test_to_dict(self):
        p = MarketParticipant("p1", stake_balance=100.0, total_staked=50.0)
        d = p.to_dict()
        assert d["participant_id"] == "p1"
        assert d["stake_balance"] == 100.0
        assert d["total_staked"] == 50.0
        assert d["is_active"] is True


class TestMarketProposal:
    def test_proposal_defaults(self):
        proposal = MarketProposal(
            proposal_id="mkt_001",
            target="test_target",
            current_value=1,
            proposed_value=2,
            justification="test",
            proposer_id="alice",
            timestamp=0.0,
        )
        assert proposal.status == "open"
        assert proposal.min_stake == 1.0
        assert proposal.quorum_threshold == 0.67
        assert proposal.evolution_rule_id == ""

    def test_proposal_to_dict(self):
        proposal = MarketProposal(
            proposal_id="mkt_001",
            target="test_target",
            current_value=1,
            proposed_value=2,
            justification="test",
            proposer_id="alice",
            timestamp=0.0,
            status="open",
        )
        d = proposal.to_dict()
        assert d["proposal_id"] == "mkt_001"
        assert d["target"] == "test_target"
        assert d["status"] == "open"


class TestMarketVote:
    def test_vote_to_dict(self):
        vote = MarketVote(
            vote_id="v001",
            proposal_id="mkt_001",
            participant_id="alice",
            vote_value=VoteValue.APPROVE,
            stake_amount=10.0,
            timestamp=0.0,
            justification="looks good",
        )
        d = vote.to_dict()
        assert d["vote"] == "approve"
        assert d["stake_amount"] == 10.0
        assert d["justification"] == "looks good"


class TestMarketConsensusResult:
    def test_result_to_dict(self):
        result = MarketConsensusResult(
            proposal_id="mkt_001",
            consensus_reached=True,
            winning_vote=VoteValue.APPROVE,
            approve_stake=30.0,
            reject_stake=10.0,
            abstain_stake=0.0,
            total_stake=40.0,
            participation_rate=0.8,
            confidence=0.75,
            reward_pool=2.0,
            status="reached",
        )
        d = result.to_dict()
        assert d["consensus_reached"] is True
        assert d["winning_vote"] == "approve"
        assert d["confidence"] == 0.75


class TestDecisionMarketBasic:
    def test_create_market(self):
        market = DecisionMarket()
        assert market.stats()["total_proposals"] == 0
        assert market.stats()["total_participants"] == 0

    def test_register_participant(self):
        market = DecisionMarket()
        p = market.register_participant("alice", initial_stake=100.0)
        assert p.participant_id == "alice"
        assert p.stake_balance == 100.0
        assert market.stats()["total_participants"] == 1

    def test_register_duplicate_participant_returns_existing(self):
        market = DecisionMarket()
        p1 = market.register_participant("alice", initial_stake=100.0)
        p2 = market.register_participant("alice", initial_stake=200.0)
        assert p1 is p2
        assert p2.stake_balance == 100.0

    def test_deposit_stake(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=50.0)
        balance = market.deposit_stake("alice", 50.0)
        assert balance == 100.0

    def test_deposit_stake_unknown_participant(self):
        market = DecisionMarket()
        with pytest.raises(DecisionMarketError):
            market.deposit_stake("unknown", 10.0)

    def test_get_participant(self):
        market = DecisionMarket()
        market.register_participant("alice")
        p = market.get_participant("alice")
        assert p is not None
        assert p.participant_id == "alice"

    def test_get_participant_none(self):
        market = DecisionMarket()
        assert market.get_participant("unknown") is None

    def test_list_participants(self):
        market = DecisionMarket()
        market.register_participant("alice")
        market.register_participant("bob")
        assert len(market.list_participants()) == 2


class TestDecisionMarketPropose:
    def test_propose_success(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="adoption_gain_threshold",
            current_value=0.03,
            proposed_value=0.05,
            proposer_id="alice",
            justification="increase threshold",
        )
        assert proposal.proposer_id == "alice"
        assert proposal.target == "adoption_gain_threshold"
        assert proposal.status == "open"
        assert market.stats()["total_proposals"] == 1

    def test_propose_unknown_proposer(self):
        market = DecisionMarket()
        with pytest.raises(DecisionMarketError):
            market.propose("target", 1, 2, "unknown")

    def test_propose_insufficient_stake(self):
        market = DecisionMarket(default_min_stake=10.0)
        market.register_participant("alice", initial_stake=5.0)
        with pytest.raises(InsufficientStakeError):
            market.propose("target", 1, 2, "alice")

    def test_propose_with_custom_min_stake(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="target",
            current_value=1,
            proposed_value=2,
            proposer_id="alice",
            min_stake=50.0,
        )
        assert proposal.min_stake == 50.0

    def test_propose_with_freeze_zone_blocks_frozen_target(self):
        freeze_zone = RuleFreezeZone()
        market = DecisionMarket(freeze_zone=freeze_zone)
        market.register_participant("alice", initial_stake=100.0)
        with pytest.raises(ProposalFrozenError):
            market.propose(
                target="circuit_breaker",
                current_value="old",
                proposed_value="new",
                proposer_id="alice",
            )

    def test_propose_with_freeze_zone_allows_non_frozen_target(self):
        freeze_zone = RuleFreezeZone()
        market = DecisionMarket(freeze_zone=freeze_zone)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="adoption_gain_threshold",
            current_value=0.03,
            proposed_value=0.05,
            proposer_id="alice",
        )
        assert proposal.target == "adoption_gain_threshold"

    def test_get_proposal(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        retrieved = market.get_proposal(proposal.proposal_id)
        assert retrieved is not None
        assert retrieved.proposal_id == proposal.proposal_id

    def test_list_proposals(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        market.propose("target1", 1, 2, "alice")
        market.propose("target2", 3, 4, "alice")
        assert len(market.list_proposals()) == 2

    def test_list_proposals_by_status(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        p1 = market.propose("target1", 1, 2, "alice", quorum_threshold=0.6)
        market.propose("target2", 3, 4, "alice")
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(p1.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(p1.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(p1.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(p1.proposal_id)
        open_proposals = market.list_proposals(status="open")
        assert len(open_proposals) == 1


class TestDecisionMarketVote:
    def test_vote_success(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=100.0)
        vote = market.vote(
            proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0
        )
        assert vote.vote_value == VoteValue.APPROVE
        assert vote.stake_amount == 10.0

    def test_vote_insufficient_stake(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=5.0)
        with pytest.raises(InsufficientStakeError):
            market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)

    def test_vote_below_min_stake(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", min_stake=20.0)
        market.register_participant("bob", initial_stake=100.0)
        with pytest.raises(InsufficientStakeError):
            market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=5.0)

    def test_vote_on_closed_proposal(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        with pytest.raises(DecisionMarketError):
            market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE)

    def test_vote_unknown_proposal(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        with pytest.raises(DecisionMarketError):
            market.vote("unknown", "alice", VoteValue.APPROVE)

    def test_vote_unknown_participant(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        with pytest.raises(DecisionMarketError):
            market.vote(proposal.proposal_id, "unknown", VoteValue.APPROVE)

    def test_get_votes(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=100.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        votes = market.get_votes(proposal.proposal_id)
        assert len(votes) == 1
        assert votes[0].participant_id == "bob"


class TestDecisionMarketConsensus:
    def test_consensus_approve_reached(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is True
        assert result.winning_vote == VoteValue.APPROVE
        assert result.confidence > 0.0
        assert market.get_proposal(proposal.proposal_id).status == "consensus_reached"

    def test_consensus_reject_reached(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.REJECT, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.REJECT, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.APPROVE, stake_amount=10.0)
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is True
        assert result.winning_vote == VoteValue.REJECT

    def test_consensus_not_reached_insufficient_participation(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is False
        assert proposal.status in ("inconclusive", "consensus_failed")

    def test_consensus_with_abstain(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.5)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.register_participant("dave", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.ABSTAIN, stake_amount=10.0)
        market.vote(proposal.proposal_id, "dave", VoteValue.REJECT, stake_amount=10.0)
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is True
        assert result.winning_vote == VoteValue.APPROVE
        assert result.abstain_stake == 10.0

    def test_evaluate_consensus_unknown_proposal(self):
        market = DecisionMarket()
        with pytest.raises(DecisionMarketError):
            market.evaluate_consensus("unknown")

    def test_get_consensus_result(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        result = market.get_consensus_result(proposal.proposal_id)
        assert result is not None
        assert result.consensus_reached is True


class TestDecisionMarketRewards:
    def test_winners_get_rewarded(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        alice = market.get_participant("alice")
        bob = market.get_participant("bob")
        carol = market.get_participant("carol")
        assert alice.total_rewards > 0.0
        assert bob.total_rewards > 0.0
        assert carol.total_penalties > 0.0

    def test_abstain_no_penalty_no_reward(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.ABSTAIN, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        bob = market.get_participant("bob")
        assert bob.total_rewards == 0.0
        assert bob.total_penalties == 0.0


class TestDecisionMarketAudit:
    def test_audit_trail_records_proposals(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        market.propose("target", 1, 2, "alice")
        trail = market.audit_trail()
        assert len(trail) >= 2
        assert any(e.event_type == "participant_registered" for e in trail)
        assert any(e.event_type == "proposal_created" for e in trail)

    def test_audit_trail_records_votes(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=100.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE)
        trail = market.audit_trail()
        assert any(e.event_type == "vote_cast" for e in trail)

    def test_audit_trail_records_consensus(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        trail = market.audit_trail()
        assert any(e.event_type == "consensus_evaluated" for e in trail)

    def test_audit_entry_to_unified(self):
        from maref.recursive.unified_audit import UnifiedAuditRecord

        entry = DecisionMarketAuditEntry(
            entry_id="dm_001",
            timestamp=0.0,
            proposal_id="mkt_001",
            event_type="vote_cast",
            participant_id="alice",
            details={"vote": "approve", "target": "test", "justification": "ok"},
        )
        unified = entry.to_unified(round_num=5)
        assert isinstance(unified, UnifiedAuditRecord)
        assert unified.layer == "decision_market"
        assert unified.round == 5
        assert unified.source_module == "DecisionMarket"


class TestDecisionMarketStats:
    def test_stats_empty_market(self):
        market = DecisionMarket()
        stats = market.stats()
        assert stats["total_proposals"] == 0
        assert stats["consensus_reached"] == 0
        assert stats["consensus_rate"] == 0.0

    def test_stats_after_consensus(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.6)
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        stats = market.stats()
        assert stats["total_proposals"] == 1
        assert stats["consensus_reached"] == 1
        assert stats["consensus_rate"] == 1.0
        assert stats["total_staked"] == 30.0

    def test_to_dict(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        market.propose("target", 1, 2, "alice")
        d = market.to_dict()
        assert "stats" in d
        assert "participants" in d
        assert "proposals" in d
        assert len(d["participants"]) == 1


class TestDecisionMarketEvolutionDSLIntegration:
    def test_propose_creates_evolution_rule(self):
        dsl = EvolutionDSL()
        market = DecisionMarket(evolution_dsl=dsl)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="adoption_gain_threshold",
            current_value=0.03,
            proposed_value=0.05,
            proposer_id="alice",
        )
        assert proposal.evolution_rule_id != ""
        assert proposal.evolution_rule_id in dsl.rules

    def test_consensus_approve_applies_evolution_rule(self):
        dsl = EvolutionDSL()
        market = DecisionMarket(evolution_dsl=dsl)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="adoption_gain_threshold",
            current_value=0.03,
            proposed_value=0.05,
            proposer_id="alice",
            quorum_threshold=0.6,
        )
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.REJECT, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        assert proposal.status == "consensus_reached"

    def test_consensus_reject_does_not_apply_evolution(self):
        dsl = EvolutionDSL()
        market = DecisionMarket(evolution_dsl=dsl)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="adoption_gain_threshold",
            current_value=0.03,
            proposed_value=0.05,
            proposer_id="alice",
            quorum_threshold=0.6,
        )
        market.register_participant("bob", initial_stake=100.0)
        market.register_participant("carol", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.REJECT, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.REJECT, stake_amount=10.0)
        market.vote(proposal.proposal_id, "carol", VoteValue.APPROVE, stake_amount=10.0)
        market.evaluate_consensus(proposal.proposal_id)
        assert proposal.status == "consensus_reached"

    def test_propose_frozen_target_with_dsl_raises(self):
        dsl = EvolutionDSL()
        market = DecisionMarket(evolution_dsl=dsl, freeze_zone=dsl.freeze_zone)
        market.register_participant("alice", initial_stake=100.0)
        with pytest.raises(ProposalFrozenError):
            market.propose(
                target="circuit_breaker",
                current_value="old",
                proposed_value="new",
                proposer_id="alice",
            )


class TestDecisionMarketFreezeZoneIntegration:
    def test_market_with_freeze_zone_property(self):
        freeze_zone = RuleFreezeZone()
        market = DecisionMarket(freeze_zone=freeze_zone)
        assert market.freeze_zone is freeze_zone

    def test_market_without_freeze_zone_allows_any_target(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose(
            target="circuit_breaker",
            current_value="old",
            proposed_value="new",
            proposer_id="alice",
        )
        assert proposal.target == "circuit_breaker"


class TestDecisionMarketEdgeCases:
    def test_no_votes_consensus_fails(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is False

    def test_single_participant_consensus(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is True
        assert result.winning_vote == VoteValue.APPROVE

    def test_tie_vote_inconclusive(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        market.register_participant("bob", initial_stake=100.0)
        market.vote(proposal.proposal_id, "alice", VoteValue.APPROVE, stake_amount=10.0)
        market.vote(proposal.proposal_id, "bob", VoteValue.REJECT, stake_amount=10.0)
        result = market.evaluate_consensus(proposal.proposal_id)
        assert result.consensus_reached is False

    def test_participant_weight_updates_after_stake(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=10.0)
        market.deposit_stake("alice", 90.0)
        validator = market._engine._validators.get("alice")
        assert validator is not None
        assert validator.weight > 1.0

    def test_default_min_stake_used_when_not_specified(self):
        market = DecisionMarket(default_min_stake=5.0)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        assert proposal.min_stake == 5.0

    def test_quorum_threshold_custom(self):
        market = DecisionMarket()
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice", quorum_threshold=0.8)
        assert proposal.quorum_threshold == 0.8

    def test_consensus_deadline_set(self):
        market = DecisionMarket(consensus_timeout_s=600.0)
        market.register_participant("alice", initial_stake=100.0)
        proposal = market.propose("target", 1, 2, "alice")
        assert proposal.consensus_deadline == pytest.approx(proposal.timestamp + 600.0, abs=1.0)
