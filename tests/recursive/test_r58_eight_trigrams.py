from __future__ import annotations

from maref.recursive.eight_trigrams_governance import (
    TRIGRAM_CONFIG,
    TRIGRAM_TRANSITIONS,
    EightTrigramsGovernance,
    TrigramsGovernance,
    TrigramState,
    TrigramTransition,
)


class TestTrigramsGovernance:
    def test_all_eight_trigrams(self):
        assert len(TrigramsGovernance) == 8

    def test_trigram_labels(self):
        assert TrigramsGovernance.QIAN.label == "\u4e7e"
        assert TrigramsGovernance.KUN.label == "\u5764"

    def test_trigram_descriptions(self):
        assert (
            "自" in TrigramsGovernance.QIAN.description
            or "\u81ea" in TrigramsGovernance.QIAN.description
        )

    def test_all_have_config(self):
        for trigram in TrigramsGovernance:
            config = TRIGRAM_CONFIG[trigram]
            assert "trust_threshold" in config
            assert "red_line_level" in config
            assert "evolution_permission" in config
            assert "audit_frequency_hours" in config

    def test_all_have_transitions(self):
        for trigram in TrigramsGovernance:
            transitions = TRIGRAM_TRANSITIONS[trigram]
            assert len(transitions) >= 1

    def test_qian_highest_autonomy(self):
        qian = TRIGRAM_CONFIG[TrigramsGovernance.QIAN]
        kun = TRIGRAM_CONFIG[TrigramsGovernance.KUN]
        assert qian["trust_threshold"] > kun["trust_threshold"]
        assert qian["max_concurrent_actions"] > kun["max_concurrent_actions"]


class TestEightTrigramsGovernanceInit:
    def test_default_init(self):
        gov = EightTrigramsGovernance("agent_1")
        assert gov.agent_id == "agent_1"
        assert gov.current_trigram == TrigramsGovernance.DUI

    def test_init_config_available(self):
        gov = EightTrigramsGovernance("agent_1")
        config = gov.current_config
        assert "trust_threshold" in config


class TestTrigramForTrust:
    def test_high_trust_returns_qian(self):
        gov = EightTrigramsGovernance("agent_1")
        assert gov.get_trigram_for_trust(0.95) == TrigramsGovernance.QIAN

    def test_low_trust_returns_kun(self):
        gov = EightTrigramsGovernance("agent_1")
        assert gov.get_trigram_for_trust(0.25) == TrigramsGovernance.KUN

    def test_medium_trust_returns_mid_trigram(self):
        gov = EightTrigramsGovernance("agent_1")
        trigram = gov.get_trigram_for_trust(0.72)
        assert trigram in TrigramsGovernance


class TestCanTransition:
    def test_valid_transition(self):
        gov = EightTrigramsGovernance("agent_1")
        assert gov.can_transition(TrigramsGovernance.DUI, TrigramsGovernance.QIAN)

    def test_invalid_transition(self):
        gov = EightTrigramsGovernance("agent_1")
        assert not gov.can_transition(TrigramsGovernance.DUI, TrigramsGovernance.KUN)

    def test_self_transition(self):
        gov = EightTrigramsGovernance("agent_1")
        assert not gov.can_transition(TrigramsGovernance.DUI, TrigramsGovernance.DUI)


class TestTransition:
    def test_manual_transition(self):
        gov = EightTrigramsGovernance("agent_1")
        t = gov.transition(TrigramsGovernance.QIAN, "upgrade_to_full_autonomy")
        assert t is not None
        assert gov.current_trigram == TrigramsGovernance.QIAN

    def test_transition_to_same_returns_none(self):
        gov = EightTrigramsGovernance("agent_1")
        t = gov.transition(TrigramsGovernance.DUI, "no_change")
        assert t is None

    def test_transition_to_invalid_returns_none(self):
        gov = EightTrigramsGovernance("agent_1")
        t = gov.transition(TrigramsGovernance.KUN, "invalid_jump")
        assert t is None

    def test_auto_transition_by_trust(self):
        gov = EightTrigramsGovernance("agent_1")
        t = gov.auto_transition(0.92)
        assert t is not None
        assert gov.current_trigram == TrigramsGovernance.QIAN

    def test_update_trust_and_adapt(self):
        gov = EightTrigramsGovernance("agent_1")
        t = gov.update_trust_and_adapt(0.85)
        assert t is not None

    def test_update_with_violation_decreases_trust(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.update_trust_and_adapt(0.72, violation=True)
        assert gov.trust_score < 0.7


class TestAudit:
    def test_perform_audit(self):
        gov = EightTrigramsGovernance("agent_1")
        result = gov.perform_audit()
        assert result["trigram"] == "dui"
        assert result["audit_count"] == 1

    def test_multiple_audits(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.perform_audit()
        gov.perform_audit()
        result = gov.perform_audit()
        assert result["audit_count"] == 3


class TestQuery:
    def test_get_all_trigrams(self):
        gov = EightTrigramsGovernance("agent_1")
        all_t = gov.get_all_trigrams()
        assert len(all_t) == 8
        assert all("trigram" in t for t in all_t)

    def test_get_applicable_transitions(self):
        gov = EightTrigramsGovernance("agent_1")
        transitions = gov.get_applicable_transitions()
        assert len(transitions) >= 1
        assert all(isinstance(t, TrigramsGovernance) for t in transitions)

    def test_get_transition_history(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.transition(TrigramsGovernance.QIAN, "test")
        history = gov.get_transition_history()
        assert len(history) == 1
        assert isinstance(history[0], TrigramTransition)


class TestSerialization:
    def test_trigram_state_to_dict(self):
        state = TrigramState(TrigramsGovernance.QIAN, 0.9)
        d = state.to_dict()
        assert d["trigram"] == "qian"
        assert "config" in d

    def test_trigram_transition_to_dict(self):
        t = TrigramTransition(TrigramsGovernance.DUI, TrigramsGovernance.QIAN, "upgrade", 0.92)
        d = t.to_dict()
        assert d["from"] == "dui"
        assert d["to"] == "qian"

    def test_governance_to_dict(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.transition(TrigramsGovernance.QIAN, "upgrade")
        d = gov.to_dict()
        assert d["agent_id"] == "agent_1"
        assert "current_trigram" in d
        assert "config" in d
        assert "state" in d
        assert "applicable_transitions" in d


class TestFullCycle:
    def test_cycle_through_trigrams(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.update_trust_and_adapt(0.92)
        assert gov.current_trigram == TrigramsGovernance.QIAN
        gov.update_trust_and_adapt(0.75, violation=True)
        assert gov.current_trigram != TrigramsGovernance.QIAN

    def test_qian_has_full_evolution(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.transition(TrigramsGovernance.QIAN, "upgrade")
        config = gov.current_config
        assert config["evolution_permission"] == "full"
        assert config["innovation_allowed"]
        assert config["self_replication_allowed"]

    def test_kun_is_most_restrictive(self):
        gov = EightTrigramsGovernance("agent_1")
        gov.auto_transition(0.25)
        if gov.current_trigram == TrigramsGovernance.KUN:
            config = gov.current_config
            assert config["requires_human_signoff"]
            assert not config["innovation_allowed"]
        else:
            config = TRIGRAM_CONFIG[TrigramsGovernance.KUN]
            assert config["requires_human_signoff"]
            assert not config["innovation_allowed"]
